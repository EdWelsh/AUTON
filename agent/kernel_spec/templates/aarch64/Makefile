# AUTON aarch64 seed kernel build.
#
# Unlike x86_64 there is no GRUB and no ISO: QEMU's virt machine takes the ELF
# with -kernel and hands the kernel a device tree in X0. That is why the
# aarch64 bring-up starts with a DTB parser (tests/kernel/run_dtb_test.sh)
# rather than with a bootloader.

ARCH := aarch64
include kernel/arch/$(ARCH)/toolchain.mk

BUILD  := build
KERNEL := $(BUILD)/kernel.bin

QEMU ?= qemu-system-aarch64

CSRC := $(shell find kernel -name '*.c')
ASRC := $(shell find kernel -name '*.S')
OBJ  := $(patsubst %,$(BUILD)/%.o,$(CSRC) $(ASRC))

all: $(KERNEL)

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

# `iso` exists so the same harnesses work on both architectures; here it is the
# kernel itself, because virt needs no image. A target that quietly did nothing
# would let a caller believe it had produced something bootable.
iso: $(KERNEL)
	@echo "aarch64: no ISO is built; QEMU virt boots $(KERNEL) with -kernel"

# gic-version=2 matches arch/aarch64.md; -cpu cortex-a72 is a part QEMU models
# fully under TCG and accelerates under HVF on Apple Silicon.
run: $(KERNEL)
	$(QEMU) -M virt,gic-version=2 -cpu cortex-a72 -m 256M \
		-kernel $(KERNEL) -serial stdio -display none -no-reboot

clean:
	rm -rf $(BUILD)

.PHONY: all iso run clean
