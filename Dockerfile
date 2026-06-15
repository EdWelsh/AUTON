# AUTON build/run/dev environment.
#
# Pinned to linux/amd64: the kernel is x86_64 and GRUB's PC/BIOS target
# (grub-pc-bin) + qemu-system-x86_64 BIOS boot only exist on amd64. On Apple
# Silicon this runs emulated — correct, just slower.
#
# Two stages:
#   base : toolchain + QEMU + GRUB (enough to build & boot the OS)
#   dev  : base + Python + Rust (orchestrator, tests, SLM tooling)

# ---- base: build & boot the kernel -----------------------------------------
FROM --platform=linux/amd64 debian:bookworm-slim AS base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc make binutils \
        nasm \
        qemu-system-x86 \
        grub-common grub-pc-bin xorriso mtools \
        ca-certificates bash \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
# The seed Makefile defaults CC to the bare-metal cross compiler; on amd64 the
# native gcc builds the freestanding kernel fine.
ENV CC=gcc
CMD ["bash", "scripts/auton-boot.sh", "x86_64"]

# ---- dev: orchestrator + tests + SLM tooling -------------------------------
FROM base AS dev
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git cargo rustc \
    && rm -rf /var/lib/apt/lists/*
# Orchestrator runtime + test deps. Heavy SLM training deps (torch) are NOT
# installed here to keep the image usable; install them in an SLM profile.
RUN pip3 install --no-cache-dir --break-system-packages \
        litellm gitpython pydantic rich click pyyaml \
        pytest pytest-asyncio pytest-cov pytest-mock pytest-timeout ruff
