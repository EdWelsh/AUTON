#!/bin/sh
# Boot /auton.iso. Extra QEMU arguments may be passed to `docker run`.
ACCEL=tcg
[ -r /dev/kvm ] && [ -w /dev/kvm ] && ACCEL=kvm
echo "AUTON-CONTAINER: accel=$ACCEL"
exec qemu-system-x86_64 -accel "$ACCEL" -m "${AUTON_MEM:-512}" -cdrom /auton.iso -boot d \
  -display none -vga std -serial stdio -no-reboot \
  -qmp tcp:0.0.0.0:4444,server,nowait -vnc :0 "$@"
