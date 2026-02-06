# Drivers Specification

## Overview

Minimal device drivers for console I/O, timer, and keyboard.

## Serial Driver (UART 16550A)

Primary console output. COM1 at I/O port 0x3F8.

### Interface (`kernel/include/serial.h`)
```c
void serial_init(void);
void serial_putchar(char c);
void serial_write(const char *str);
void serial_printf(const char *fmt, ...);
char serial_getchar(void);  // Blocking read
int serial_available(void);  // Non-blocking check
```

### Implementation
- Initialize: set baud rate (115200), 8N1 format, enable FIFO
- Write: poll Line Status Register bit 5 (THR empty), write to THR
- Read: poll LSR bit 0 (data ready), read from RBR

## VGA Text Mode Driver

80x25 text framebuffer at 0xB8000.

### Interface (`kernel/include/vga.h`)
```c
void vga_init(void);
void vga_putchar(char c);
void vga_write(const char *str);
void vga_clear(void);
void vga_set_color(uint8_t fg, uint8_t bg);
```

## Timer Driver (PIT 8254)

Programmable Interval Timer for scheduler preemption.

### Interface (`kernel/include/timer.h`)
```c
void timer_init(uint32_t frequency_hz);  // e.g., 100 Hz
uint64_t timer_get_ticks(void);
void timer_handler(void);  // Called from IRQ0
```

## Keyboard Driver (PS/2)

### Interface (`kernel/include/keyboard.h`)
```c
void keyboard_init(void);
char keyboard_getchar(void);       // Blocking, returns ASCII
int keyboard_available(void);      // Non-blocking check
void keyboard_handler(void);       // Called from IRQ1
```

## Acceptance Criteria

- Serial: "Hello from AUTON!" appears in QEMU serial output
- VGA: Text displayed on screen in QEMU
- Timer: Interrupt fires at configured frequency
- Keyboard: Key presses captured and echoed to serial
