#!/bin/bash
# Build the Halium Android system image yourself (alternative to
# fetch-halium-system.sh). Needs a Linux PC with ~250 GB free disk, 16+ GB
# RAM and several hours: it syncs the LineageOS 20 tree with the Halium
# patches and builds the generic system image ("halium_arm64").
#
#   scripts/build-halium-system.sh /path/to/workdir
#
# NOTE: reference steps, not run in the ucrom CI (the tree is too big for it).
# Branch names follow LineageOS 20 / Halium 13; check them against the
# current Halium docs before a long build. fetch-halium-system.sh is the
# recommended path.
set -euo pipefail
W=${1:?usage: $0 <workdir with 250 GB free>}
command -v repo >/dev/null || { echo "install the 'repo' tool first"; exit 1; }
mkdir -p "$W" && cd "$W"
repo init -u https://github.com/LineageOS/android.git -b lineage-20.0 --git-lfs --depth=1
repo sync -c -j"$(nproc)" --no-tags --no-clone-bundle
# Halium patches + generic arm64 target from the UBports/Halium project
git clone --depth 1 https://gitlab.com/ubports/porting/community-ports/halium-generic-adaptation-build-tools halium-tools
[ -d halium ] || git clone --depth 1 -b halium-13.0 https://github.com/Halium/android.git halium
./halium/halium/devices/setup halium_arm64 2>/dev/null || true
source build/envsetup.sh
lunch halium_arm64-userdebug
m systemimage
echo "system image: $W/out/target/product/*/system.img"
echo "use it with: HALIUM_SYSTEM_IMAGE=<that file> make device DEVICE=oneplus-hotdog"
