# Pre-registration: generate storage (virtio-blk + FAT32, F7)

**Written 2026-09-22T16:39:17Z, before the run.** Protocol: `completed/w13-factory-f6-rerun.plan.md`.

| | |
|---|---|
| Subject | virtio-blk (`drivers.md`, `drivers/virtio-blk.md`) + FAT32 (`fs.md`), into `kernel-base-v5` |
| Model | ollama/gemma4:latest, 8.0B, Q4_K_M |
| Budget | $0; 30 iterations; 60 min; 600 s per call |
| Loop | as of `28d7b7d`: tool calls logged, and **the compile check before review (`6b349a9`)**, its first run |
| Goal | verbatim in `goal.txt` |
| Gates, in order | `KERNEL_TREE=<ws> tests/kernel/run_virtio_blk_test.sh`; `run_fat32_test.sh`; `scripts/run-storage-acceptance.sh <ws>` |
| Injected bugs | V6's 5 chain bugs and FAT32's 5, on whatever is generated |
| Expected | F6 and generate-mm: gemma4 writes at most a header. The same is likely. Reported either way |
| Deviation noted in advance | the plan depends on `w13-generate-mm`, which produced no allocator. The goal points the driver at the base's `dma_alloc` (identity-mapped, DMA-safe), which the virtqueue needs |
