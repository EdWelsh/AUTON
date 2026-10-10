---
service: play-doom
requires: [boot, allocator, pci, terminal, scoped, framebuffer, input, module-asset, timer]
excludes: [net, fs, sched, ipc]
entry: play_doom_serve
markers:
  - "[FB] mode set"
  - "[INPUT] keyboard ready"
  - "[DOOM] frame 1"
assets: [doom.wad]
---

# Play Doom Service Specification

## Overview

Boots straight into Doom. One engine, one WAD handed in by the loader, one loop drawing frames
to the framebuffer GRUB configured. No network, no filesystem, no scheduler, no second program.
It is the PRD set's headline intent (`AUTON train "I want to play Doom" --output ./Doom`), and it
is the right first consumer image because it needs **no storage and no network**. It tests
`excludes` in the direction opposite to `host-repo`.

The engine is not specified here. It is **doomgeneric**, a portable fork of id Software's
released Doom source whose whole platform contract is six functions (`doomgeneric.h`). This
spec says what the image does to satisfy that contract with the capabilities it requires,
and nothing about how Doom plays.

Scope boundary: one player, no sound, no music, no network game, no savegames (all need a
device or `fs` the image excludes). The engine's sound and network modules are compiled out,
not stubbed to succeed silently.

**Normative references**

| Reference | Governs |
|---|---|
| doomgeneric `doomgeneric.h` (github.com/ozkl/doomgeneric) | The six platform functions and `DG_ScreenBuffer` |
| Multiboot2 Specification §3.6.6 (modules) and §3.6.12 (framebuffer info) | How the WAD and the framebuffer arrive (via `subsystems/boot.md`) |
| `drivers/framebuffer.md`, `drivers/ps2-keyboard.md` | The two driver records this image consumes |

doomgeneric is **not inventoried** in `agent/hardware/vendors.yaml`, and it is GPL-2.0 source.
See *Licence* below. That is a blocker, not a footnote.

## Assumptions carried from the intent

- The user owns a WAD and supplies its path at build time. None is committed or fetched.
  **The target is the original 1993 DOOM**: the owner chose the id Software shareware
  `DOOM1.WAD` v1.9 (4,196,020 bytes, MD5 `f0cefca49926d00903cf57551d901abe`, an `IWAD`) for
  validation, kept locally at `.cache/assets/DOOM1.WAD` and never committed. doomgeneric
  identifies it as shareware Doom and runs Episode 1.
- A PS/2 keyboard is present. This excludes microVMs, whose i8042 is vestigial
  (`targets/firecracker.md`).
- GRUB configured a linear 32-bpp framebuffer (Multiboot2 framebuffer tag, type 1 = RGB).

## Data Structures

### Screen

```c
/* doomgeneric renders into DG_ScreenBuffer: DOOMGENERIC_RESX x DOOMGENERIC_RESY,
 * one uint32_t (0x00RRGGBB) per pixel, no padding. The platform copies it out. */
#define DOOM_RESX 640
#define DOOM_RESY 400
```

The source rows are `DOOM_RESX` pixels wide. The destination rows are **`pitch` bytes** wide, from
the framebuffer tag, and pitch is not `width * 4` (`drivers/framebuffer.md`). The copy centres
the image and advances the destination by `pitch`, never by a computed stride.

### Key queue

```c
#define DOOM_KEYQ 16
typedef struct {
    uint8_t  pressed;   /* 1 = make, 0 = break */
    uint8_t  key;       /* doomgeneric key code (doomkeys.h), already translated */
} doom_key_t;
/* Single-producer ring filled by the keyboard IRQ, drained by DG_GetKey. */
```

Scancodes are translated to Doom key codes **once**, at the IRQ, using the set-1 table in
`drivers/scancodes.yaml`. A full queue drops the newest event and counts it. It never blocks the
IRQ.

## Interface (`kernel/include/play_doom.h`)

```c
/* The single serve loop named in the front-matter. Never returns. */
void play_doom_serve(void);

/* doomgeneric's platform contract, implemented by this service. */
void     DG_Init(void);
void     DG_DrawFrame(void);
void     DG_SleepMs(uint32_t ms);
uint32_t DG_GetTicksMs(void);
int      DG_GetKey(int *pressed, unsigned char *key);  /* 1 = event returned, 0 = queue empty */
void     DG_SetWindowTitle(const char *title);          /* no window: logged, otherwise a no-op */
```

## Host-test interface (REQUIRED)

The arithmetic a Doom image can get wrong without the game failing outright (a sheared frame, a
dead key, a WAD read one byte past the module) lives in **`kernel/services/play_doom/platform_pure.c`**.
That file includes only `<stdint.h>`, `<stddef.h>` and `play_doom.h`, calls nothing else in the
kernel, and is compiled on the host by `tests/kernel/run_play_doom_test.sh`. The suite was frozen
before any generation run. `dg_platform.c` and `w_file_module.c` call these functions; they do
not re-implement them.

```c
/* The IRQ side of the key queue: feed ONE raw set-1 byte as read from port 0x60.
 * Handles the 0xE0 prefix (remembered for the next byte) and the release bit
 * (0x80). Returns 1 if an event was queued, 0 if the byte was a prefix, was
 * unmapped, or was dropped because the queue was full. */
int      play_doom_key_scancode(uint8_t byte);
uint32_t play_doom_keys_dropped(void);   /* events dropped on a full queue, since boot */
void     play_doom_keys_reset(void);     /* empties the queue, zeroes the count, forgets E0 */
/* DG_GetKey (above) drains the same queue, oldest first. */

/* Copy a DOOM_RESX x DOOM_RESY frame into a 32-bpp linear framebuffer of fb_w x fb_h
 * pixels and `pitch` bytes per row, centred: x0 = (fb_w - DOOM_RESX) / 2,
 * y0 = (fb_h - DOOM_RESY) / 2. Rows advance by `pitch`, never by fb_w * 4. Pixels
 * outside the centred rectangle are not written. The caller has checked
 * fb_w >= DOOM_RESX and fb_h >= DOOM_RESY. */
void play_doom_blit(const uint32_t *src, uint8_t *fb, uint32_t pitch,
                    uint32_t fb_w, uint32_t fb_h);

/* The memory-backed WAD read: copy up to `len` bytes starting at `offset` of the
 * module [base, base + size). Returns the count copied: `len`, or fewer at the end
 * of the module, or 0 when offset >= size. Never reads outside the module. */
size_t play_doom_wad_read(const uint8_t *base, size_t size, uint32_t offset,
                          void *buf, size_t len);
```

### Key translation (normative)

Set-1 make codes to doomgeneric key codes (`doomkeys.h`). A release is the make code with bit 7
set, and it produces the same key with `pressed = 0`. `E0`-prefixed codes are the extended keys.
The bindings follow doomgeneric's own reference port (`doomgeneric_sdl.c`): Ctrl fires, Space
uses, Shift runs. Anything not in this table is ignored, never queued.

| Set-1 | Key | Doom key | Value |
|---|---|---|---|
| `01` | Escape | `KEY_ESCAPE` | 27 |
| `1C` | Enter | `KEY_ENTER` | 13 |
| `0F` | Tab | `KEY_TAB` | 9 |
| `0E` | Backspace | `KEY_BACKSPACE` | 0x7f |
| `1D` / `E0 1D` | Ctrl (left / right) | `KEY_FIRE` | 0xa3 |
| `39` | Space | `KEY_USE` | 0xa2 |
| `2A` / `36` | Shift (left / right) | `KEY_RSHIFT` | 0xb6 |
| `38` / `E0 38` | Alt (left / right) | `KEY_RALT` | 0xb8 |
| `E0 48` | Up | `KEY_UPARROW` | 0xad |
| `E0 50` | Down | `KEY_DOWNARROW` | 0xaf |
| `E0 4B` | Left | `KEY_LEFTARROW` | 0xac |
| `E0 4D` | Right | `KEY_RIGHTARROW` | 0xae |
| printable (`drivers/scancodes.yaml`) | letters and digits | the unshifted character, lower case | ASCII |

`48`, `50`, `4B` and `4D` **without** `E0` are the numeric keypad and are ignored. A driver that
drops the prefix turns every arrow into a keypad press.

## Behavior

### Serve loop

1. Locate the WAD: `pkg_module_asset("doom.wad")` (`subsystems/pkg.md`, *Module assets*). If it
   is absent, log `[DOOM] no WAD module — pass one with module2` and halt. **Never** fall back to
   a built-in or downloaded WAD.
2. `DG_Init()`: verify the framebuffer tag is present, 32 bpp and at least `DOOM_RESX × DOOM_RESY`,
   then clear it and emit `[FB] mode set`. Enable the keyboard IRQ and emit
   `[INPUT] keyboard ready`. Any failure is logged by name and halts. A missing framebuffer is not
   degraded to text mode.
3. `doomgeneric_Create(argc, argv)` with `argv = {"doom", "-iwad", "doom.wad"}`.
4. Loop `doomgeneric_Tick()` forever. After the first `DG_DrawFrame` completes, emit
   `[DOOM] frame 1` once.

### WAD access

The engine reads its WAD through `w_file.h`'s `wad_file_class_t`. This image provides a
**memory-backed class** reading from the module's physical range, identity-mapped as
`subsystems/boot.md` leaves it. `Read(offset, len)` is bounds-checked against
`end - start` and returns a short count past the end, as `w_file_stdc.c` does on EOF.
`w_file_stdc.c` is compiled out; it needs `fopen`, and the image excludes `fs`.

The module range is already reserved from the PMM (`boot.md` §*Boot-module tags*), so the WAD is
never handed out as free memory. The engine only reads it.

### Engine surface (measured)

The engine is built for a hosted C library, and this image has none. What it needs was
**measured, not read from documentation**: every engine unit was compiled once and the symbols no
engine unit defines were listed; the result is
[`reference/doom-surface.yaml`](../reference/doom-surface.yaml) (49 names, six of them the `DG_*`
functions). `libc_min.c` provides exactly the non-`DG_` names, built on the kernel's allocator
and `kprintf`, and no more: a symbol not in that file's list is not provided.

- **Memory and strings** (`malloc` family, `mem*`, `str*`, `*casecmp`, `bzero`, `atoi`, `atof`,
  `toupper`) and **formatting** (`printf`, `snprintf`, `vsnprintf`, `vfprintf`, `fprintf`,
  `sscanf`, `puts`, `putchar`): real implementations; `printf`-family output goes to the serial
  console, `stdout` and `stderr` being handles to it.
- **Files** (`fopen` … `system`): this image excludes `fs`, so these **fail closed**: `fopen`
  returns `NULL`, `mkdir`/`remove`/`rename`/`system` return -1, `fread`/`fwrite` on the two
  console handles only. The engine copes: no config file means defaults, no savegame directory
  means no saves. They are never implemented to succeed, which would be an `fs` the image does
  not have. The WAD does not come through them (*WAD access*).
- **Sound**: leave `FEATURE_SOUND` undefined. The engine's own `dummy.c` then supplies the
  `I_*Sound`/`I_*Music` functions, so nothing in `i_sound.c` links against a mixer.
- `exit` logs and halts. `errno` is one integer.

A build that needs a name beyond the measured list is a finding about the measurement, not a
licence to grow the file.

### Timing

`DG_GetTicksMs` returns milliseconds since boot from the `timer` capability. `DG_SleepMs` halts
(`hlt`) until the tick passes the deadline. It does not spin. Doom runs its game logic at 35 Hz
off these two calls, so a clock running at the wrong rate makes the game play at the wrong speed
rather than failing.

### Edge cases

| Case | Behaviour |
|---|---|
| No `doom.wad` module | log, halt; step 1 |
| Framebuffer not 32 bpp, or smaller than 640×400 | log both geometries, halt |
| Framebuffer larger than 640×400 | centre; the border stays black |
| Key queue overflow | drop the newest event, count it; the count is logged on the next frame |
| Unknown scancode | ignored, not queued |
| WAD read past end | short read; the engine reports the lump error itself |

## Files

| File | Purpose |
|---|---|
| `kernel/services/play_doom/serve.c` | `play_doom_serve`, the WAD lookup, the markers |
| `kernel/services/play_doom/platform_pure.c` | the key queue, translation, blit and WAD read (*Host-test interface*) |
| `kernel/services/play_doom/dg_platform.c` | five of the six `DG_*` functions (`DG_Init`, `DG_DrawFrame`, `DG_SleepMs`, `DG_GetTicksMs`, `DG_SetWindowTitle`); **`DG_GetKey` is defined in `platform_pure.c`**, because the frozen host suite calls it there |
| `kernel/services/play_doom/w_file_module.c` | the memory-backed `wad_file_class_t` |
| `kernel/services/play_doom/libc_min.c` | the libc functions the engine calls (*Engine surface*), and nothing else |
| `kernel/include/play_doom.h` | the interface above |
| `third_party/doomgeneric/` | the engine. **Not in this repo.** See *Licence* |

## Dependencies

Capabilities, per the front-matter: boot, allocator, pci, terminal, scoped, framebuffer, input,
module-asset, timer.

- `framebuffer`: the linear buffer and its `pitch` (`drivers/framebuffer.md`).
- `input`: the i8042 keyboard, accepted without a specification (`drivers/ps2-keyboard.md`).
- `module-asset`: the WAD (`subsystems/pkg.md`, *Module assets*).
- `timer`: `DG_GetTicksMs` and `DG_SleepMs`.
- `allocator`: the engine's zone memory (`Z_Init` takes one contiguous block).

Explicitly excluded: net, fs, sched, ipc. The engine's network and sound modules are compiled out.
A build that links `i_sound.c` or `net_*.c` is a leakage failure.

## Licence

doomgeneric, like the id Software source it forks, is **GPL-2.0**. This repository is distributed
under a source-available licence (`LICENSE.md`). `drivers/licences.yaml` says a GPL-2.0 port is
`depends-on-use`: whether linking it creates a derivative work of the whole image, and what that
obliges, *"is exactly the question this table refuses to answer … a human must decide."*

So **this spec is implementable and the image is not yet distributable**. Until a person records
that decision, the engine stays out of the tree, and a generated image containing it must not be
published. The WAD is a separate matter. Commercial WADs are copyrighted and never committed.
`freedoom` WADs are BSD-licensed, and the user may supply one.

## Acceptance Criteria

1. All 3 markers appear on the serial console, in order.
2. With no `doom.wad` module the image logs the absence and halts. It emits neither
   `[DOOM] frame 1` nor a fallback.
3. A framebuffer whose `pitch` exceeds `width × 4` renders with no diagonal shear. The host
   test in `tests/kernel/run_display_test.sh` covers the copy arithmetic.
4. `build_service.py`'s leakage gate finds no `net`, `fs`, `sched` or `ipc` object in the image.
6. `KERNEL_TREE=<tree> tests/kernel/run_play_doom_test.sh` exits 0: the key queue, the
   translation table, the centred blit and the bounded WAD read, on the host.
7. `scripts/run-intent-probe.sh doom <package>` reports WORKED: a non-blank frame, and keys that
   change it, judged from outside the guest through QEMU's monitor.
5. No WAD, and no doomgeneric source, is present in the repository.
