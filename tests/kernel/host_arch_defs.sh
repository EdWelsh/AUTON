# Sourced by the host suites. The HAL (kernel/include/hal.h) defines ARCH_* memory constants
# per architecture with #if defined(__x86_64__). The suites model the x86_64 target but are built
# on whatever the host is (an arm64 Mac), where hal.h has no branch and #errors out: a generated
# allocator that includes hal.h for arch_halt, as mm.md now tells it to, failed to compile (w24).
# Each is guarded #ifndef in hal.h, so on an x86_64 host these change nothing.
HOST_ARCH_DEFS=(-DARCH_PAGE_SIZE=4096ULL -DARCH_PAGE_SHIFT=12 -DARCH_PT_LEVELS=4
	-DARCH_STACK_SIZE=16384ULL -DARCH_KERNEL_VBASE=0xFFFF800000000000ULL
	-DARCH_KERNEL_LOAD=0x100000ULL -DARCH_USER_VBASE=0ULL -DARCH_USER_VTOP=0x00007FFFFFFFFFFFULL)
