#!/usr/bin/env bash
# The AUTON end-to-end spine: train -> export -> parity -> ISO -> boot ->
# markers -> transcript, in one command, with a verdict and an artifact dir.
#
# Usage: scripts/e2e.sh [--rung 3a] [--skip-train] [--keep N] [--help]
#
#   --rung {3a,3b,3c}  training rung (default 3a: tiny model, existing corpus)
#   --skip-train       reuse the last checkpoint in SLM/work (fast iteration)
#   --eval             add the graded chat eval as a final stage
#   --target DIR       kernel tree to validate (default: kernels/<arch>).
#                      Point this at agent-generated output.
#   --keep N           artifact dirs to retain (default 10)
#   --accel NAME       QEMU accelerator (default: probed; AUTON_ACCEL also works).
#                      An explicit choice the host lacks is refused, never downgraded.
#   --firmware F       bios (default) or uefi (OVMF; the ISO is repacked for UEFI)
#   --arch A           x86_64 (default) or aarch64. aarch64 runs the BOOT spine
#                      only: build, boot, markers. The model stages are x86-only
#                      by specification (slm.md), and a spine that pretended
#                      otherwise would report a pass for stages it never ran.
#
# Exits non-zero on the first failing stage. Artifacts are written either way.
#
# Hard rule: this script CALLS existing entry points and never reimplements
# them. Any logic a stage needs belongs in the tool that stage invokes.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"
# shellcheck source=lib/markers.sh
source "$ROOT/scripts/lib/markers.sh"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac   # absolutize before any cd

ARCH="${ARCH:-x86_64}"
# The kernel tree is a TARGET, not a fixed path. In the intent-compiler model
# the tree is agent-generated output — `AUTON train "<intent>" --output ./Doom`
# — so the spine must validate whatever was just produced. Defaults to the
# in-repo reference tree when one exists.
TARGET="${TARGET:-$ROOT/kernels/$ARCH}"
case "$TARGET" in /*) ;; *) TARGET="$ROOT/$TARGET";; esac

RUNG="3a"
SKIP_TRAIN=0
RUN_EVAL=0
KEEP="${KEEP:-10}"
ACCEL_REQ=""
FIRMWARE="${FIRMWARE:-bios}"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
	case "$1" in
		--rung)       RUNG="${2:?--rung needs a value}"; shift 2 ;;
		--rung=*)     RUNG="${1#*=}"; shift ;;
		--skip-train) SKIP_TRAIN=1; shift ;;
		--eval)       RUN_EVAL=1; shift ;;
		--target)     TARGET="${2:?--target needs a directory}"; shift 2 ;;
		--target=*)   TARGET="${1#*=}"; shift ;;
		--keep)       KEEP="${2:?--keep needs a value}"; shift 2 ;;
		--keep=*)     KEEP="${1#*=}"; shift ;;
		--accel)      ACCEL_REQ="${2:?--accel needs a value}"; shift 2 ;;
		--accel=*)    ACCEL_REQ="${1#*=}"; shift ;;
		--firmware)   FIRMWARE="${2:?--firmware needs bios or uefi}"; shift 2 ;;
		--firmware=*) FIRMWARE="${1#*=}"; shift ;;
		--arch)       ARCH="${2:?--arch needs x86_64 or aarch64}"; shift 2 ;;
		--arch=*)     ARCH="${1#*=}"; shift ;;
		-h|--help)    usage; exit 0 ;;
		*) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
	esac
done

case "$RUNG" in
	3a) ;;
	3b|3c)
		echo "rung $RUNG is not implemented yet (Phase $RUNG delivers it)." >&2
		echo "Only --rung 3a runs today." >&2
		exit 2 ;;
	*) echo "unknown rung: $RUNG (expected 3a, 3b or 3c)" >&2; exit 2 ;;
esac

# The architecture decides the toolchain, the emulator and which stages exist.
# toolchain.sh was sourced before the arguments were parsed, so re-resolve with
# the chosen ARCH — otherwise `--arch aarch64` would quietly use x86 tools.
case "$ARCH" in
	x86_64|aarch64) ;;
	*) echo "unknown arch: $ARCH (expected x86_64 or aarch64)" >&2; exit 2 ;;
esac
if [ "$ARCH" != "x86_64" ]; then
	unset CC QEMU GRUB_MKRESCUE GRUB_MKRESCUE_EFI
	export ARCH
	# shellcheck source=lib/toolchain.sh
	source "$ROOT/scripts/lib/toolchain.sh"
	TARGET="${TARGET:-$ROOT/kernels/$ARCH}"
	case "$TARGET" in /*) ;; *) TARGET="$ROOT/$TARGET";; esac
	echo "arch: $ARCH (CC=$CC, QEMU=$QEMU)"
	# The tree comes first: asking for a cross compiler to build a tree that
	# has nothing to compile sends the reader after the wrong problem.
	if [ ! -d "$TARGET/kernel/arch/aarch64" ]; then
		echo "no kernel/arch/aarch64 in ${TARGET#"$ROOT"/}: the arch layer is not generated." >&2
		echo "arch/aarch64.md specifies it; the DTB parser it needs is proved by" >&2
		echo "tests/kernel/run_dtb_test.sh. Nothing to boot, so nothing is claimed." >&2
		exit 2
	fi
	command -v "$CC" >/dev/null || {
		echo "no $CC on PATH: brew install aarch64-elf-gcc (Darwin), or" >&2
		echo "apt install gcc-aarch64-linux-gnu (Debian)" >&2
		exit 2; }
fi

auton_accel "$ACCEL_REQ" || exit 2
echo "accelerator: $AUTON_ACCEL ($AUTON_ACCEL_REASON)"

# Firmware (windows-linux B3). UEFI boots OVMF from pflash and an ISO repacked
# by scripts/iso-efi.sh; an explicit uefi request without OVMF fails here, not
# mid-run.
FW_ARGS=()
case "$FIRMWARE" in
	bios) ;;
	uefi)
		auton_ovmf || exit 2
		FW_ARGS=(-machine pc -drive "if=pflash,format=raw,readonly=on,file=$AUTON_OVMF_CODE")
		echo "firmware: uefi ($AUTON_OVMF_CODE)" ;;
	*) echo "unknown firmware: $FIRMWARE (expected bios or uefi)" >&2; exit 2 ;;
esac

# bootable <isodir> <bios-iso>: the ISO to boot for $FIRMWARE.
bootable() {
	if [ "$FIRMWARE" = uefi ]; then
		local out="${2%.iso}-efi.iso"
		"$ROOT/scripts/iso-efi.sh" "$1" "$out" >/dev/null || return 1
		echo "$out"
	else
		echo "$2"
	fi
}

# --- artifacts -------------------------------------------------------------- #
RUN_ID="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
ART="$ROOT/.artifacts/e2e/$RUN_ID"
mkdir -p "$ART"

WORK="$ROOT/SLM/work"
STAGE_LOG="$ART/stages.tsv"
printf 'stage\tname\tstatus\tseconds\n' > "$STAGE_LOG"

TOTAL_STAGES=$([ "$RUN_EVAL" -eq 1 ] && echo 11 || echo 10)
STAGE_NO=0
FAILED_STAGE=""
declare -a STAGE_NAMES=()
declare -a STAGE_STATUS=()
declare -a STAGE_SECS=()

# stage <name> <function> [args...]
# Runs a stage, times it, records it, and short-circuits the rest on failure.
# A stage that is skipped still appears in the summary — a silent skip and a
# pass must never look alike.
stage() {
	local name="$1"; shift
	STAGE_NO=$((STAGE_NO + 1))
	local label
	label="$(printf '[%d/%d] %-10s' "$STAGE_NO" "$TOTAL_STAGES" "$name")"

	if [ -n "$FAILED_STAGE" ]; then
		printf '%s SKIPPED (after %s failed)\n' "$label" "$FAILED_STAGE"
		record_stage "$name" SKIPPED 0
		return 0
	fi

	local start end secs rc
	start="$(date +%s)"
	printf '%s ... ' "$label"
	if "$@" > "$ART/$STAGE_NO-$name.log" 2>&1; then rc=0; else rc=$?; fi
	end="$(date +%s)"
	secs=$((end - start))

	if [ "$rc" -eq 0 ]; then
		printf 'ok (%ss)\n' "$secs"
		record_stage "$name" PASS "$secs"
	else
		printf 'FAILED (%ss, rc=%s)\n' "$secs" "$rc"
		printf '        see %s\n' "${ART#"$ROOT"/}/$STAGE_NO-$name.log"
		tail -n "${FAIL_TAIL:-15}" "$ART/$STAGE_NO-$name.log" | sed 's/^/        | /'
		record_stage "$name" FAIL "$secs"
		FAILED_STAGE="$name"
	fi
}

record_stage() {
	STAGE_NAMES+=("$1"); STAGE_STATUS+=("$2"); STAGE_SECS+=("$3")
	printf '%d\t%s\t%s\t%s\n' "$STAGE_NO" "$1" "$2" "$3" >> "$STAGE_LOG"
}

# --- rung parameters -------------------------------------------------------- #
# 3a proves the pipeline on the existing corpus: os_tasks.jsonl is 1.7 KB and
# tokenizes to ~61 tokens, so seq_len*batch_size must stay under that or
# train.py rejects the dataset. Chat quality is Phase 3b's job, not this one.
CORPUS="$ROOT/SLM/datasets/os_tasks.jsonl"
CONFIG="$ROOT/SLM/configs/tiny_10M.yaml"
MAX_STEPS="${MAX_STEPS:-200}"
SEQ_LEN="${SEQ_LEN:-16}"
BATCH_SIZE="${BATCH_SIZE:-2}"

VOCAB="$WORK/vocab.json"
TOKENS="$WORK/tokens.jsonl"
CKPT="$WORK/final.pt"
MODEL_BIN="$WORK/auton-slm.bin"
NEURAL_ISO="$TARGET/build/auton-neural.iso"
SERIAL_LOG="$ART/serial-neural.log"
TRANSCRIPT_FILE="${TRANSCRIPT_FILE:-$ROOT/tests/transcripts/boot-basics.txt}"

# --- stages ------------------------------------------------------------------ #
# Each stage CALLS an existing entry point. No stage reimplements logic that
# lives in the tool it invokes.

s_train() {
	mkdir -p "$WORK"
	if [ "$SKIP_TRAIN" -eq 1 ]; then
		# A reused checkpoint is legitimate, a missing one is not — never let
		# --skip-train silently proceed to export a stale or absent model.
		local missing=0
		for f in "$VOCAB" "$CKPT"; do
			[ -f "$f" ] || { echo "--skip-train but $f is missing"; missing=1; }
		done
		[ "$missing" -eq 0 ] || return 1
		echo "reusing checkpoint $CKPT ($(date -r "$CKPT" -u +%Y-%m-%dT%H:%M:%SZ))"
		return 0
	fi

	"$PY" "$ROOT/SLM/tools/tokenizer.py" \
		--input "$CORPUS" --output "$VOCAB" --tokenize-to "$TOKENS" || return 1
	"$PY" "$ROOT/SLM/scripts/train.py" \
		--config "$CONFIG" --dataset "$TOKENS" --output "$WORK" \
		--max-steps "$MAX_STEPS" --seq-len "$SEQ_LEN" --batch-size "$BATCH_SIZE"
}

s_export() {
	"$PY" "$ROOT/SLM/scripts/export_auton.py" \
		--checkpoint "$CKPT" --vocab "$VOCAB" --output "$MODEL_BIN" || return 1
	# export_auton.py already writes <output>.manifest.json; keep it with the run.
	[ -f "$MODEL_BIN.manifest.json" ] && cp "$MODEL_BIN.manifest.json" "$ART/"
	return 0
}

s_parity() {
	KERNEL_TREE="$TARGET" "$ROOT/tests/kernel/neural_parity.sh" \
		"$MODEL_BIN" "$CKPT" "$VOCAB"
}

s_iso() {
	make -C "$TARGET" iso-neural MODEL="$MODEL_BIN"
}

# aarch64 has no bootloader: QEMU's virt machine takes the ELF with -kernel and
# hands the kernel a device tree. There is no ISO to build and none is faked.
s_build_arch() {
	make -C "$TARGET" CC="$CC" >/dev/null || return 1
	test -f "$TARGET/build/kernel.bin"
}

s_boot() {
	# The kernel boots to an interactive prompt and never exits, so waiting for
	# QEMU to finish would always burn the whole timeout. Poll for the last boot
	# marker instead and stop as soon as it lands — a timeout then means the
	# boot genuinely did not complete, not that the VM is merely still running.
	: > "$SERIAL_LOG"
	local iso
	iso="$(bootable "$TARGET/build/isodir-neural" "$NEURAL_ISO")" || return 1
	"$QEMU" -accel "$AUTON_ACCEL" ${FW_ARGS[@]+"${FW_ARGS[@]}"} -cdrom "$iso" -serial stdio -display none \
		-no-reboot -m "${MEM:-256M}" > "$SERIAL_LOG" 2>/dev/null &
	local qemu_pid=$! booted=0 waited=0
	local limit="${BOOT_TIMEOUT:-90}"

	while [ "$waited" -lt "$limit" ]; do
		if grep -q '\[BOOT\] OK' "$SERIAL_LOG" 2>/dev/null; then booted=1; break; fi
		kill -0 "$qemu_pid" 2>/dev/null || break   # QEMU exited on its own
		sleep 1
		waited=$((waited + 1))
	done

	kill "$qemu_pid" 2>/dev/null
	wait "$qemu_pid" 2>/dev/null || true

	if [ ! -s "$SERIAL_LOG" ]; then
		echo "no serial output captured in ${waited}s"
		return 1
	fi
	if [ "$booted" -ne 1 ]; then
		echo "boot did not reach [BOOT] OK within ${limit}s; last lines:"
		tail -5 "$SERIAL_LOG"
		return 1
	fi
	echo "booted in ${waited}s ($(wc -l < "$SERIAL_LOG" | tr -d ' ') lines of serial output)"
	return 0
}

s_markers() {
	local serial fail=0
	serial="$(cat "$SERIAL_LOG")"
	# A neural boot must satisfy the ordinary boot markers AND the model-loaded
	# /backend-selected chain. Both sets come from acceptance_tests.py.
	for set_name in boot neural; do
		markers_load "$set_name" || return 1
		echo "--- $set_name ---"
		markers_check "$serial"
		[ "$MARKERS_FAILED" -eq 0 ] || fail=1
	done
	return "$fail"
}

s_eval() {
	# A freshly trained model has a new fingerprint, so every free-form answer is
	# unseen and queues for review. That is honest, not a failure: the stage
	# reports the auto-graded subset and says how many await a human. Exit 3
	# from eval.sh means "ungraded remain", which is not a red run.
	"$ROOT/scripts/eval.sh" --model "$MODEL_BIN" --json "$ART/eval.json"
	local rc=$?
	[ "$rc" -eq 0 ] || [ "$rc" -eq 3 ]
}

# Boot a deliberately unusable model and assert the kernel degrades honestly.
# The happy path alone would not notice a kernel that faulted on, or silently
# mis-parsed, a corrupt module — and the module is untrusted input.
s_fallback() {
	local bad="$ART/corrupt-model.bin"
	local fail=0 serial="$ART/serial-fallback.log"

	# Truncated: a real header followed by nothing like enough weights.
	head -c 100000 "$MODEL_BIN" > "$bad" 2>/dev/null || return 1
	make -C "$TARGET" iso-neural MODEL="$bad" >/dev/null 2>&1 || return 1

	: > "$serial"
	local iso
	iso="$(bootable "$TARGET/build/isodir-neural" "$NEURAL_ISO")" || return 1
	"$QEMU" -accel "$AUTON_ACCEL" ${FW_ARGS[@]+"${FW_ARGS[@]}"} -cdrom "$iso" -serial stdio -display none \
		-no-reboot -m "${MEM:-256M}" > "$serial" 2>/dev/null &
	local qp=$! waited=0
	while [ "$waited" -lt "${BOOT_TIMEOUT:-60}" ]; do
		grep -q '\[BOOT\] OK' "$serial" 2>/dev/null && break
		kill -0 "$qp" 2>/dev/null || break
		sleep 1; waited=$((waited + 1))
	done
	kill "$qp" 2>/dev/null; wait "$qp" 2>/dev/null || true

	markers_load fallback-rejected || return 1
	echo "--- corrupt module ---"
	markers_check "$(cat "$serial")"
	[ "$MARKERS_FAILED" -eq 0 ] || fail=1

	# No module at all: the rule engine is the intended backend here.
	make -C "$TARGET" iso >/dev/null 2>&1 || return 1
	: > "$serial.nomodule"
	iso="$(bootable "$TARGET/build/isodir" "$TARGET/build/auton.iso")" || return 1
	"$QEMU" -accel "$AUTON_ACCEL" ${FW_ARGS[@]+"${FW_ARGS[@]}"} -cdrom "$iso" -serial stdio \
		-display none -no-reboot -m "${MEM:-256M}" > "$serial.nomodule" 2>/dev/null &
	qp=$!; waited=0
	while [ "$waited" -lt "${BOOT_TIMEOUT:-60}" ]; do
		grep -q '\[BOOT\] OK' "$serial.nomodule" 2>/dev/null && break
		kill -0 "$qp" 2>/dev/null || break
		sleep 1; waited=$((waited + 1))
	done
	kill "$qp" 2>/dev/null; wait "$qp" 2>/dev/null || true

	markers_load fallback-no-module || return 1
	echo "--- no module ---"
	markers_check "$(cat "$serial.nomodule")"
	[ "$MARKERS_FAILED" -eq 0 ] || fail=1

	# Restore the real neural ISO for anything downstream.
	make -C "$TARGET" iso-neural MODEL="$MODEL_BIN" >/dev/null 2>&1
	return "$fail"
}

# The host half of the chat OS. Needs no VM, so it is cheap and independent of
# everything above it; a kernel regression and a control-plane regression should
# not be able to mask each other.
s_controlplane() {
	"$ROOT/scripts/cp-e2e.sh"
}

# "Speak a goal, AUTON does the steps" — on both the deterministic planner and
# the live brain, plus the approval gate. Driven with --brain llm rather than
# auto, so a broken model cannot pass by falling back.
s_operator() {
	"$ROOT/scripts/operator-e2e.sh"
}

s_transcript() {
	# Driven against the rule-engine ISO: these are deterministic system answers,
	# and rung 3a's model is trained only far enough to prove the pipeline, not
	# to hold a conversation. Chat quality is graded in Phase 6.
	local iso="$TARGET/build/auton.iso"
	[ -f "$iso" ] || make -C "$TARGET" iso >/dev/null || return 1
	"$ROOT/scripts/transcript.sh" "$TRANSCRIPT_FILE" "$iso" "$ART/serial-transcript.log"
}

echo "AUTON e2e — rung $RUNG$([ "$SKIP_TRAIN" -eq 1 ] && echo ' (train skipped)')"
echo "artifacts: ${ART#"$ROOT"/}"
echo

# --- stage 0: preflight ------------------------------------------------------ #
# A gate, not one of the seven: if the host cannot do the work there is nothing
# to report per-stage. Runs before training so a missing tool or a full disk
# costs seconds, not a training run.
if [ ! -d "$TARGET/kernel" ]; then
	echo "no kernel tree at ${TARGET#"$ROOT"/}"
	echo
	echo "The spine validates a kernel tree; none is present. Either generate"
	echo "one (AUTON's premise: the agents write it) or restore the reference"
	echo "tree, then re-run with --target <dir>."
	exit 2
fi

printf '[0/%d] %-10s ... ' "$TOTAL_STAGES" "preflight"
if CHECK_E2E=1 "$ROOT/scripts/preflight.sh" > "$ART/0-preflight.log" 2>&1; then
	echo "ok"
else
	echo "FAILED"
	sed 's/^/        | /' "$ART/0-preflight.log"
	echo
	echo "RED    preflight failed — host is not ready to run the spine"
	echo "artifacts: ${ART#"$ROOT"/}"
	exit 1
fi

RUN_START="$(date +%s)"
if [ "$ARCH" = "aarch64" ]; then
	# The boot spine only. The model stages are x86-only by specification
	# (slm.md: the neural backend's SSE path), and the control-plane stages are
	# host-side and architecture-independent, so running them here would say
	# nothing about aarch64. Naming the omission beats a green run that
	# silently skipped two thirds of itself.
	echo "aarch64: build -> boot -> markers. The model stages are x86-only (slm.md)."
	stage build      s_build_arch
	stage boot       s_boot
	stage markers    s_markers
	stage transcript s_transcript
else
stage train      s_train
stage export     s_export
stage parity     s_parity
stage iso        s_iso
stage boot       s_boot
stage markers    s_markers
stage fallback   s_fallback
stage cplane     s_controlplane
stage operator   s_operator
stage transcript s_transcript
[ "$RUN_EVAL" -eq 1 ] && stage eval s_eval
fi
RUN_SECS=$(( $(date +%s) - RUN_START ))

# --- verdict ---------------------------------------------------------------- #
if [ -z "$FAILED_STAGE" ]; then VERDICT=GREEN; else VERDICT=RED; fi

write_summary_json() {
	local i first=1
	{
		printf '{\n'
		printf '  "run_id": "%s",\n' "$RUN_ID"
		printf '  "verdict": "%s",\n' "$VERDICT"
		printf '  "rung": "%s",\n' "$RUNG"
		printf '  "arch": "%s",\n' "$ARCH"
		printf '  "skip_train": %s,\n' "$([ "$SKIP_TRAIN" -eq 1 ] && echo true || echo false)"
		printf '  "failed_stage": %s,\n' \
			"$([ -n "$FAILED_STAGE" ] && printf '"%s"' "$FAILED_STAGE" || echo null)"
		printf '  "seconds": %s,\n' "$RUN_SECS"
		printf '  "model": {\n'
		printf '    "max_steps": %s, "seq_len": %s, "batch_size": %s\n' \
			"$MAX_STEPS" "$SEQ_LEN" "$BATCH_SIZE"
		printf '  },\n'
		printf '  "stages": [\n'
		for i in "${!STAGE_NAMES[@]}"; do
			[ "$first" -eq 1 ] || printf ',\n'
			first=0
			printf '    {"n": %d, "name": "%s", "status": "%s", "seconds": %s}' \
				"$((i + 1))" "${STAGE_NAMES[$i]}" "${STAGE_STATUS[$i]}" "${STAGE_SECS[$i]}"
		done
		printf '\n  ]\n}\n'
	} > "$ART/summary.json"
}

write_summary_md() {
	{
		printf '# E2E run %s\n\n' "$RUN_ID"
		printf '%s — rung %s, %ss total.' "$VERDICT" "$RUNG" "$RUN_SECS"
		if [ -n "$FAILED_STAGE" ]; then
			printf ' Stage `%s` failed; later stages were skipped.\n\n' "$FAILED_STAGE"
		else
			printf ' All %s stages passed.\n\n' "$TOTAL_STAGES"
		fi
		printf '| # | Stage | Status | Seconds |\n|---|---|---|---|\n'
		local i
		for i in "${!STAGE_NAMES[@]}"; do
			printf '| %d | %s | %s | %s |\n' \
				"$((i + 1))" "${STAGE_NAMES[$i]}" "${STAGE_STATUS[$i]}" "${STAGE_SECS[$i]}"
		done
		printf '\nArtifacts: `%s`\n' "${ART#"$ROOT"/}"
	} > "$ART/summary.md"
}

# Keep the last $KEEP runs. Serial logs and model manifests are small, but a
# loop left running would fill the disk the Phase 0 preflight exists to guard.
prune_artifacts() {
	local dirs n
	[ "$KEEP" -gt 0 ] 2>/dev/null || return 0
	dirs="$(ls -1d "$ROOT/.artifacts/e2e"/*/ 2>/dev/null | sort)"
	n="$(printf '%s\n' "$dirs" | grep -c . )"
	[ "$n" -gt "$KEEP" ] || return 0
	printf '%s\n' "$dirs" | head -n "$((n - KEEP))" | while IFS= read -r d; do
		[ -n "$d" ] && rm -rf "$d"
	done
}

write_summary_json
write_summary_md
prune_artifacts

echo
if [ "$VERDICT" = GREEN ]; then
	echo "GREEN  all $TOTAL_STAGES stages passed in ${RUN_SECS}s"
else
	echo "RED    stage '$FAILED_STAGE' failed after ${RUN_SECS}s"
fi
echo "artifacts: ${ART#"$ROOT"/}"

if [ "$RUN_EVAL" -eq 1 ] && [ -f "$ART/eval.json" ]; then
	"$PY" - "$ART/eval.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
c, graded = d["counts"], d["graded"]
if graded:
    pct = lambda n: 100.0 * n / graded
    print(f'eval:      correct {pct(c["correct"]):.0f}%  honest {pct(c["honest_roadmap"]):.0f}%  '
          f'garbage {pct(c["garbage"]):.0f}%  (graded {graded}/{d["total"]})')
else:
    print(f'eval:      nothing graded yet ({d["total"]} awaiting review)')
PYEOF
fi

[ "$VERDICT" = GREEN ]
