# aarch64 toolchain settings for the seed kernel.
#
# CC defaults to the bare-metal cross compiler; scripts/lib/toolchain.sh picks
# the platform's name (aarch64-elf-gcc on Darwin, aarch64-linux-gnu-gcc
# elsewhere) when ARCH=aarch64:
#   make CC=aarch64-linux-gnu-gcc
CC      ?= aarch64-elf-gcc
LINKER  := kernel/arch/aarch64/linker.ld

# Freestanding and integer-only. -mgeneral-regs-only is the aarch64 equivalent
# of x86's -mno-sse: it keeps the compiler out of the FP/SIMD registers, which
# matters because an exception handler that clobbers them without saving them
# corrupts whatever was mid-calculation. The neural backend's float code is
# x86-only (slm.md), so nothing here needs the FP profile x86_64 has.
CFLAGS  := -ffreestanding -fno-stack-protector -fno-pic -fno-pie \
           -mgeneral-regs-only -mstrict-align \
           -fno-tree-loop-distribute-patterns \
           -std=gnu11 -O2 -g -Wall -Wextra \
           -Ikernel/include

ASFLAGS := -ffreestanding -fno-pic -fno-pie

# -Wl,--build-id=none keeps the image byte-identical across builds; QEMU's virt
# machine loads the ELF directly, so there is no bootloader to strip it.
LDFLAGS := -nostdlib -no-pie -Wl,--build-id=none -Wl,-T,$(LINKER)
