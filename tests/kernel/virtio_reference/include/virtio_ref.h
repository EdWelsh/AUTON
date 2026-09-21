/* Reference virtqueue arithmetic, shared by every VirtIO driver specified in
 * agent/kernel_spec/subsystems/drivers.md.
 *
 * Written for VirtIO Network (V5) and renamed when VirtIO Block (V6) became its
 * second consumer. A shared component named after one of its consumers is how
 * the second one ends up with a copy.
 *
 * NOT kernel code and NOT shipped. It exists so the virtio host tests can be proved
 * correct, and so the ring index arithmetic in the specification is executable
 * rather than prose.
 *
 * Why this part and not the rest: the descriptor chain and the available/used
 * ring indices are where a DMA bug lives, and they can be proved on a host. A
 * register poke cannot be — under emulation a driver is verified against QEMU's
 * model of the device, not the device, which is the gap
 * agent/hardware/CONFORMANCE-HARDWARE.md records for silicon and which applies
 * here with full force.
 */
#ifndef VIRTIO_REF_H
#define VIRTIO_REF_H

#include <stdint.h>

#define VNR_DESC_F_NEXT   1u
#define VNR_DESC_F_WRITE  2u

/* The longest chain any specified VirtIO driver builds: a block request is
 * header + data + status. Bounded so the uniform-flag wrapper needs no
 * allocation. */
#define VNR_MAX_CHAIN     8

/* Mirrors virtq_desc_t in drivers.md. Not redefined there — referenced. */
typedef struct vnr_desc {
	uint64_t addr;
	uint32_t len;
	uint16_t flags;
	uint16_t next;
} vnr_desc_t;

typedef struct vnr_queue {
	uint16_t size;          /* must be a power of two, VIRTIO 1.2 §2.6 */
	vnr_desc_t *desc;
	uint16_t *avail_ring;
	uint16_t avail_idx;     /* the driver's own copy; free-running */
	uint16_t *used_ring;
	uint16_t used_idx;      /* last used index the driver has consumed */
	uint16_t free_head;
	uint16_t num_free;
} vnr_queue_t;

void vnr_queue_init(vnr_queue_t *q, uint16_t size, vnr_desc_t *desc,
                    uint16_t *avail_ring, uint16_t *used_ring);

/* Build a descriptor chain over `n` buffers and publish its head.
 * Returns the head index, or -1 when the queue lacks free descriptors. */
int vnr_add_chain(vnr_queue_t *q, const uint64_t *addrs, const uint32_t *lens,
                  uint16_t n, int device_writable);

/* As above, but with a per-descriptor writable flag.
 *
 * Added when VirtIO Block became the second consumer. The uniform-flag form
 * above was written for the network driver, where every buffer in a chain runs
 * the same direction — and a block request does not: its header is read-only,
 * its status byte is device-writable, and its data buffer depends on the
 * request type. A chain built with one flag value is wrong in both directions,
 * so the shared reference has to be able to express the difference. */
int vnr_add_chain_mixed(vnr_queue_t *q, const uint64_t *addrs,
                        const uint32_t *lens, const int *writable, uint16_t n);

/* Reclaim a chain the device has finished with, returning descriptors to the
 * free list. Returns the number of descriptors freed. */
int vnr_free_chain(vnr_queue_t *q, uint16_t head);

/* Where a free-running index lands in a ring of `size` entries.
 * VIRTIO 1.2 §2.7.6: the index wraps naturally at 65536 and is masked by the
 * queue size, which is why the size must be a power of two. */
static inline uint16_t vnr_ring_slot(uint16_t idx, uint16_t size)
{
	return (uint16_t)(idx & (uint16_t)(size - 1u));
}

#endif /* VIRTIO_REF_H */
