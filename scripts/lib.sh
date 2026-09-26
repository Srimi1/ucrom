#!/bin/bash
# Shared helpers for ucrom build scripts.
set -euo pipefail

UCROM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../config/ucrom.conf
. "$UCROM_ROOT/config/ucrom.conf"

BUILD_DIR="${BUILD_DIR:-$UCROM_ROOT/build}"
OUT_DIR="${OUT_DIR:-$UCROM_ROOT/out}"
mkdir -p "$BUILD_DIR" "$OUT_DIR"

log()  { printf '\033[1;34m[ucrom]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[ucrom] warning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[ucrom] error:\033[0m %s\n' "$*" >&2; exit 1; }

need_root() { [ "$(id -u)" = 0 ] || die "this step needs root (try: sudo make ...)"; }

# retry <attempts> <cmd...>: retry with exponential backoff (network steps)
retry() {
    local n=$1 delay=2 i; shift
    for ((i = 1; i <= n; i++)); do
        "$@" && return 0
        [ "$i" -lt "$n" ] || break
        warn "attempt $i/$n failed: $*; retrying in ${delay}s"
        sleep "$delay"; delay=$((delay * 2))
    done
    return 1
}

# read_list <file...>: package names from list files, comments stripped
read_list() { sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$@" | tr -s '[:space:]' ' '; }

# ensure_arm64_exec: make sure this host can run arm64 binaries (binfmt+qemu)
ensure_arm64_exec() {
    [ "$(uname -m)" = aarch64 ] && return 0
    if [ ! -e /proc/sys/fs/binfmt_misc/register ]; then
        mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc 2>/dev/null ||
            die "binfmt_misc unavailable; build on an arm64 host or a VM"
    fi
    if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
        [ -f /usr/lib/binfmt.d/qemu-aarch64.conf ] || die "install qemu-user-static"
        cat /usr/lib/binfmt.d/qemu-aarch64.conf > /proc/sys/fs/binfmt_misc/register
    fi
}

# chroot mounts
chroot_mount() {
    local r=$1
    mount -t proc proc "$r/proc"
    mount -t sysfs sys "$r/sys"
    mount --bind /dev "$r/dev"
    mount --bind /dev/pts "$r/dev/pts"
    mount -t tmpfs tmpfs "$r/run"
    mkdir -p "$r/run/systemd"
    [ -e "$r/etc/resolv.conf" ] && cp -L --remove-destination /etc/resolv.conf "$r/etc/resolv.conf" 2>/dev/null || true
}
chroot_umount() {
    local r=$1 m
    for m in run dev/pts dev sys proc; do
        mountpoint -q "$r/$m" && umount -l "$r/$m"
    done
    return 0
}

# chroot_run <root> <cmd...>: run in chroot with proxy env passed through
chroot_run() {
    local r=$1; shift
    env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8 \
        DEBIAN_FRONTEND=noninteractive \
        http_proxy="${http_proxy:-${HTTP_PROXY:-}}" https_proxy="${https_proxy:-${HTTPS_PROXY:-}}" \
        HTTP_PROXY="${HTTP_PROXY:-}" HTTPS_PROXY="${HTTPS_PROXY:-}" \
        no_proxy="${no_proxy:-}" NO_PROXY="${NO_PROXY:-}" \
        npm_config_https_proxy="${https_proxy:-${HTTPS_PROXY:-}}" npm_config_noproxy="${no_proxy:-}" \
        chroot "$r" "$@"
}

# Build hosts behind a TLS-intercepting proxy: trust its CA inside the chroot
# only while building. UCROM_BUILD_CA defaults to $SSL_CERT_FILE if set.
BUILD_CA_NAME="ucrom-build-proxy-ca.crt"
build_ca_install() {
    local r=$1 ca="${UCROM_BUILD_CA:-${SSL_CERT_FILE:-}}"
    [ -n "$ca" ] && [ -f "$ca" ] || return 0
    mkdir -p "$r/usr/local/share/ca-certificates"
    cp "$ca" "$r/usr/local/share/ca-certificates/$BUILD_CA_NAME"
    if [ -x "$r/usr/sbin/update-ca-certificates" ]; then
        chroot_run "$r" update-ca-certificates >/dev/null 2>&1 || true
    fi
}
build_ca_remove() {
    local r=$1
    [ -f "$r/usr/local/share/ca-certificates/$BUILD_CA_NAME" ] || return 0
    rm -f "$r/usr/local/share/ca-certificates/$BUILD_CA_NAME"
    chroot_run "$r" update-ca-certificates --fresh >/dev/null 2>&1 || true
}
