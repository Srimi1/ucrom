#!/bin/bash
# Build the kernel for a device.
#
#   scripts/build-kernel.sh <device> [halium|mainline]
#
# halium:   the phone's LineageOS vendor kernel + socs/common/halium.config
#           + socs/common/kernel-touch-only.config
# mainline: the SoC's mainline tree + base config + mainline.config
#           + kernel-touch-only.config (+ device DTS patch if any)
#
# Output: out/devices/<device>/<flavor>/kernel/
. "$(dirname "$0")/lib.sh"
. "$(dirname "$0")/resolve-device.sh"

DEV=${1:?usage: $0 <device> [flavor]}
UCROM_FLAVOR=${2:-} resolve_device "$DEV"

SRC_DIR="$BUILD_DIR/src/kernel-$SOC_ID-$FLAVOR"
KOUT="$BUILD_DIR/kernel-out/$DEV-$FLAVOR"
DEST="$OUT_DIR/devices/$DEV/$FLAVOR/kernel"
mkdir -p "$KOUT" "$DEST"

if [ "$FLAVOR" = halium ]; then
    REPO=$HALIUM_KERNEL_REPO; REF=$HALIUM_KERNEL_REF
else
    REPO=$MAINLINE_KERNEL_REPO; REF=$MAINLINE_KERNEL_REF
fi
[ -n "$REPO" ] && [ -n "$REF" ] || die "$DEV: no $FLAVOR kernel source defined for $SOC_ID"

if [ ! -d "$SRC_DIR/.git" ]; then
    log "cloning $REPO ($REF)"
    retry 3 git clone --depth 1 -b "$REF" "$REPO" "$SRC_DIR"
fi
COMMIT=$(git -C "$SRC_DIR" rev-parse HEAD)

# ucrom kernel patches (toolchain fixes etc.), applied once, in order
for p in "$UCROM_ROOT"/socs/"$SOC_ID"/patches/"$FLAVOR"/*.patch "$DEVICE_DIR"/patches/"$FLAVOR"/*.patch; do
    [ -e "$p" ] || continue
    if git -C "$SRC_DIR" apply --reverse --check "$p" 2>/dev/null; then
        continue
    fi
    log "applying $(basename "$p")"
    git -C "$SRC_DIR" apply "$p" || die "patch $(basename "$p") does not apply"
done
log "$DEV ($DEVICE_NAME): $FLAVOR kernel $REPO @ $REF ($COMMIT)"

# Old Android kernels pass "--prefix=<dir of ${CROSS_COMPILE}elfedit>" to clang,
# and new clang then looks for unprefixed "as"/"ld" in that dir. Give it a
# private dir where those names are the aarch64 binutils, not the host ones.
TC="$BUILD_DIR/toolchain/aarch64/bin"
if [ ! -x "$TC/as" ]; then
    mkdir -p "$TC"
    for t in as ld ld.bfd nm objcopy objdump readelf strip ar elfedit; do
        ln -sf "$(command -v aarch64-linux-gnu-$t)" "$TC/$t"
        ln -sf "$(command -v aarch64-linux-gnu-$t)" "$TC/aarch64-linux-gnu-$t"
    done
    ln -sf "$(command -v aarch64-linux-gnu-gcc)" "$TC/aarch64-linux-gnu-gcc"
fi

# Toolchain: Ubuntu clang + GNU binutils (what LineageOS builds use, minus
# Google's prebuilt clang). Warnings are not errors: vendor trees are noisy
# with newer compilers.
MAKE=(make -C "$SRC_DIR" O="$KOUT" ARCH=arm64 -j"$(nproc)"
      CC=clang HOSTCC=gcc
      CROSS_COMPILE="$TC/aarch64-linux-gnu-" CROSS_COMPILE_ARM32=arm-linux-gnueabi-
      CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
      KCFLAGS="-Wno-error -w" KBUILD_BUILD_USER=ucrom KBUILD_BUILD_HOST=ucrom)
if grep -q CLANG_TRIPLE "$SRC_DIR/Makefile"; then
    MAKE+=(CLANG_TRIPLE=aarch64-linux-gnu-)
fi
if [ "$FLAVOR" = halium ]; then
    # shellcheck disable=SC2206
    MAKE+=(${HALIUM_MAKE_FLAGS:-} CONFIG_SECTION_MISMATCH_WARN_ONLY=y)
fi

FRAGMENTS=()
if [ "$FLAVOR" = halium ]; then
    log "defconfig: $HALIUM_DEFCONFIG"
    "${MAKE[@]}" "$HALIUM_DEFCONFIG"
    FRAGMENTS+=("$UCROM_ROOT/socs/common/halium.config")
else
    if [ -n "${MAINLINE_CONFIG_URL:-}" ]; then
        log "base config: $MAINLINE_CONFIG_URL"
        retry 3 curl -fsSL -o "$KOUT/.config" "$MAINLINE_CONFIG_URL"
        "${MAKE[@]}" olddefconfig
    else
        # shellcheck disable=SC2086
        "${MAKE[@]}" $MAINLINE_DEFCONFIG
    fi
    FRAGMENTS+=("$UCROM_ROOT/socs/common/mainline.config")
    if [ -n "${DEVICE_MAINLINE_DTS_PATCH:-}" ]; then
        dts="$DEVICE_DIR/$DEVICE_MAINLINE_DTS_PATCH"
        log "adding device tree $(basename "$dts")"
        cp "$dts" "$SRC_DIR/arch/arm64/boot/dts/qcom/"
        mk="$SRC_DIR/arch/arm64/boot/dts/qcom/Makefile"
        dtb="$(basename "${dts%.dts}").dtb"
        grep -q "$dtb" "$mk" || echo "dtb-\$(CONFIG_ARCH_QCOM)	+= $dtb" >> "$mk"
    fi
fi
FRAGMENTS+=("$UCROM_ROOT/socs/common/kernel-touch-only.config")
[ -f "$UCROM_ROOT/socs/$SOC_ID/$FLAVOR.config" ] && FRAGMENTS+=("$UCROM_ROOT/socs/$SOC_ID/$FLAVOR.config")
[ -f "$DEVICE_DIR/$FLAVOR.config" ] && FRAGMENTS+=("$DEVICE_DIR/$FLAVOR.config")

log "merging fragments: ${FRAGMENTS[*]##*/}"
(cd "$KOUT" && ARCH=arm64 "$SRC_DIR/scripts/kconfig/merge_config.sh" -m -O "$KOUT" "$KOUT/.config" "${FRAGMENTS[@]}" >/dev/null)
"${MAKE[@]}" olddefconfig

# Fail early if a fragment option silently didn't stick (dependency missing)
missing=0
for frag in "${FRAGMENTS[@]}"; do
    while IFS= read -r line; do
        case "$line" in
            CONFIG_*=*) want=$line ;;
            "# CONFIG_"*" is not set") want=$line ;;
            *) continue ;;
        esac
        sym=$(sed -E 's/^# (CONFIG_[A-Za-z0-9_]+) is not set$/\1/; s/^(CONFIG_[A-Za-z0-9_]+)=.*/\1/' <<<"$want")
        got=$(grep -E "^$sym=|^# $sym is not set" "$KOUT/.config" || echo "# $sym is not set")
        # "=n"-style: not set means absent from .config too
        if [ "$want" != "$got" ]; then
            if [[ $want == "# "* ]] && ! grep -qE "^$sym=" "$KOUT/.config"; then continue; fi
            if ! grep -q "config ${sym#CONFIG_}\$" -r "$SRC_DIR" --include='Kconfig*' 2>/dev/null; then
                echo "  (option $sym does not exist in this kernel, skipped)" >&2; continue
            fi
            warn "fragment option not applied: want '$want', got '$got'"
            missing=$((missing + 1))
        fi
    done < "$frag"
done
echo "$missing" > "$DEST/fragment-mismatches"

# KERNEL_TARGETS=dtbs (or a single "qcom/x.dtb") builds device trees only:
# used to validate device trees for phones without a full kernel build.
TARGETS=()
if [ -n "${KERNEL_TARGETS:-}" ]; then
    # shellcheck disable=SC2206
    TARGETS=($KERNEL_TARGETS)
    log "building only: ${TARGETS[*]}"
else
    log "compiling (this takes a while)"
fi
rc=0
"${MAKE[@]}" "${TARGETS[@]}" > "$KOUT/build.log" 2>&1 || rc=$?
grep -E "error:|Error [0-9]|warning: unmet" "$KOUT/build.log" | head -50 || true
[ "$rc" = 0 ] || die "kernel build failed (rc=$rc); see $KOUT/build.log"

KREL=$(cat "$KOUT/include/config/kernel.release" 2>/dev/null || echo "dtbs-only")
log "kernel $KREL built"

rm -rf "${DEST:?}"/*
cp "$KOUT/.config" "$DEST/config"
for img in Image-dtb Image.gz-dtb Image.gz Image; do
    if [ -f "$KOUT/arch/arm64/boot/$img" ]; then cp "$KOUT/arch/arm64/boot/$img" "$DEST/"; fi
done
mkdir -p "$DEST/dtbs" "$DEST/dtbo"
(cd "$KOUT/arch/arm64/boot/dts" && find . -name '*.dtb' -exec cp --parents {} "$DEST/dtbs/" \;)
(cd "$KOUT/arch/arm64/boot/dts" && find . -name '*.dtbo' -exec cp --parents {} "$DEST/dtbo/" \;)
if [ -z "${KERNEL_TARGETS:-}" ] && grep -q '^CONFIG_MODULES=y' "$KOUT/.config"; then
    "${MAKE[@]}" INSTALL_MOD_PATH="$DEST/modules-root" INSTALL_MOD_STRIP=1 modules_install >/dev/null
fi
cat > "$DEST/BUILD_INFO" <<EOF
device=$DEV
name=$DEVICE_NAME
soc=$SOC_ID ($SOC_MARKETING)
flavor=$FLAVOR
repo=$REPO
ref=$REF
commit=$COMMIT
release=$KREL
compiler=$(clang --version | head -1)
fragments=${FRAGMENTS[*]##*/}
fragment_mismatches=$missing
targets=${KERNEL_TARGETS:-all}
EOF
log "kernel artifacts in $DEST"
