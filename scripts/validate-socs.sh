#!/bin/bash
# Validate every chip and phone profile against the real kernel trees,
# without a full clone per tree (tree-only partial clones):
#   * device.conf -> soc.conf resolves, required keys present
#   * each kernel repo/branch exists
#   * each halium defconfig exists in its tree
#   * each mainline device tree (.dts) exists in its tree, or is shipped by
#     ucrom as a patch (devices/<dev>/dts/)
#
# Output: out/validate-socs.json (read by tests/test_soc_matrix.py)
. "$(dirname "$0")/lib.sh"
. "$(dirname "$0")/resolve-device.sh"

CACHE="$BUILD_DIR/treecache"
mkdir -p "$CACHE"
RESULT="$OUT_DIR/validate-socs.json"

# tree_has <repo> <ref> <path>  -> 0 if the path exists at that ref
tree_has() {
    local repo=$1 ref=$2 path=$3
    local dir="$CACHE/$(echo "$repo@$ref" | sha1sum | cut -c1-16)"
    if [ ! -d "$dir" ]; then
        retry 3 git clone -q --filter=blob:none --no-checkout --depth 1 -b "$ref" "$repo" "$dir" >/dev/null 2>&1 || return 2
    fi
    git -C "$dir" cat-file -e "HEAD:$path" 2>/dev/null
}

ref_exists() {
    git ls-remote --exit-code "$1" "refs/heads/$2" "refs/tags/$2" >/dev/null 2>&1
}

py_rows=()
add() { py_rows+=("$(printf '%s\t' "$@")"); }

for conf in "$UCROM_ROOT"/devices/*/device.conf; do
    dev=$(basename "$(dirname "$conf")")
    (
        unset "${!DEVICE_@}" "${!MAINLINE_@}" "${!HALIUM_@}" "${!BOOTIMG_@}" "${!SOC_@}"
        if ! resolve_device "$dev" 2>/dev/null; then
            printf '%s\tresolve\tFAIL\tprofile does not resolve\n' "$dev"; exit 0
        fi
        printf '%s\tresolve\tOK\t%s / %s\n' "$dev" "$SOC_MARKETING" "$FLAVOR"
        for fl in $SOC_FLAVORS; do
            if [ "$fl" = halium ]; then repo=$HALIUM_KERNEL_REPO; ref=$HALIUM_KERNEL_REF
            else repo=$MAINLINE_KERNEL_REPO; ref=$MAINLINE_KERNEL_REF; fi
            if [ -z "$repo" ] || [ -z "$ref" ]; then
                printf '%s\t%s-kernel\tNONE\tno %s kernel published for %s\n' "$dev" "$fl" "$fl" "$SOC_ID"; continue
            fi
            if ref_exists "$repo" "$ref"; then
                printf '%s\t%s-kernel\tOK\t%s @ %s\n' "$dev" "$fl" "$repo" "$ref"
            else
                printf '%s\t%s-kernel\tFAIL\t%s @ %s not found\n' "$dev" "$fl" "$repo" "$ref"; continue
            fi
            if [ "$fl" = halium ] && [ "$HALIUM_DEFCONFIG" != gki_defconfig ]; then
                if tree_has "$repo" "$ref" "arch/arm64/configs/$HALIUM_DEFCONFIG"; then
                    printf '%s\thalium-defconfig\tOK\t%s\n' "$dev" "$HALIUM_DEFCONFIG"
                else
                    printf '%s\thalium-defconfig\tFAIL\t%s missing\n' "$dev" "$HALIUM_DEFCONFIG"
                fi
            fi
            if [ "$fl" = mainline ] && [ -n "${DEVICE_MAINLINE_DTB:-}" ]; then
                if [ -n "${DEVICE_MAINLINE_DTS_PATCH:-}" ] && [ -f "$DEVICE_DIR/$DEVICE_MAINLINE_DTS_PATCH" ]; then
                    printf '%s\tmainline-dts\tOK\t%s (shipped by ucrom)\n' "$dev" "$DEVICE_MAINLINE_DTB"
                elif tree_has "$repo" "$ref" "arch/arm64/boot/dts/$DEVICE_MAINLINE_DTB.dts"; then
                    printf '%s\tmainline-dts\tOK\t%s\n' "$dev" "$DEVICE_MAINLINE_DTB"
                else
                    printf '%s\tmainline-dts\tFAIL\t%s.dts not in tree\n' "$dev" "$DEVICE_MAINLINE_DTB"
                fi
            fi
        done
    )
done | tee "$BUILD_DIR/validate-socs.tsv"

python3 - "$BUILD_DIR/validate-socs.tsv" "$RESULT" <<'EOF'
import json, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1]) if l.strip()]
out = [{"device": r[0], "check": r[1], "result": r[2], "detail": r[3] if len(r) > 3 else ""} for r in rows]
json.dump(out, open(sys.argv[2], "w"), indent=1)
fails = [o for o in out if o["result"] == "FAIL"]
print(f"{len(out)} checks, {len(fails)} failed")
EOF
log "results: $RESULT"
