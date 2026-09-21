/* See include/virtio_ref.h. NOT kernel code and NOT shipped. */
#include "virtio_ref.h"

void vnr_queue_init(vnr_queue_t *q, uint16_t size, vnr_desc_t *desc,
                    uint16_t *avail_ring, uint16_t *used_ring)
{
	q->size = size;
	q->desc = desc;
	q->avail_ring = avail_ring;
	q->used_ring = used_ring;
	q->avail_idx = 0;
	q->used_idx = 0;
	q->free_head = 0;
	q->num_free = size;

	/* The free list threads through `next`. The last descriptor points at
	 * itself rather than at 0: a wrap here would silently make descriptor 0
	 * reachable twice, which is a double-free of a DMA buffer. */
	for (uint16_t i = 0; i < size; i++)
		desc[i].next = (uint16_t)((i + 1u < size) ? i + 1u : i);
}

int vnr_add_chain(vnr_queue_t *q, const uint64_t *addrs, const uint32_t *lens,
                  uint16_t n, int device_writable)
{
	int flags[VNR_MAX_CHAIN];

	if (n == 0 || n > VNR_MAX_CHAIN)
		return -1;
	for (uint16_t i = 0; i < n; i++)
		flags[i] = device_writable;
	return vnr_add_chain_mixed(q, addrs, lens, flags, n);
}

int vnr_add_chain_mixed(vnr_queue_t *q, const uint64_t *addrs,
                        const uint32_t *lens, const int *writable, uint16_t n)
{
	if (n == 0 || n > q->num_free)
		return -1;

	uint16_t head = q->free_head;
	uint16_t prev = head;

	for (uint16_t i = 0; i < n; i++) {
		uint16_t cur = q->free_head;
		q->desc[cur].addr = addrs[i];
		q->desc[cur].len = lens[i];
		q->desc[cur].flags = (uint16_t)(writable[i] ? VNR_DESC_F_WRITE : 0u);
		if (i + 1u < n)
			q->desc[cur].flags |= VNR_DESC_F_NEXT;
		prev = cur;
		q->free_head = q->desc[cur].next;
		q->num_free--;
	}
	/* The tail's NEXT is cleared above by not setting it; `next` still holds
	 * a stale free-list link, which the device must never follow. */
	q->desc[prev].next = 0;

	/* Publish. The available index is free-running and only masked when it is
	 * used to address the ring — masking the stored index instead is the
	 * classic wrap bug, and it silently overwrites live entries after 65536
	 * packets rather than failing. */
	q->avail_ring[vnr_ring_slot(q->avail_idx, q->size)] = head;
	q->avail_idx++;
	return (int)head;
}

int vnr_free_chain(vnr_queue_t *q, uint16_t head)
{
	int freed = 0;
	uint16_t cur = head;

	for (;;) {
		uint16_t next = q->desc[cur].next;
		int more = (q->desc[cur].flags & VNR_DESC_F_NEXT) != 0;
		q->desc[cur].next = q->free_head;
		q->free_head = cur;
		q->num_free++;
		freed++;
		if (!more)
			break;
		cur = next;
	}
	return freed;
}
