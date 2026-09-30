/* The play-doom host-test interface (agent/kernel_spec/services/play-doom.md,
 * "Host-test interface"). The reference implementation's header; a generated
 * tree supplies its own kernel/include/play_doom.h, which must declare these. */
#ifndef PLAY_DOOM_H
#define PLAY_DOOM_H

#include <stddef.h>
#include <stdint.h>

#define DOOM_RESX 640
#define DOOM_RESY 400
#define DOOM_KEYQ 16

int      play_doom_key_scancode(uint8_t byte);
uint32_t play_doom_keys_dropped(void);
void     play_doom_keys_reset(void);
int      DG_GetKey(int *pressed, unsigned char *key);

void play_doom_blit(const uint32_t *src, uint8_t *fb, uint32_t pitch,
                    uint32_t fb_w, uint32_t fb_h);

size_t play_doom_wad_read(const uint8_t *base, size_t size, uint32_t offset,
                          void *buf, size_t len);

#endif
