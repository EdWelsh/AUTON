/* The SMTP state machine specified in agent/kernel_spec/services/smtp.md.
 * Host-provable: the command sequence, the limits, relay refusal, dot-stuffing
 * and sequence recovery. NOT kernel code and NOT shipped. */
#ifndef AUTON_SMTP_H
#define AUTON_SMTP_H

#include <stdint.h>

#define SMTP_MAX_MESSAGE    1048576u
#define SMTP_MAX_RCPT       16
#define SMTP_MAX_LINE       1000u
#define SMTP_NAME_MAX       32

/* Where a stored message goes. The host suite keeps these in memory; a kernel
 * writes them to /MAIL/ on FAT32. */
typedef struct smtp_store {
	char     name[SMTP_MAX_RCPT][SMTP_NAME_MAX];   /* file names, in order */
	uint8_t *body[SMTP_MAX_RCPT];
	uint32_t len[SMTP_MAX_RCPT];
	int      count;
	int      flushes;          /* a 250 is owed only after a flush */
	int      writable;         /* 0 makes a store fail, as a full volume would */
} smtp_store_t;

void smtp_reset(smtp_store_t *store, const char *domain, int existing_highest);

/* One line in (without its CRLF), one reply out. Returns the reply length, or
 * 0 when the line was body data that needs no reply. */
int  smtp_handle(const char *line, uint32_t len, char *out, uint32_t out_cap);

/* The next sequence number, as recovered by scanning the directory. */
int  smtp_next_seq(void);

/* The highest sequence in a directory listing, 0 when it holds no messages.
 * A counter that restarts at 1 overwrites the mail that survived the reboot. */
int  smtp_scan_highest(const char *const *names, int n);

#endif
