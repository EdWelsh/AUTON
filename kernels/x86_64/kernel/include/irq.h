/* Minimal interrupt subsystem: IDT + 8259 PIC + PIT timer tick.
 *
 * Its main purpose in the seed is to let polling loops execute `hlt` and yield
 * the CPU. Under QEMU/TCG a busy poll loop starves the emulator's main loop, so
 * the SLIRP network backend almost never delivers received frames. Halting
 * until the next timer interrupt hands control back to QEMU every tick, after
 * which a single net_poll() reliably drains anything that arrived. */
#ifndef AUTON_IRQ_H
#define AUTON_IRQ_H

/* Install the IDT, remap the PIC, and start a ~1 kHz timer. Leaves IF clear. */
void idt_init(void);

/* Set IF (sti). Call once after idt_init, before any hlt-based wait loop. */
void irq_enable(void);

#endif /* AUTON_IRQ_H */
