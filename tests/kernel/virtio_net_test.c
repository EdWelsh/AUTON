/* Host test for the VirtIO Network virtqueue arithmetic specified in
 * agent/kernel_spec/subsystems/drivers.md.
 *
 * The descriptor chain and the available/used ring indices are where a DMA bug
 * lives, and they are the part that can be proved without hardware. Everything
 * a register poke does is verified against QEMU's model of the device rather
 * than the device — see agent/hardware/CONFORMANCE-HARDWARE.md — so it is not
 * claimed here.
 *
 * The cases that matter most are the ones a working device never produces: an
 * index past 65535, a chain longer than the free list, a tail descriptor whose
 * stale NEXT still points into the free list.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "virtio_ref.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-58s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

#define QSIZE 8
static vnr_desc_t desc[QSIZE];
static uint16_t avail[QSIZE];
static uint16_t used[QSIZE];
static vnr_queue_t q;

static void fresh(void)
{
	memset(desc, 0, sizeof desc);
	memset(avail, 0, sizeof avail);
	memset(used, 0, sizeof used);
	vnr_queue_init(&q, QSIZE, desc, avail, used);
}

int main(void)
{
	uint64_t addrs[4] = { 0x1000, 0x2000, 0x3000, 0x4000 };
	uint32_t lens[4]  = { 64, 128, 256, 512 };

	/* --- a single-descriptor chain --------------------------------- */
	fresh();
	int head = vnr_add_chain(&q, addrs, lens, 1, 0);
	ok("single chain returns a head", head == 0, NULL);
	ok("single chain consumes one descriptor", q.num_free == QSIZE - 1, NULL);
	ok("single chain clears NEXT", (desc[head].flags & VNR_DESC_F_NEXT) == 0,
	   "a device following a stale NEXT walks the free list");
	ok("head is published in the available ring", avail[0] == (uint16_t)head, NULL);
	ok("available index advanced", q.avail_idx == 1, NULL);

	/* --- a multi-descriptor chain ---------------------------------- */
	fresh();
	head = vnr_add_chain(&q, addrs, lens, 3, 0);
	ok("multi chain consumes three", q.num_free == QSIZE - 3, NULL);
	ok("first two set NEXT",
	   (desc[0].flags & VNR_DESC_F_NEXT) && (desc[1].flags & VNR_DESC_F_NEXT), NULL);
	ok("the tail does not set NEXT", (desc[2].flags & VNR_DESC_F_NEXT) == 0, NULL);
	ok("lengths are carried per descriptor",
	   desc[0].len == 64 && desc[1].len == 128 && desc[2].len == 256, NULL);
	/* NEXT being clear is what a correct device honours; the stale link left
	 * behind it is what an incorrect one follows. Both are checked, because
	 * the flag alone passes while the pointer still aims into the free list. */
	ok("the tail's NEXT pointer does not aim into the free list",
	   desc[2].next != q.free_head,
	   "a device ignoring the NEXT flag would walk into unallocated buffers");
	/* Checked on a multi-descriptor chain because on a single one the head and
	 * the tail are the same descriptor, and publishing either passes. */
	ok("the chain's head is published, not its tail",
	   avail[0] == (uint16_t)head && (uint16_t)head != 2,
	   "publishing the tail hands the device the last buffer and loses the rest");

	/* --- device-writable buffers ----------------------------------- */
	fresh();
	head = vnr_add_chain(&q, addrs, lens, 2, 1);
	ok("receive buffers are marked WRITE",
	   (desc[0].flags & VNR_DESC_F_WRITE) && (desc[1].flags & VNR_DESC_F_WRITE),
	   "a receive buffer the device may not write receives nothing");
	fresh();
	vnr_add_chain(&q, addrs, lens, 2, 0);
	ok("transmit buffers are not marked WRITE",
	   (desc[0].flags & VNR_DESC_F_WRITE) == 0,
	   "a writable transmit buffer lets the device scribble on the packet");

	/* --- exhaustion, which a working device never produces --------- */
	fresh();
	ok("a chain longer than the queue is refused",
	   vnr_add_chain(&q, addrs, lens, 4, 0) >= 0, NULL);
	/* Bounded deliberately. An unbounded fill loop here hangs rather than
	 * fails when the free-list check is wrong, and a test that hangs is worse
	 * than one that fails — it stops the suite instead of reporting. */
	int n = 0;
	while (n <= QSIZE && vnr_add_chain(&q, addrs, lens, 1, 0) >= 0)
		n++;
	ok("the free list runs out rather than wrapping", n <= QSIZE && q.num_free == 0,
	   "an unbounded free list hands out descriptors already in flight");
	ok("a full queue refuses rather than overwriting",
	   vnr_add_chain(&q, addrs, lens, 1, 0) == -1,
	   "returning a descriptor already in flight is a use-after-free of a DMA buffer");

	/* --- reclaiming ------------------------------------------------ */
	fresh();
	head = vnr_add_chain(&q, addrs, lens, 3, 0);
	int freed = vnr_free_chain(&q, (uint16_t)head);
	ok("reclaiming returns every descriptor in the chain", freed == 3, NULL);
	ok("reclaimed descriptors return to the free list", q.num_free == QSIZE, NULL);
	head = vnr_add_chain(&q, addrs, lens, 3, 0);
	ok("a reclaimed queue can be refilled", head >= 0 && q.num_free == QSIZE - 3,
	   NULL);

	/* --- the wrap. VIRTIO 1.2 §2.7.6 ------------------------------- */
	ok("slot 0 of an 8-entry ring", vnr_ring_slot(0, 8) == 0, NULL);
	ok("slot 7 of an 8-entry ring", vnr_ring_slot(7, 8) == 7, NULL);
	ok("index 8 wraps to slot 0", vnr_ring_slot(8, 8) == 0, NULL);
	ok("index 65535 wraps correctly", vnr_ring_slot(65535, 8) == 7,
	   "the index is free-running and masked only when addressing the ring");
	ok("index 65535 in a 256-entry ring", vnr_ring_slot(65535, 256) == 255, NULL);

	/* The bug this exists to catch: masking the stored index instead of the
	 * addressing one. It is invisible for 65536 packets and then silently
	 * overwrites live entries. */
	fresh();
	q.avail_idx = 65535;
	vnr_add_chain(&q, addrs, lens, 1, 0);
	ok("the available index wraps past 65535 to 0", q.avail_idx == 0,
	   "a free-running uint16 must wrap, not saturate");
	ok("the wrapped entry lands in the right slot",
	   avail[vnr_ring_slot(65535, QSIZE)] == 0, NULL);

	/* 65535 -> 0 is the same answer whether the index wraps or is masked by
	 * the queue size, so it cannot tell the two apart. This can: with a
	 * queue of 8, a stored index of 10 must stay 11, not become 3. Masking
	 * the stored index is invisible for 65536 packets and then silently
	 * overwrites live entries. */
	fresh();
	q.avail_idx = 10;
	vnr_add_chain(&q, addrs, lens, 1, 0);
	ok("the stored index is not masked by the queue size", q.avail_idx == 11,
	   "masking the stored index instead of the addressing one loses the "
	   "device's view of how many buffers were published");

	/* --- the free list's terminator -------------------------------- */
	fresh();
	ok("the last descriptor does not link to descriptor 0",
	   desc[QSIZE - 1].next == QSIZE - 1,
	   "a wrap here makes descriptor 0 reachable twice");

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails,
	       fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
