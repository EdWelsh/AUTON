/* The V8 gate suite: VirtIO Console (VIRTIO 1.2 §5.3), single port.
 *
 * Written by a person and frozen before the agent's run, so it judges the
 * agent's reference (tests/kernel/virtio_console_reference.c in its tree)
 * rather than being shaped by it. Proved first against virtio_console_gate/.
 *
 * What it guards is direction. §5.3.6.1: a device-readable buffer in a
 * receiveq, or a device-writable one in a transmitq, is forbidden: the first
 * gives the device nowhere to put input, the second lets it scribble on
 * memory the driver only meant to send. And the device's used length is never
 * trusted past the buffer it was handed.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "virtio_console.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-62s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

#define QSIZE 4
#define BIT(n) (1ULL << (n))

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
	/* --- §5.3.2: queue numbering ------------------------------------- */
	ok("port 0's receiveq is queue 0", VCON_RECEIVEQ == 0, NULL);
	ok("port 0's transmitq is queue 1", VCON_TRANSMITQ == 1, NULL);

	/* --- feature negotiation ------------------------------------------ */
	uint64_t all = BIT(VIRTIO_F_VERSION_1) | BIT(VIRTIO_CONSOLE_F_SIZE) |
	               BIT(VIRTIO_CONSOLE_F_MULTIPORT) | BIT(VIRTIO_CONSOLE_F_EMERG_WRITE) |
	               BIT(5) | BIT(40);
	uint64_t got = vcon_negotiate(all);
	ok("VERSION_1 is accepted when offered", (got & BIT(VIRTIO_F_VERSION_1)) != 0, NULL);
	ok("CONSOLE_F_SIZE is accepted when offered", (got & BIT(VIRTIO_CONSOLE_F_SIZE)) != 0, NULL);
	ok("MULTIPORT is never accepted (single port)",
	   (got & BIT(VIRTIO_CONSOLE_F_MULTIPORT)) == 0,
	   "accepting it obliges the control queues and DEVICE_READY (§5.3.6.2.2)");
	ok("EMERG_WRITE is not accepted", (got & BIT(VIRTIO_CONSOLE_F_EMERG_WRITE)) == 0, NULL);
	ok("unknown feature bits are not accepted", (got & (BIT(5) | BIT(40))) == 0, NULL);
	ok("nothing is accepted that was not offered",
	   (vcon_negotiate(BIT(VIRTIO_F_VERSION_1)) & ~BIT(VIRTIO_F_VERSION_1)) == 0 &&
	   vcon_negotiate(0) == 0, NULL);

	/* --- receive buffers ---------------------------------------------- */
	fresh();
	int h = vcon_post_rx(&q, 0x1000, 64);
	ok("a receive buffer is posted", h >= 0 && h < QSIZE, NULL);
	ok("a receive buffer IS device-writable",
	   h >= 0 && (desc[h].flags & VNR_DESC_F_WRITE) != 0,
	   "§5.3.6.1: a device-readable buffer in a receiveq is forbidden");
	ok("a receive buffer is one descriptor, no NEXT",
	   h >= 0 && (desc[h].flags & VNR_DESC_F_NEXT) == 0 && q.num_free == QSIZE - 1, NULL);
	ok("the descriptor carries the buffer's address and length",
	   h >= 0 && desc[h].addr == 0x1000 && desc[h].len == 64, NULL);
	ok("the buffer is published in the available ring",
	   h >= 0 && q.avail_idx == 1 && avail[0] == (uint16_t)h, NULL);

	/* --- transmit buffers --------------------------------------------- */
	fresh();
	h = vcon_post_tx(&q, 0x2000, 5);
	ok("a transmit buffer is NOT device-writable",
	   h >= 0 && (desc[h].flags & VNR_DESC_F_WRITE) == 0,
	   "§5.3.6.1: a device-writable buffer in a transmitq is forbidden");
	ok("a transmit buffer is one descriptor of the right length",
	   h >= 0 && (desc[h].flags & VNR_DESC_F_NEXT) == 0 && desc[h].len == 5, NULL);

	/* --- refusals ----------------------------------------------------- */
	fresh();
	ok("a zero-length receive buffer is refused", vcon_post_rx(&q, 0x1000, 0) == -1, NULL);
	ok("a zero-length transmit buffer is refused", vcon_post_tx(&q, 0x1000, 0) == -1, NULL);
	ok("a refusal consumes no descriptor", q.num_free == QSIZE && q.avail_idx == 0, NULL);
	for (int i = 0; i < QSIZE; i++)
		vcon_post_rx(&q, 0x1000 + 0x100u * (unsigned)i, 64);
	ok("a full queue refuses another buffer", vcon_post_rx(&q, 0x9000, 64) == -1, NULL);

	/* --- the used length is never trusted past the buffer -------------- */
	fresh();
	h = vcon_post_rx(&q, 0x1000, 64);
	ok("a short used length is the input length",
	   h >= 0 && vcon_rx_complete(&q, (uint16_t)h, 10) == 10, NULL);
	ok("completion returns the descriptor", q.num_free == QSIZE, NULL);
	h = vcon_post_rx(&q, 0x1000, 64);
	ok("a used length past the buffer is clamped to it",
	   h >= 0 && vcon_rx_complete(&q, (uint16_t)h, 4096) == 64,
	   "trusting it reads past the buffer the device was given");

	/* --- the available index wraps; the slot is masked ----------------- */
	fresh();
	q.avail_idx = 65535;
	h = vcon_post_rx(&q, 0x1000, 64);
	ok("at avail_idx 65535 the buffer lands in slot 3",
	   h >= 0 && avail[3] == (uint16_t)h, NULL);
	ok("and the free-running index wraps to 0", q.avail_idx == 0, NULL);

	/* --- §5.3.4 configuration: size ----------------------------------- */
	uint8_t cfg[VCON_CONFIG_LEN] = {0x02, 0x01, 0x19, 0x00};   /* cols 258, rows 25 */
	uint16_t cols = 7, rows = 7;
	ok("with SIZE negotiated, cols and rows are read",
	   vcon_read_size(cfg, BIT(VIRTIO_CONSOLE_F_SIZE), &cols, &rows) == 0, NULL);
	ok("they are little-endian", cols == 258 && rows == 25,
	   "0x0102 read big-endian is 513");
	cols = rows = 7;
	ok("without SIZE negotiated, the fields are not valid",
	   vcon_read_size(cfg, BIT(VIRTIO_F_VERSION_1), &cols, &rows) == -1, NULL);
	ok("and neither output is touched", cols == 7 && rows == 7, NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
