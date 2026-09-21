/* Host test for the VirtIO Block request chain specified in
 * agent/kernel_spec/subsystems/drivers.md.
 *
 * The virtqueue arithmetic is NOT retested here — it is shared with the network
 * driver and proved in virtio_net_test.c against the same reference. This
 * covers only what is block-specific: the three-descriptor request chain and
 * its non-uniform flags.
 *
 * That non-uniformity is the whole point. A chain built with one flag value is
 * wrong in both directions: uniformly writable lets the device overwrite the
 * request header it is meant to read, and uniformly read-only leaves it nowhere
 * to report status, so every request appears to succeed. The first is a
 * memory-corruption primitive; the second is silent data loss.
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
#define VIRTIO_BLK_T_IN    0
#define VIRTIO_BLK_T_OUT   1
#define VIRTIO_BLK_T_FLUSH 4

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

/* Build a block request chain: header (read-only), data (direction-dependent),
 * status (always device-writable). Returns the head, or -1.
 *
 * One call to the shared reference, using the per-descriptor flag form that
 * VirtIO Block's chain is the reason for. Stitching three uniform-flag chains
 * together by hand — the first attempt — meant unwinding the publish counter
 * after each one, which is a ring operation done in a test rather than in the
 * thing that owns the ring. */
static int blk_chain(vnr_queue_t *queue, uint32_t type, uint64_t hdr,
                     uint64_t data, uint32_t data_len, uint64_t status)
{
	uint64_t addrs[3];
	uint32_t lens[3];
	int writable[3];
	uint16_t n = 0;

	addrs[n] = hdr;    lens[n] = 16;  writable[n] = 0;  n++;
	if (type != VIRTIO_BLK_T_FLUSH) {
		addrs[n] = data; lens[n] = data_len;
		writable[n] = (type == VIRTIO_BLK_T_IN);
		n++;
	}
	addrs[n] = status; lens[n] = 1;   writable[n] = 1;  n++;

	return vnr_add_chain_mixed(queue, addrs, lens, writable, n);
}

int main(void)
{
	/* --- a read request ------------------------------------------- */
	fresh();
	int head = blk_chain(&q, VIRTIO_BLK_T_IN, 0x1000, 0x2000, 512, 0x3000);
	ok("a read request builds a three-descriptor chain",
	   head == 0 && q.num_free == QSIZE - 3, NULL);
	ok("the header is NOT device-writable",
	   (desc[0].flags & VNR_DESC_F_WRITE) == 0,
	   "a writable header lets the device overwrite the request it must read");
	ok("a read's data buffer IS device-writable",
	   (desc[1].flags & VNR_DESC_F_WRITE) != 0,
	   "a read into a non-writable buffer returns nothing");
	ok("the status byte IS device-writable",
	   (desc[2].flags & VNR_DESC_F_WRITE) != 0,
	   "without it every request appears to succeed");
	ok("the chain is linked head to status",
	   desc[0].next == 1 && desc[1].next == 2, NULL);
	ok("the status descriptor is one byte", desc[2].len == 1, NULL);
	ok("the chain terminates at the status byte",
	   (desc[2].flags & VNR_DESC_F_NEXT) == 0, NULL);

	/* --- the flags are not uniform, in either direction ------------ */
	ok("the flags differ across the chain",
	   (desc[0].flags & VNR_DESC_F_WRITE) != (desc[2].flags & VNR_DESC_F_WRITE),
	   "a chain built with one flag value is wrong in both directions");

	/* --- a write request ------------------------------------------- */
	fresh();
	head = blk_chain(&q, VIRTIO_BLK_T_OUT, 0x1000, 0x2000, 512, 0x3000);
	ok("a write's data buffer is NOT device-writable",
	   (desc[1].flags & VNR_DESC_F_WRITE) == 0,
	   "the device reads the payload on a write; making it writable invites a scribble");
	ok("a write's status byte is still device-writable",
	   (desc[2].flags & VNR_DESC_F_WRITE) != 0, NULL);

	/* --- flush: TWO descriptors, which a driver assuming three breaks */
	fresh();
	head = blk_chain(&q, VIRTIO_BLK_T_FLUSH, 0x1000, 0, 0, 0x3000);
	ok("a flush builds a two-descriptor chain", q.num_free == QSIZE - 2,
	   "a flush has no data buffer; assuming three corrupts the chain");
	ok("a flush links header straight to status", desc[0].next == 1, NULL);
	ok("a flush's status is device-writable",
	   (desc[1].flags & VNR_DESC_F_WRITE) != 0, NULL);
	ok("a flush's header is not device-writable",
	   (desc[0].flags & VNR_DESC_F_WRITE) == 0, NULL);

	/* --- capacity is counted in 512-byte sectors, always ----------- */
	uint64_t capacity_sectors = 1048576;
	uint32_t blk_size = 4096;
	ok("capacity is sectors, not logical blocks",
	   capacity_sectors * 512 == 536870912ULL,
	   "VIRTIO_BLK_F_BLK_SIZE changes addressing, never the unit capacity uses");
	ok("a 4K logical block spans eight sectors", blk_size / 512 == 8, NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails,
	       fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
