/* IDT setup, 8259 PIC remap, and a ~1 kHz PIT timer. See irq.h for why this
 * exists (hlt-based yielding so polled networking works under QEMU). */
#include <stdint.h>
#include "irq.h"
#include "kernel.h"
#include "io/io.h"

/* ---- 8259 PIC ---- */
#define PIC1_CMD  0x20
#define PIC1_DATA 0x21
#define PIC2_CMD  0xA0
#define PIC2_DATA 0xA1
#define PIC_EOI   0x20

/* ---- PIT ---- */
#define PIT_CH0   0x40
#define PIT_CMD   0x43
#define PIT_HZ    1000u
#define PIT_BASE  1193182u

/* IDT vectors: exceptions 0-31, hardware IRQs remapped to 32-47. */
#define IRQ_BASE  32

struct idt_entry {
	uint16_t off_lo;
	uint16_t sel;
	uint8_t  ist;
	uint8_t  type_attr;
	uint16_t off_mid;
	uint32_t off_hi;
	uint32_t zero;
} __attribute__((packed));

struct idt_ptr {
	uint16_t limit;
	uint64_t base;
} __attribute__((packed));

static struct idt_entry idt[256];

/* asm stubs */
extern void isr_default(void);
extern void irq0_stub(void);
extern void irq_default(void);

static void set_entry(int vec, void (*handler)(void))
{
	uint64_t a = (uint64_t)handler;

	idt[vec].off_lo = (uint16_t)(a & 0xFFFF);
	idt[vec].sel = 0x08;            /* 64-bit kernel code selector (boot.S GDT) */
	idt[vec].ist = 0;
	idt[vec].type_attr = 0x8E;      /* present, DPL0, 64-bit interrupt gate */
	idt[vec].off_mid = (uint16_t)((a >> 16) & 0xFFFF);
	idt[vec].off_hi = (uint32_t)((a >> 32) & 0xFFFFFFFF);
	idt[vec].zero = 0;
}

static void pic_remap(void)
{
	/* ICW1: begin init, ICW4 present. */
	io_write8(PIC1_CMD, 0x11);
	io_write8(PIC2_CMD, 0x11);
	/* ICW2: vector offsets. */
	io_write8(PIC1_DATA, IRQ_BASE);
	io_write8(PIC2_DATA, IRQ_BASE + 8);
	/* ICW3: master/slave wiring (slave on IRQ2). */
	io_write8(PIC1_DATA, 0x04);
	io_write8(PIC2_DATA, 0x02);
	/* ICW4: 8086 mode. */
	io_write8(PIC1_DATA, 0x01);
	io_write8(PIC2_DATA, 0x01);
	/* Masks: unmask only the timer (IRQ0) on the master. */
	io_write8(PIC1_DATA, 0xFE);
	io_write8(PIC2_DATA, 0xFF);
}

static void pit_init(void)
{
	uint32_t div = PIT_BASE / PIT_HZ;

	io_write8(PIT_CMD, 0x36);                       /* ch0, lo/hi, mode 3 */
	io_write8(PIT_CH0, (uint8_t)(div & 0xFF));
	io_write8(PIT_CH0, (uint8_t)((div >> 8) & 0xFF));
}

/* ---- C handlers called from the asm stubs ---- */
void exception_handler(void)
{
	kprintf("[CPU] unhandled exception - halting\n");
	for (;;)
		__asm__ volatile("cli; hlt");
}

void irq_timer(void)
{
	io_write8(PIC1_CMD, PIC_EOI);
}

void irq_eoi_only(void)
{
	io_write8(PIC2_CMD, PIC_EOI);
	io_write8(PIC1_CMD, PIC_EOI);
}

void idt_init(void)
{
	for (int i = 0; i < 32; i++)
		set_entry(i, isr_default);
	for (int i = 32; i < 48; i++)
		set_entry(i, irq_default);
	set_entry(IRQ_BASE, irq0_stub);         /* timer */

	struct idt_ptr p = { (uint16_t)(sizeof(idt) - 1), (uint64_t)(uintptr_t)idt };
	__asm__ volatile("lidt %0" : : "m"(p));

	pic_remap();
	pit_init();
}

void irq_enable(void)
{
	__asm__ volatile("sti");
}
