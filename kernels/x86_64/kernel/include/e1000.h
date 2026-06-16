/* Intel e1000 (82540EM) NIC driver — real TX/RX over MMIO + DMA rings.
 * Polled (no IRQs in the seed): the net core pumps e1000_poll(). */
#ifndef AUTON_E1000_H
#define AUTON_E1000_H

#include <stdint.h>
#include "pci.h"

/* Bring up the card: map BAR0, reset, link up, read MAC, init RX/TX rings.
 * Writes the 6-byte MAC into 'mac_out'. Returns 0 on success, negative else. */
int e1000_init(const pci_device_t *dev, uint8_t mac_out[6]);

/* Transmit one Ethernet frame (already framed, incl. dst/src/ethertype).
 * Blocks until the descriptor reports done. Returns 0 on success. */
int e1000_tx(const void *frame, uint16_t len);

/* Poll the RX ring for one received frame. Copies up to 'maxlen' bytes into
 * 'buf' and returns the frame length, or 0 if nothing is available. */
uint16_t e1000_poll(void *buf, uint16_t maxlen);

/* Print TX/RX counters (diagnostics). */
void e1000_debug(void);

#endif /* AUTON_E1000_H */
