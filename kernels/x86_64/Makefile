# AUTON x86_64 seed kernel build.
# Produces build/kernel.bin — the exact path the QEMU test harness boots
# (orchestrator/validation/test_validator.py).

ARCH := x86_64
include kernel/arch/$(ARCH)/toolchain.mk

BUILD  := build
KERNEL := $(BUILD)/kernel.bin
ISO    := $(BUILD)/auton.iso

CSRC := $(shell find kernel -name '*.c')
ASRC := $(shell find kernel -name '*.S')
OBJ  := $(patsubst %,$(BUILD)/%.o,$(CSRC) $(ASRC))

all: $(KERNEL)

# Neural float code is compiled with SSE (more specific rules win over %.c.o).
$(BUILD)/kernel/slm/neural/%.c.o: kernel/slm/neural/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS_SSE) -c $< -o $@

$(BUILD)/kernel/lib/kmath.c.o: kernel/lib/kmath.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS_SSE) -c $< -o $@

$(BUILD)/%.c.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.S.o: %.S
	@mkdir -p $(dir $@)
	$(CC) $(ASFLAGS) -c $< -o $@

$(KERNEL): $(OBJ) $(LINKER)
	@mkdir -p $(dir $@)
	$(CC) $(LDFLAGS) -o $@ $(OBJ)
	@echo "built $(KERNEL)"

# Build a bootable GRUB rescue ISO (Multiboot2 -> ELF64 long-mode kernel).
iso: $(ISO)
$(ISO): $(KERNEL) grub/grub.cfg
	@mkdir -p $(BUILD)/isodir/boot/grub
	cp $(KERNEL) $(BUILD)/isodir/boot/kernel.bin
	cp grub/grub.cfg $(BUILD)/isodir/boot/grub/grub.cfg
	grub-mkrescue -o $(ISO) $(BUILD)/isodir 2>/dev/null
	@echo "built $(ISO)"

# Boot the kernel in QEMU with serial on stdio.
run: $(ISO)
	qemu-system-x86_64 -cdrom $(ISO) -serial stdio -display none \
		-no-reboot -m 128M

# Bootable ISO that bundles the on-device model as a Multiboot2 module.
# MODEL must point to a flat auton-slm.bin (see SLM/scripts/export_auton.py).
NEURAL_ISO := $(BUILD)/auton-neural.iso
iso-neural: $(NEURAL_ISO)
$(NEURAL_ISO): $(KERNEL) grub/grub-neural.cfg
	@test -n "$(MODEL)" || { echo "set MODEL=path/to/auton-slm.bin"; exit 1; }
	@test -f "$(MODEL)" || { echo "MODEL not found: $(MODEL)"; exit 1; }
	@mkdir -p $(BUILD)/isodir-neural/boot/grub
	cp $(KERNEL) $(BUILD)/isodir-neural/boot/kernel.bin
	cp "$(MODEL)" $(BUILD)/isodir-neural/boot/auton-slm.bin
	cp grub/grub-neural.cfg $(BUILD)/isodir-neural/boot/grub/grub.cfg
	grub-mkrescue -o $(NEURAL_ISO) $(BUILD)/isodir-neural 2>/dev/null
	@echo "built $(NEURAL_ISO)"

# Boot with the model module and enough RAM to select the neural backend.
run-neural: $(NEURAL_ISO)
	qemu-system-x86_64 -cdrom $(NEURAL_ISO) -serial stdio -display none \
		-no-reboot -m 256M

clean:
	rm -rf $(BUILD)

.PHONY: all iso run iso-neural run-neural clean
