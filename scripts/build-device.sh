#!/bin/bash
# Assemble flashable images for one phone.
#
#   scripts/build-device.sh <device> [halium|mainline]
#
# Needs: the flavor rootfs (build-rootfs.sh <flavor>) and the kernel
# (build-kernel.sh, run automatically when missing).
#
# Output in out/devices/<device>/<flavor>/:
#   boot.img       Android boot image (kernel + ucrom initramfs + DTB)
#   dtbo.img       device tree overlays (halium devices that use a dtbo partition)
#   userdata.img   sparse ext4 for `fastboot flash userdata`
#                    mainline: the ucrom root filesystem itself
#                    halium:   holds rootfs.img (Halium file layout)
#   SHA256SUMS, BUILD_INFO, VALIDATION
#
# KEEP_USERDATA=0 deletes userdata.img after it is validated (saves disk on
# build machines; boot.img/dtbo.img are always kept).
. "$(dirname "$0")/lib.sh"
. "$(dirname "$0")/resolve-device.sh"
need_root
ensure_arm64_exec

DEV=${1:?usage: $0 <device> [flavor]}
UCROM_FLAVOR=${2:-} resolve_device "$DEV"
KEEP_USERDATA=${KEEP_USERDATA:-1}

LOWER="$BUILD_DIR/rootfs-$FLAVOR"
[ -d "$LOWER/usr" ] || die "missing $LOWER; run: scripts/build-rootfs.sh $FLAVOR"
KDIR="$OUT_DIR/devices/$DEV/$FLAVOR/kernel"
[ -f "$KDIR/BUILD_INFO" ] || "$UCROM_ROOT/scripts/build-kernel.sh" "$DEV" "$FLAVOR"
DEST="$OUT_DIR/devices/$DEV/$FLAVOR"
STAGE="$BUILD_DIR/stage/$DEV-$FLAVOR"
MERGED="$STAGE/merged"

cleanup() {
    chroot_umount "$MERGED" 2>/dev/null || true
    mountpoint -q "$MERGED" && umount -l "$MERGED"
    return 0
}
trap cleanup EXIT

log "staging $DEV ($DEVICE_NAME, $FLAVOR) on top of rootfs-$FLAVOR"
cleanup
rm -rf "$STAGE"; mkdir -p "$STAGE"/{upper,work,merged}
mount -t overlay overlay -o "lowerdir=$LOWER,upperdir=$STAGE/upper,workdir=$STAGE/work" "$MERGED"

KREL=$(sed -n 's/^release=//p' "$KDIR/BUILD_INFO")

# --- device identity and profile (used by Hardware Check, ucrom-fod, ...)
echo "$DEVICE_CODENAME" > "$MERGED/etc/ucrom-device"
mkdir -p "$MERGED/usr/share/ucrom/devices"
cat "$DEVICE_DIR/device.conf" "$UCROM_ROOT/socs/$SOC_ID/soc.conf" > "$MERGED/usr/share/ucrom/devices/$DEVICE_CODENAME.conf"
echo "ucrom-$DEVICE_CODENAME" > "$MERGED/etc/hostname"

# --- kernel modules
if [ -d "$KDIR/modules-root/lib/modules" ]; then
    mkdir -p "$MERGED/lib/modules"
    cp -a "$KDIR/modules-root/lib/modules/." "$MERGED/lib/modules/"
fi
mkdir -p "$MERGED/lib/modules/$KREL"
chroot_run "$MERGED" depmod -a "$KREL" 2>/dev/null || true

# --- firmware (mainline): proprietary blobs fetched from the device's firmware repo
if [ "$FLAVOR" = mainline ] && [ -n "${DEVICE_FIRMWARE_REPO:-}" ]; then
    fw="$BUILD_DIR/src/firmware-$DEVICE_CODENAME"
    [ -d "$fw/.git" ] || retry 3 git clone -q --depth 1 "$DEVICE_FIRMWARE_REPO" "$fw" || warn "firmware fetch failed"
    if [ -d "$fw/lib/firmware" ]; then cp -a "$fw/lib/firmware/." "$MERGED/lib/firmware/"; fi
fi

# --- initramfs
chroot_mount "$MERGED"
if [ "$FLAVOR" = halium ]; then
    if ! chroot_run "$MERGED" dpkg -s initramfs-tools-halium >/dev/null 2>&1; then
        log "installing Halium initramfs scripts from source"
        src="$BUILD_DIR/src/initramfs-tools-halium"
        [ -d "$src/.git" ] || retry 3 git clone -q --depth 1 -b droidian https://github.com/droidian/initramfs-tools-halium "$src"
        install -D -m 755 "$src/scripts/halium" "$MERGED/usr/share/initramfs-tools/scripts/halium"
        install -D -m 755 "$src/hooks/halium" "$MERGED/usr/share/initramfs-tools/hooks/halium"
        install -D -m 644 "$src/conf/halium" "$MERGED/usr/share/initramfs-tools/conf.d/halium"
    fi
    # The hook copies the unversioned libcrypto.so dev symlink (only present
    # with libssl-dev); use the runtime library instead.
    sed -i -E 's#(libcrypto\.so)$#\1.3#' "$MERGED/usr/share/initramfs-tools/hooks/halium"
    # The Halium hook copies a touchscreen udev rule: ship ucrom's touch-only
    # policy in its place, so keyboards are blocked from the very first second.
    cp "$MERGED/etc/udev/rules.d/90-ucrom-touch-only.rules" "$MERGED/etc/udev/rules.d/90-touchscreen.rules"
    printf 'BOOT=halium\nMODULES=list\nCOMPRESS=gzip\n' > "$MERGED/etc/initramfs-tools/conf.d/ucrom.conf"
else
    printf 'MODULES=most\nCOMPRESS=gzip\n' > "$MERGED/etc/initramfs-tools/conf.d/ucrom.conf"
fi
# initramfs hooks (Halium's) ask dpkg-architecture for the multiarch triplet;
# a build-time shim avoids pulling the whole dpkg-dev toolchain into the phone
SHIM=""
if ! chroot_run "$MERGED" sh -c 'command -v dpkg-architecture' >/dev/null 2>&1; then
    SHIM="$MERGED/usr/bin/dpkg-architecture"
    printf '#!/bin/sh\n# ucrom build-time shim\ncase "$*" in *MULTIARCH*) echo aarch64-linux-gnu ;; *ARCH*) echo arm64 ;; esac\n' > "$SHIM"
    chmod 755 "$SHIM"
fi
mkdir -p "$MERGED/boot"
cp "$KDIR/config" "$MERGED/boot/config-$KREL"
chroot_run "$MERGED" sh -c "mkinitramfs -o /tmp/ucrom-initrd.img $KREL" > "$STAGE/initramfs.log" 2>&1 ||
    die "initramfs failed: $(tail -5 "$STAGE/initramfs.log")"
mkdir -p "$DEST"
cp "$MERGED/tmp/ucrom-initrd.img" "$DEST/initrd.img"
rm -f "$MERGED/tmp/ucrom-initrd.img" "$MERGED/etc/udev/rules.d/90-touchscreen.rules"
[ -z "$SHIM" ] || rm -f "$SHIM"
chroot_umount "$MERGED"

# --- boot.img
if [ "$FLAVOR" = halium ]; then
    CMDLINE="$DEVICE_HALIUM_CMDLINE"
else
    CMDLINE="$DEVICE_MAINLINE_CMDLINE"
fi
KIMG=""
for k in Image.gz Image; do [ -f "$KDIR/$k" ] && { KIMG="$KDIR/$k"; break; }; done
[ -n "$KIMG" ] || die "no kernel image in $KDIR"
DTB="$STAGE/dtb"
if [ "$FLAVOR" = halium ]; then
    # All base DTBs for the SoC; the bootloader picks by msm-id/board-id
    find "$KDIR/dtbs" -name '*.dtb' | sort | xargs cat > "$DTB"
else
    cp "$KDIR/dtbs/$DEVICE_MAINLINE_DTB.dtb" "$DTB" || die "missing DTB $DEVICE_MAINLINE_DTB"
fi
[ -s "$DTB" ] || die "empty DTB"
MKARGS=(--kernel "$KIMG" --ramdisk "$DEST/initrd.img" --cmdline "$CMDLINE"
        --base "$BOOTIMG_BASE" --pagesize "$BOOTIMG_PAGESIZE"
        --kernel_offset "$BOOTIMG_KERNEL_OFFSET" --ramdisk_offset "$BOOTIMG_RAMDISK_OFFSET"
        --tags_offset "$BOOTIMG_TAGS_OFFSET" --header_version "$BOOTIMG_HEADER_VERSION"
        --os_version "${HALIUM_ANDROID_VERSION:-13}.0.0" --os_patch_level 2023-12)
if [ "$BOOTIMG_HEADER_VERSION" -ge 2 ]; then
    MKARGS+=(--dtb "$DTB" --dtb_offset "$BOOTIMG_DTB_OFFSET")
else
    cat "$KIMG" "$DTB" > "$STAGE/kernel-dtb"
    MKARGS[1]="$STAGE/kernel-dtb"
fi
# Ubuntu's mkbootimg imports a gki module it does not ship
PYTHONPATH="$UCROM_ROOT/scripts/tools/pyshim" mkbootimg "${MKARGS[@]}" -o "$DEST/boot.img"
size=$(stat -c %s "$DEST/boot.img")
if [ -n "${DEVICE_BOOT_PARTITION_SIZE:-}" ] && [ "$size" -gt "$DEVICE_BOOT_PARTITION_SIZE" ]; then
    die "boot.img ($size) larger than boot partition ($DEVICE_BOOT_PARTITION_SIZE)"
fi
log "boot.img: $size bytes, header v$BOOTIMG_HEADER_VERSION"

# --- dtbo.img
if [ "$FLAVOR" = halium ] && [ "${HALIUM_SEPARATED_DTBO:-false}" = true ]; then
    mapfile -t dtbos < <(find "$KDIR/dtbo" -name '*.dtbo' | sort)
    [ "${#dtbos[@]}" -gt 0 ] || die "no .dtbo overlays built"
    python3 "$UCROM_ROOT/scripts/tools/mkdtboimg.py" create "$DEST/dtbo.img" --page_size "$BOOTIMG_PAGESIZE" "${dtbos[@]}"
fi

# --- userdata.img
log "creating userdata image"
raw="$STAGE/userdata.raw"
if [ "$FLAVOR" = halium ]; then
    # Halium file layout: /rootfs.img on userdata (found by the initramfs)
    rootimg="$STAGE/rootfs.img"
    truncate -s "$UCROM_ROOTFS_SIZE" "$rootimg"
    mkfs.ext4 -q -F -L ucrom-root -d "$MERGED" "$rootimg"
    mkdir -p "$STAGE/userdata-content"
    mv "$rootimg" "$STAGE/userdata-content/rootfs.img"
    # The Android side (Halium system image). It cannot be built or fetched in
    # every environment; pass HALIUM_SYSTEM_IMAGE=/path/android-rootfs.img
    # (see scripts/fetch-halium-system.sh). Without it the image still boots
    # Linux, but the hardware bridges have no Android drivers to talk to.
    if [ -n "${HALIUM_SYSTEM_IMAGE:-}" ] && [ -f "$HALIUM_SYSTEM_IMAGE" ]; then
        cp "$HALIUM_SYSTEM_IMAGE" "$STAGE/userdata-content/system.img"
        echo "halium_system=included" > "$STAGE/halium-system"
    else
        warn "no HALIUM_SYSTEM_IMAGE given: userdata.img has no Android system image yet"
        echo "halium_system=missing" > "$STAGE/halium-system"
    fi
    truncate -s 12G "$raw"
    mkfs.ext4 -q -F -L userdata -d "$STAGE/userdata-content" "$raw"
    rm -rf "$STAGE/userdata-content"
else
    truncate -s "$UCROM_ROOTFS_SIZE" "$raw"
    mkfs.ext4 -q -F -L userdata -d "$MERGED" "$raw"
fi
umount "$MERGED"
# Disk-frugal: hash the raw image, keep only the sparse one, then prove the
# sparse image expands back to the identical filesystem.
raw_sha=$(sha256sum "$raw" | cut -d' ' -f1)
img2simg "$raw" "$DEST/userdata.img"
rm -f "$raw"
rm -rf "$STAGE/upper" "$STAGE/work"

# --- validation (recorded; tests read it for images not kept on disk)
{
    echo "userdata_sparse_bytes=$(stat -c %s "$DEST/userdata.img")"
    simg2img "$DEST/userdata.img" "$STAGE/check.raw"
    if [ "$(sha256sum "$STAGE/check.raw" | cut -d' ' -f1)" = "$raw_sha" ]; then echo "sparse_roundtrip=ok"; else echo "sparse_roundtrip=FAIL"; fi
    if e2fsck -fn "$STAGE/check.raw" >/dev/null 2>&1; then echo "e2fsck=ok"; else echo "e2fsck=FAIL"; fi
    if [ "$FLAVOR" = halium ]; then
        cat "$STAGE/halium-system"
        debugfs -R "stat /rootfs.img" "$STAGE/check.raw" 2>/dev/null | grep -q "Type: regular" && echo "has_rootfs_img=ok" || echo "has_rootfs_img=FAIL"
    else
        debugfs -R "cat /etc/os-release" "$STAGE/check.raw" 2>/dev/null | grep -q '^ID=ucrom' && echo "rootfs_os_release=ok" || echo "rootfs_os_release=FAIL"
    fi
} > "$DEST/VALIDATION"
rm -f "$STAGE/check.raw"
cat "$DEST/VALIDATION"

(cd "$DEST" && sha256sum ./*.img > SHA256SUMS)
cat > "$DEST/BUILD_INFO" <<EOF
device=$DEV
name=$DEVICE_NAME
soc=$SOC_ID ($SOC_MARKETING)
flavor=$FLAVOR
kernel=$KREL
cmdline=$CMDLINE
bootimg_header=$BOOTIMG_HEADER_VERSION
built=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
if [ "$KEEP_USERDATA" = 0 ]; then
    rm -f "$DEST/userdata.img"
    echo "userdata_kept=no" >> "$DEST/VALIDATION"
fi
rm -rf "$STAGE"
log "images ready in $DEST"
ls -la "$DEST"
