# AUTON aarch64 seed kernel build.
#
# Unlike x86_64 there is no GRUB and no ISO: QEMU's virt machine takes the ELF
# with -kernel and hands the kernel a device tree in X0. That is why the
# aarch64 bring-up starts with a DTB parser (tests/kernel/run_dtb_test.sh)
# rather than with a bootloader.

ARCH := aarch64
include kernel/arch/$(ARCH)/toolchain.mk

BUILD  := build
ELF    := $(BUILD)/kernel.elf
# The bootable artefact is a FLAT image, not the ELF, and that is not a
# preference. QEMU's virt machine follows the Linux arm64 boot protocol —
# which is what puts the device tree's address in X0, as arch/aarch64.md
# says — only for a raw image. Booted as an ELF the same kernel starts with
# X0 = 0 and cannot find its own memory map. Measured, not assumed:
# tests/kernel/run_aarch64_smoke.sh prints "dtb in x0" for one and not the other.
KERNEL := $(BUILD)/kernel.bin
OBJCOPY ?= $(patsubst %-gcc,%-objcopy,$(CC))

QEMU ?= qemu-system-aarch64
# -cpu host is required by HVF; cortex-a72 is the portable TCG default.
CPU        ?= cortex-a72
ACCEL_ARGS ?=

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

$(ELF): $(OBJ) $(LINKER)
	@mkdir -p $(dir $@)
	$(CC) $(LDFLAGS) -o $@ $(OBJ)

$(KERNEL): $(ELF)
	$(OBJCOPY) -O binary $< $@
	@echo "built $(KERNEL) (flat image; the ELF is $(ELF))"

# `iso` exists so the same harnesses work on both architectures; here it is the
# kernel itself, because virt needs no image. A target that quietly did nothing
# would let a caller believe it had produced something bootable.
iso: $(KERNEL)
	@echo "aarch64: no ISO is built; QEMU virt boots $(KERNEL) with -kernel"

# gic-version=3, not 2: QEMU refuses -accel hvf with GICv2 ("HVF does not
# support GICv2 emulation"), and aarch64 exists here precisely because it is the
# architecture this host can run accelerated. ACCEL is left to the caller so a
# plain `make run` stays portable.
run: $(KERNEL)
	$(QEMU) -M virt,gic-version=3 -cpu $(CPU) $(ACCEL_ARGS) -m 256M \
		-kernel $(KERNEL) -serial stdio -display none -no-reboot

clean:
	rm -rf $(BUILD)

.PHONY: all iso run clean
