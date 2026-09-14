# x86_64 toolchain settings for the seed kernel.
#
# CC defaults to the bare-metal cross compiler (x86_64-elf-gcc) but can be
# overridden to the Linux GNU cross compiler used in the Docker image:
#   make CC=x86_64-linux-gnu-gcc
CC      ?= x86_64-elf-gcc
LINKER  := kernel/arch/x86_64/linker.ld

# Freestanding, integer-only (no SSE/x87/red-zone), small code model.
# The seed runs identity-mapped in low memory, so no -mcmodel=kernel offset.
CFLAGS  := -ffreestanding -fno-stack-protector -fno-pic -fno-pie \
           -mno-red-zone -mno-mmx -mno-sse -mno-sse2 -mno-80387 \
           -fno-tree-loop-distribute-patterns \
           -std=gnu11 -O2 -g -Wall -Wextra \
           -Ikernel/include

# SSE-enabled profile for the neural backend's float math (kernel/slm/neural/*,
# kernel/lib/kmath.c). SSE is turned on in boot.S; these TUs may use hardware
# float. Red zone stays disabled (interrupt-safe). The rest of the kernel keeps
# the integer-only CFLAGS above so interrupt handlers never touch SSE state.
CFLAGS_SSE := -ffreestanding -fno-stack-protector -fno-pic -fno-pie \
              -mno-red-zone -fno-math-errno -fno-tree-loop-distribute-patterns \
              -std=gnu11 -O2 -g -Wall -Wextra \
              -Ikernel/include

ASFLAGS := -ffreestanding -fno-pic -fno-pie

LDFLAGS := -nostdlib -no-pie -Wl,--build-id=none -Wl,-T,$(LINKER)
