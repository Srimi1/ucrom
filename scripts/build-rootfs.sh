#!/bin/bash
# Build the ucrom root filesystem.
#
#   scripts/build-rootfs.sh common          Ubuntu base + Phosh + apps + ucrom policy
#   scripts/build-rootfs.sh mainline        common + mainline hardware flavor (also the QEMU image)
#   scripts/build-rootfs.sh halium          common + Halium bridge flavor (7T Pro and friends)
#
# The common layer is cached as build/rootfs-common.tar.zst and reused.
. "$(dirname "$0")/lib.sh"
need_root

FLAVOR="${1:-common}"
case "$FLAVOR" in common|mainline|halium) ;; *) die "unknown flavor: $FLAVOR" ;; esac

COMMON_TAR="$BUILD_DIR/rootfs-common.tar.zst"
ROOT="$BUILD_DIR/rootfs-$FLAVOR"

cleanup() { chroot_umount "$ROOT"; }
trap cleanup EXIT

apt_install() {
    chroot_run "$ROOT" apt-get install -y --no-install-recommends \
        -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "$@"
}

run_hooks() {
    local stage=$1 hook
    mkdir -p "$ROOT/tmp/ucrom-hooks"
    cp "$UCROM_ROOT"/config/ucrom.conf "$ROOT/tmp/ucrom-hooks/ucrom.conf"
    for hook in "$UCROM_ROOT"/rootfs/hooks/"$stage"-*.chroot; do
        [ -e "$hook" ] || continue
        log "hook: $(basename "$hook")"
        cp "$hook" "$ROOT/tmp/ucrom-hooks/"
        chroot_run "$ROOT" /bin/bash -e "/tmp/ucrom-hooks/$(basename "$hook")"
    done
    rm -rf "$ROOT/tmp/ucrom-hooks"
}

# Copy repo content that lives inside the image: overlay, ucrom apps and daemons
install_ucrom_files() {
    rsync -a --chown=root:root "$UCROM_ROOT/rootfs/overlay/" "$ROOT/"
    mkdir -p "$ROOT/usr/lib/ucrom"
    rsync -a --delete --chown=root:root --exclude '__pycache__' \
        "$UCROM_ROOT/apps/" "$ROOT/usr/lib/ucrom/apps/"
    rsync -a --delete --chown=root:root --exclude '__pycache__' --exclude 'tests' \
        "$UCROM_ROOT/ucrom/" "$ROOT/usr/lib/ucrom/daemons/"
}

build_common() {
    ensure_arm64_exec
    rm -rf "$ROOT"; mkdir -p "$ROOT"
    log "bootstrapping Ubuntu $UCROM_SUITE $UCROM_ARCH from $UCROM_MIRROR"
    retry 3 mmdebstrap --mode=root --variant=minbase --arch="$UCROM_ARCH" \
        --components="${UCROM_COMPONENTS//,/ }" \
        --include=ca-certificates,apt-utils,gnupg \
        --aptopt='Acquire::Retries "5"' \
        --aptopt='APT::Install-Recommends "false"' \
        "$UCROM_SUITE" "$ROOT" \
        "deb $UCROM_MIRROR $UCROM_SUITE ${UCROM_COMPONENTS//,/ }" \
        "deb $UCROM_MIRROR $UCROM_SUITE-updates ${UCROM_COMPONENTS//,/ }" \
        "deb $UCROM_MIRROR $UCROM_SUITE-security ${UCROM_COMPONENTS//,/ }"

    chroot_mount "$ROOT"
    build_ca_install "$ROOT"
    # Never start services inside the build chroot
    printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"; chmod +x "$ROOT/usr/sbin/policy-rc.d"

    retry 3 chroot_run "$ROOT" apt-get update
    local pkgs
    pkgs=$(read_list "$UCROM_ROOT"/config/packages/{base,phosh,apps}.list)
    log "installing $(wc -w <<<"$pkgs") packages"
    # shellcheck disable=SC2086
    retry 2 apt_install $pkgs

    install_ucrom_files
    run_hooks 1
    rm -f "$ROOT/usr/sbin/policy-rc.d"
    build_ca_remove "$ROOT"
    chroot_run "$ROOT" apt-get clean
    chroot_umount "$ROOT"

    log "caching common layer -> $COMMON_TAR"
    tar -C "$ROOT" --numeric-owner --xattrs --acls -I 'zstd -T0 -3' -cpf "$COMMON_TAR" .
}

build_flavor() {
    [ -f "$COMMON_TAR" ] || { FLAVOR=common ROOT="$BUILD_DIR/rootfs-common" build_common; }
    ensure_arm64_exec
    rm -rf "$ROOT"; mkdir -p "$ROOT"
    log "unpacking common layer into $ROOT"
    tar -C "$ROOT" --numeric-owner --xattrs --acls -I zstd -xpf "$COMMON_TAR"
    chroot_mount "$ROOT"
    build_ca_install "$ROOT"
    printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"; chmod +x "$ROOT/usr/sbin/policy-rc.d"

    # Refresh ucrom files so edits don't need a full rebuild
    install_ucrom_files
    retry 3 chroot_run "$ROOT" apt-get update
    local pkgs
    # common lists again (cheap no-op when unchanged) so list edits apply
    # without rebuilding the cached common layer, then the flavor list
    pkgs=$(read_list "$UCROM_ROOT"/config/packages/{base,phosh,apps}.list "$UCROM_ROOT/config/packages/$FLAVOR.list")
    # shellcheck disable=SC2086
    [ -z "$pkgs" ] || retry 2 apt_install $pkgs

    if [ "$FLAVOR" = halium ] && compgen -G "$OUT_DIR/bridges/*.deb" >/dev/null; then
        log "installing Halium bridge packages"
        mkdir -p "$ROOT/tmp/bridges"
        cp "$OUT_DIR"/bridges/*.deb "$ROOT/tmp/bridges/"
        chroot_run "$ROOT" sh -c 'apt-get install -y --no-install-recommends /tmp/bridges/*.deb'
        rm -rf "$ROOT/tmp/bridges"
    fi

    echo "$FLAVOR" > "$ROOT/etc/ucrom-flavor"
    run_hooks 1
    run_hooks 2
    run_hooks "$FLAVOR"
    rm -f "$ROOT/usr/sbin/policy-rc.d"
    build_ca_remove "$ROOT"
    chroot_run "$ROOT" apt-get clean
    chroot_umount "$ROOT"
    log "rootfs ready: $ROOT"
}

if [ "$FLAVOR" = common ]; then build_common; else build_flavor; fi
