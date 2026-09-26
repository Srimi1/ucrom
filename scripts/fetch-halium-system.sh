#!/bin/bash
# Fetch the Halium Android system image (the "driver host" container) for
# halium-flavor devices from the UBports system-image server, verify its GPG
# signatures, and extract android-rootfs.img.
#
#   scripts/fetch-halium-system.sh [android-version] [outdir]
#     android-version: 13 for the OnePlus 7T Pro on LineageOS 20 (default)
#
# It picks the generic "halium_<ver>_arm64" image from the server's
# channels.json (override with UCROM_HALIUM_CHANNEL / UCROM_HALIUM_DEVICE).
# Then build with:  HALIUM_SYSTEM_IMAGE=<outdir>/android-rootfs.img make device DEVICE=...
#
# Network: needs https://system-image.ubports.com (not reachable from every
# build sandbox; run it on your own machine).
. "$(dirname "$0")/lib.sh"

VER=${1:-13}
OUTD=${2:-$OUT_DIR/halium-system}
SERVER=https://system-image.ubports.com
mkdir -p "$OUTD"
cd "$OUTD"

for t in curl jq gpgv xz tar; do command -v $t >/dev/null || die "need $t"; done

if [ -z "${UCROM_HALIUM_CHANNEL:-}" ] || [ -z "${UCROM_HALIUM_DEVICE:-}" ]; then
    log "looking up a generic halium_${VER}_arm64 image in channels.json"
    retry 3 curl -fsSL -o channels.json "$SERVER/channels.json"
    read -r UCROM_HALIUM_CHANNEL UCROM_HALIUM_DEVICE < <(jq -r --arg d "halium_${VER}_arm64" '
        to_entries[] | select(.value.hidden != true) | .key as $c
        | (.value.devices // {}) | keys[] | select(. == $d) | "\($c) \(.)"' channels.json |
        grep -E "arm64" | sort | tail -1) || true
    [ -n "${UCROM_HALIUM_DEVICE:-}" ] || die "no halium_${VER}_arm64 image listed; set UCROM_HALIUM_CHANNEL/UCROM_HALIUM_DEVICE"
fi
log "channel $UCROM_HALIUM_CHANNEL, device $UCROM_HALIUM_DEVICE"

retry 3 curl -fsSL -o index.json "$SERVER/$UCROM_HALIUM_CHANNEL/$UCROM_HALIUM_DEVICE/index.json"
latest=$(jq '.images | map(select(.type == "full")) | sort_by(.version) | .[-1]' index.json)
[ "$latest" != null ] || die "no full image in index.json"

# Keyrings: the master key signs the signing key, which signs the images.
for k in image-master image-signing; do
    retry 3 curl -fsSLO "$SERVER/gpg/$k.tar.xz"
    retry 3 curl -fsSLO "$SERVER/gpg/$k.tar.xz.asc"
done
mkdir -p keys
tar -xJf image-master.tar.xz -C keys keyring.gpg && mv keys/keyring.gpg keys/master.gpg
gpgv --keyring "$PWD/keys/master.gpg" image-signing.tar.xz.asc image-signing.tar.xz ||
    die "signing keyring signature check failed"
tar -xJf image-signing.tar.xz -C keys keyring.gpg && mv keys/keyring.gpg keys/signing.gpg

found=""
for path in $(jq -r '.files[].path' <<<"$latest"); do
    f=$(basename "$path")
    retry 3 curl -fsSLO "$SERVER/$path"
    retry 3 curl -fsSLO "$SERVER/$path.asc"
    gpgv --keyring "$PWD/keys/signing.gpg" "$f.asc" "$f" || die "$f: bad signature"
    if xz -dc "$f" | tar -t 2>/dev/null | grep -qE 'var/lib/lxc/android/(android-rootfs|system)\.img$'; then
        xz -dc "$f" | tar -x --wildcards 'system/var/lib/lxc/android/*.img' 2>/dev/null ||
        xz -dc "$f" | tar -x --wildcards '*var/lib/lxc/android/*.img'
        found=$(find . -path '*var/lib/lxc/android/*.img' | head -1)
    fi
done
[ -n "$found" ] || die "the image did not contain an Android system image"
mv "$found" android-rootfs.img
sha256sum android-rootfs.img | tee android-rootfs.img.sha256
log "Halium system image: $OUTD/android-rootfs.img"
