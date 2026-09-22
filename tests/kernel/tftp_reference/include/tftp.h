/* The TFTP service interface, exactly as agent/kernel_spec/services/tftp.md
 * "Interface (kernel/include/tftp.h)" and "Data Structures" state it. */
#ifndef AUTON_TFTP_H
#define AUTON_TFTP_H
#include <stdint.h>
#include "net.h"

#define TFTP_FILE_PATTERN_LEN 1300
#define TFTP_FILE_EXACT_LEN   1024

#define TFTP_BLOCK        512
#define TFTP_TIMEOUT_MS   1000
#define TFTP_MAX_RETRIES  5

typedef struct {
    uint8_t   active;
    ipv4_t    peer_ip;
    uint16_t  peer_tid;
    uint16_t  our_tid;
    const uint8_t *file;
    uint32_t  file_len;
    uint16_t  block;
    uint32_t  sent_at_ms;
    uint8_t   retries;
} tftp_xfer_t;

typedef struct {
    ipv4_t   dst_ip;
    uint16_t dst_port;
    uint16_t src_port;
    uint8_t  payload[4 + TFTP_BLOCK];
    uint32_t len;
} tftp_reply_t;

void tftp_server_init(void);
void tftp_serve(void);
void tftp_handle(ipv4_t src, uint16_t sport, uint16_t dport,
                 const uint8_t *payload, uint32_t len, uint32_t now_ms,
                 tftp_reply_t *out);
void tftp_tick(uint32_t now_ms, tftp_reply_t *out);

#endif
