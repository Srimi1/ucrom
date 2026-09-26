#!/bin/bash
# Build the ucrom emulator image: the mainline-flavor rootfs plus Ubuntu's
# generic arm64 kernel (virtio drivers) instead of a phone kernel.
#
# Output: out/qemu/{ucrom-qemu.qcow2,vmlinuz,initrd.img,SHA256SUMS}
. "$(dirname "$0")/lib.sh"
need_root
ensure_arm64_exec

ROOT="$BUILD_DIR/rootfs-mainline"
[ -d "$ROOT/usr" ] || die "run: scripts/build-rootfs.sh mainline"
DEST="$OUT_DIR/qemu"
mkdir -p "$DEST"

cleanup() { chroot_umount "$ROOT"; }
trap cleanup EXIT

log "installing the generic arm64 kernel (emulator only)"
chroot_mount "$ROOT"
build_ca_install "$ROOT"
printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"; chmod +x "$ROOT/usr/sbin/policy-rc.d"
retry 3 chroot_run "$ROOT" apt-get install -y --no-install-recommends linux-image-generic
kver=$(ls "$ROOT/lib/modules" | sort -V | tail -1)
chroot_run "$ROOT" update-initramfs -c -k "$kver" 2>/dev/null || chroot_run "$ROOT" update-initramfs -u -k "$kver"
cp "$ROOT/boot/vmlinuz-$kver" "$DEST/vmlinuz"
cp "$ROOT/boot/initrd.img-$kver" "$DEST/initrd.img"
chmod 644 "$DEST/vmlinuz" "$DEST/initrd.img"
rm -f "$ROOT/usr/sbin/policy-rc.d"
build_ca_remove "$ROOT"
chroot_umount "$ROOT"

log "creating ext4 image ($UCROM_ROOTFS_SIZE)"
raw="$BUILD_DIR/ucrom-qemu.raw"
rm -f "$raw"
truncate -s "$UCROM_ROOTFS_SIZE" "$raw"
mkfs.ext4 -q -F -L ucrom-root -E root_owner=0:0 -d "$ROOT" "$raw"
qemu-img convert -O qcow2 -c "$raw" "$DEST/ucrom-qemu.qcow2"
rm -f "$raw"

log "removing the emulator kernel from the shared rootfs again"
chroot_mount "$ROOT"
chroot_run "$ROOT" sh -c 'apt-get purge -y "linux-image-*" "linux-modules-*" linux-generic linux-image-generic >/dev/null 2>&1; apt-get autoremove -y --purge >/dev/null 2>&1' || true
chroot_umount "$ROOT"

(cd "$DEST" && sha256sum ucrom-qemu.qcow2 vmlinuz initrd.img > SHA256SUMS)
echo "$kver" > "$DEST/KERNEL_VERSION"
log "emulator image ready in $DEST (kernel $kver)"
cat "$DEST/SHA256SUMS"
