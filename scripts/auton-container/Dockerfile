# An AUTON image as a container, for testing in Rancher/Docker (w23).
# The container is only the machine: QEMU running the ISO. Serial goes to stdout (docker logs),
# QMP listens on 4444 so a probe outside the container can read the framebuffer and send keys,
# and VNC on 5900 lets a person watch. KVM is used when /dev/kvm is passed through, else tcg.
FROM alpine:3.23
RUN apk add --no-cache qemu-system-x86_64 qemu-hw-display-virtio-vga ovmf 2>/dev/null || apk add --no-cache qemu-system-x86_64
COPY run.sh /run.sh
ARG ISO=auton.iso
COPY ${ISO} /auton.iso
ARG WAD=
EXPOSE 4444 5900
ENTRYPOINT ["/bin/sh", "/run.sh"]
