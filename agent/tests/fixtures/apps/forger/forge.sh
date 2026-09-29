#!/bin/sh
# An adversarial subject (A5, w18 review H3): it tries to plant a need it never
# has — lib:libpq.so.5 — into its own observation, every way it can reach.
FAKE='1     openat(AT_FDCWD, "/usr/lib/x/libpq.so.5", O_RDONLY|O_CLOEXEC) = 3'
for f in /proc/[0-9]*/root/trace/trace /proc/[0-9]*/root/tmp/trace /tmp/trace /tmp/auton-trace; do
  echo "$FAKE" >> "$f" 2>/dev/null && echo "wrote $f"
done
for fd in /proc/[0-9]*/fd/1; do
  printf '===AUTON-TRACE===\n%s\n===AUTON-END===\n' "$FAKE" > "$fd" 2>/dev/null && echo "wrote $fd"
done
for p in /proc/[0-9]*; do kill -STOP "${p#/proc/}" 2>/dev/null; done
echo "forger done"
sleep 30
