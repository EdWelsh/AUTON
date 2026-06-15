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
# libc6-dev provides the crt startup objects + libc needed to link hosted Rust
# binaries (the kernel itself builds -nostdlib and does not need them).
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git curl libc6-dev \
    && rm -rf /var/lib/apt/lists/*
# Modern Rust via rustup. Debian's packaged cargo (~1.63) is too old to build
# current crates (clap/tokio pull in edition-2024 deps), so install the stable
# toolchain into a shared location on PATH.
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain stable
# Orchestrator runtime + test deps. Heavy SLM training deps (torch) are NOT
# installed here to keep the image usable; install them in an SLM profile.
RUN pip3 install --no-cache-dir --break-system-packages \
        litellm gitpython pydantic rich click pyyaml \
        pytest pytest-asyncio pytest-cov pytest-mock pytest-timeout ruff

# ---- slm: dev + the heavy neural training/export stack ---------------------
# Separate stage so the torch dependency only lands in images that need it.
# The repo is volume-mounted at runtime, so packages are installed by name here
# (kept in sync with SLM/requirements.txt) rather than via COPY at build time.
# `docker compose run slm` runs the full SLM suite (training, ONNX/GGUF export).
FROM dev AS slm
RUN pip3 install --no-cache-dir --break-system-packages \
        torch numpy onnx gguf
