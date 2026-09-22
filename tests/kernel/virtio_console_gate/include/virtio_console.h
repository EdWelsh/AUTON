/* The interface the V8 gate suite tests (driver PRD V8, w13). Frozen before the
 * agent's run: an agent-written reference must provide exactly these.
 *
 * VIRTIO 1.2 §5.3, single port only (VIRTIO_CONSOLE_F_MULTIPORT is never
 * accepted). Ring arithmetic is the shared tests/kernel/virtio_reference/.
 * NOT kernel code and NOT shipped. */
#ifndef AUTON_VIRTIO_CONSOLE_H
#define AUTON_VIRTIO_CONSOLE_H

#include <stdint.h>
#include "virtio_ref.h"

/* §5.3.3 feature bits, and the device-independent VERSION_1 (§6). */
#define VIRTIO_CONSOLE_F_SIZE        0
#define VIRTIO_CONSOLE_F_MULTIPORT   1
#define VIRTIO_CONSOLE_F_EMERG_WRITE 2
#define VIRTIO_F_VERSION_1           32

/* §5.3.2: port 0's queues always exist, and are these. */
#define VCON_RECEIVEQ   0
#define VCON_TRANSMITQ  1

/* §5.3.4: struct virtio_console_config, little-endian (not legacy). */
#define VCON_CONFIG_LEN 12

/* The features the driver accepts from those offered: VERSION_1 and
 * CONSOLE_F_SIZE when offered, nothing else. Always a subset of `offered`. */
uint64_t vcon_negotiate(uint64_t offered);

/* Post one receive buffer on port 0's receiveq: a single device-WRITABLE
 * descriptor (§5.3.6.1 forbids a device-readable one there). Returns the head
 * index, or -1 when len is 0 or the queue has no free descriptor. */
int vcon_post_rx(vnr_queue_t *q, uint64_t buf, uint32_t len);

/* Post one transmit buffer on port 0's transmitq: a single device-READABLE
 * descriptor (§5.3.6.1 forbids a device-writable one there). Same returns. */
int vcon_post_tx(vnr_queue_t *q, uint64_t buf, uint32_t len);

/* A used receive buffer came back: free its descriptor and return how many
 * bytes are input. The device's used length is never trusted past the buffer
 * it was given: the result is min(used_len, the posted length). */
uint32_t vcon_rx_complete(vnr_queue_t *q, uint16_t head, uint32_t used_len);

/* §5.3.5 step 2: cols and rows are valid only when CONSOLE_F_SIZE was
 * negotiated. Returns 0 and fills both, or -1 and touches neither. */
int vcon_read_size(const uint8_t cfg[VCON_CONFIG_LEN], uint64_t negotiated,
                   uint16_t *cols, uint16_t *rows);

#endif
