# The host that boots a packaged application as a virtual machine (w23 C3).
# QEMU `virt` on the Rancher VM's architecture. With /dev/kvm it uses KVM; without,
# software emulation (TCG), which is slow but runs the same guest.
FROM alpine:3.23
RUN apk add --no-cache qemu-system-aarch64 qemu-system-x86_64 linux-virt busybox-static cpio gzip python3 \
 && mkdir -p /opt/vm && cp /boot/vmlinuz-virt /opt/vm/kernel \
 && for m in net/core/failover drivers/net/net_failover drivers/net/virtio_net; do \
      gunzip -c /lib/modules/*/kernel/$m.ko.gz > /opt/vm/$(basename $m).ko; done \
 && cp /bin/busybox.static /opt/vm/busybox
COPY boot.py /opt/vm/boot.py
ENTRYPOINT ["python3", "/opt/vm/boot.py"]
