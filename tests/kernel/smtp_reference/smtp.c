/* Reference for the SMTP state machine (see include/smtp.h and services/smtp.md).
 * NOT kernel code and NOT shipped. */
#include "smtp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef enum { S_INIT, S_GREETED, S_MAIL, S_RCPT, S_DATA } state_t;

static state_t state;
static char domain[128];
static int rcpt_count;
static int seq;
static smtp_store_t *store;
static uint8_t *body;
static uint32_t body_len, body_cap;
static int oversize;

void smtp_reset(smtp_store_t *s, const char *d, int existing_highest)
{
    state = S_INIT;
    rcpt_count = 0;
    seq = existing_highest;
    store = s;
    free(body);
    body = NULL;
    body_len = body_cap = 0;
    oversize = 0;
    snprintf(domain, sizeof domain, "%s", d ? d : "auton.local");
    if (s) {
        /* Free what a previous run stored before dropping the count that
         * records it. Setting count = 0 without this leaks every message body
         * ever accepted — LeakSanitizer caught it on Linux, where ASan runs
         * LSan by default; on Darwin LSan is unsupported, so the whole suite
         * was green here while leaking 73 bytes a run in CI. */
        for (int i = 0; i < s->count; i++) {
            free(s->body[i]);
            s->body[i] = NULL;
            s->len[i] = 0;
        }
        s->count = 0;
        s->flushes = 0;
        s->writable = 1;
    }
}

int smtp_next_seq(void)
{
    return seq + 1;
}

int smtp_scan_highest(const char *const *names, int n)
{
    int highest = 0;
    for (int i = 0; i < n; i++) {
        /* M0000007.EML */
        if (strlen(names[i]) != 12 || names[i][0] != 'M' ||
            strcmp(names[i] + 8, ".EML") != 0)
            continue;
        int v = atoi(names[i] + 1);
        if (v > highest)
            highest = v;
    }
    return highest;
}

static int reply(char *out, uint32_t cap, const char *text)
{
    uint32_t n = (uint32_t)strlen(text);
    if (n > cap)
        return -1;
    memcpy(out, text, n);
    return (int)n;
}

static int starts(const char *line, uint32_t len, const char *word)
{
    uint32_t n = (uint32_t)strlen(word);
    if (len < n)
        return 0;
    for (uint32_t i = 0; i < n; i++) {
        char c = line[i];
        if (c >= 'a' && c <= 'z')
            c = (char)(c - 'a' + 'A');
        if (c != word[i])
            return 0;
    }
    return 1;
}

/* The domain of an address in <...>, or NULL. */
static const char *domain_of(const char *line, uint32_t len, uint32_t *dlen)
{
    const char *lt = memchr(line, '<', len);
    if (!lt)
        return NULL;
    const char *gt = memchr(lt, '>', len - (uint32_t)(lt - line));
    if (!gt)
        return NULL;
    const char *at = memchr(lt, '@', (uint32_t)(gt - lt));
    if (!at)
        return NULL;                       /* no @: never ours, so never relayed */
    *dlen = (uint32_t)(gt - at - 1);
    return at + 1;
}

static int store_message(void)
{
    if (!store || !store->writable || store->count >= SMTP_MAX_RCPT)
        return -1;
    int i = store->count;
    seq++;
    snprintf(store->name[i], SMTP_NAME_MAX, "/MAIL/M%07d.EML", seq);
    store->body[i] = malloc(body_len ? body_len : 1);
    memcpy(store->body[i], body, body_len);
    store->len[i] = body_len;
    store->count++;
    store->flushes++;                      /* written through before the 250 */
    return 0;
}

int smtp_handle(const char *line, uint32_t len, char *out, uint32_t out_cap)
{
    char buf[256];

    if (state == S_DATA) {
        /* The terminator is a line that is EXACTLY ".", not any line that
         * contains one: a body line with a dot in it would truncate the mail
         * and leave the rest to be read as commands. */
        if (len == 1 && line[0] == '.') {
            state = S_GREETED;
            rcpt_count = 0;
            if (oversize) {
                free(body);
                body = NULL;
                body_len = body_cap = 0;
                oversize = 0;
                /* Nothing is stored: a truncated message that looks like a
                 * message is worse than no message. */
                return reply(out, out_cap, "552 message exceeds 1048576 bytes\r\n");
            }
            if (store_message() < 0)
                return reply(out, out_cap, "452 insufficient storage\r\n");
            snprintf(buf, sizeof buf, "250 OK %d\r\n", seq);
            free(body);
            body = NULL;
            body_len = body_cap = 0;
            return reply(out, out_cap, buf);
        }
        /* Dot-stuffing, removed on the way in (RFC 5321 4.5.2). */
        const char *p = line;
        uint32_t n = len;
        if (n >= 1 && p[0] == '.') {
            p++;
            n--;
        }
        if (body_len + n + 2 > SMTP_MAX_MESSAGE) {
            oversize = 1;                  /* keep reading until the terminator */
            return 0;
        }
        if (body_len + n + 2 > body_cap) {
            body_cap = (body_cap ? body_cap * 2 : 4096) + n + 2;
            body = realloc(body, body_cap);
        }
        memcpy(body + body_len, p, n);
        body_len += n;
        body[body_len++] = '\r';
        body[body_len++] = '\n';
        return 0;
    }

    if (len > SMTP_MAX_LINE)
        return reply(out, out_cap, "500 line too long\r\n");

    if (starts(line, len, "EHLO") || starts(line, len, "HELO")) {
        state = S_GREETED;
        rcpt_count = 0;
        snprintf(buf, sizeof buf, "250 %s\r\n", domain);
        return reply(out, out_cap, buf);
    }
    if (starts(line, len, "QUIT")) {
        state = S_INIT;
        rcpt_count = 0;
        free(body);                        /* a partial message is discarded */
        body = NULL;
        body_len = body_cap = 0;
        return reply(out, out_cap, "221 Bye\r\n");
    }
    if (starts(line, len, "NOOP"))
        return reply(out, out_cap, "250 OK\r\n");
    if (starts(line, len, "RSET")) {
        if (state != S_INIT)
            state = S_GREETED;
        rcpt_count = 0;
        free(body);
        body = NULL;
        body_len = body_cap = 0;
        return reply(out, out_cap, "250 OK\r\n");
    }
    if (starts(line, len, "MAIL FROM:")) {
        if (state == S_INIT)
            return reply(out, out_cap, "503 bad sequence of commands\r\n");
        if (state == S_MAIL || state == S_RCPT)
            return reply(out, out_cap, "503 bad sequence of commands\r\n");
        state = S_MAIL;
        rcpt_count = 0;
        return reply(out, out_cap, "250 OK\r\n");
    }
    if (starts(line, len, "RCPT TO:")) {
        if (state != S_MAIL && state != S_RCPT)
            return reply(out, out_cap, "503 bad sequence of commands\r\n");
        uint32_t dlen = 0;
        const char *d = domain_of(line, len, &dlen);
        if (!d || dlen != strlen(domain) || strncasecmp(d, domain, dlen) != 0)
            return reply(out, out_cap, "550 relay not permitted\r\n");
        if (rcpt_count >= SMTP_MAX_RCPT)
            return reply(out, out_cap, "452 too many recipients\r\n");
        rcpt_count++;
        state = S_RCPT;
        return reply(out, out_cap, "250 OK\r\n");
    }
    if (starts(line, len, "DATA")) {
        if (state != S_RCPT)
            return reply(out, out_cap, "503 bad sequence of commands\r\n");
        state = S_DATA;
        return reply(out, out_cap, "354 End data with <CR><LF>.<CR><LF>\r\n");
    }
    return reply(out, out_cap, "500 command not recognized\r\n");
}
