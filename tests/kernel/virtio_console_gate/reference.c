/* Human reference for the V8 gate suite, so the suite is proved before it
 * judges anyone. See include/virtio_console.h. NOT kernel code. */
#include "virtio_console.h"

#define BIT(n) (1ULL << (n))

uint64_t vcon_negotiate(uint64_t offered)
{
	return offered & (BIT(VIRTIO_F_VERSION_1) | BIT(VIRTIO_CONSOLE_F_SIZE));
}

static int post_one(vnr_queue_t *q, uint64_t buf, uint32_t len, int writable)
{
	if (len == 0)
		return -1;
	return vnr_add_chain(q, &buf, &len, 1, writable);
}

int vcon_post_rx(vnr_queue_t *q, uint64_t buf, uint32_t len)
{
	return post_one(q, buf, len, 1);
}

int vcon_post_tx(vnr_queue_t *q, uint64_t buf, uint32_t len)
{
	return post_one(q, buf, len, 0);
}

uint32_t vcon_rx_complete(vnr_queue_t *q, uint16_t head, uint32_t used_len)
{
	uint32_t posted = q->desc[head].len;
	vnr_free_chain(q, head);
	return used_len < posted ? used_len : posted;
}

int vcon_read_size(const uint8_t cfg[VCON_CONFIG_LEN], uint64_t negotiated,
                   uint16_t *cols, uint16_t *rows)
{
	if (!(negotiated & BIT(VIRTIO_CONSOLE_F_SIZE)))
		return -1;
	*cols = (uint16_t)(cfg[0] | (cfg[1] << 8));
	*rows = (uint16_t)(cfg[2] | (cfg[3] << 8));
	return 0;
}
