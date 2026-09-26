#!/bin/bash
# Flash ucrom to a phone over USB with fastboot. Run on your own computer,
# with the phone in fastboot mode (Power + Volume Up + Volume Down).
#
#   scripts/flash.sh <device> [--try]
#     --try   boot ucrom from RAM once (fastboot boot): nothing is written
#             except userdata. Reboot = back to your previous system.
#
# READ docs/FLASHING.md FIRST. Flashing erases the phone's user data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/resolve-device.sh"
DEV=${1:?usage: $0 <device> [--try]}
MODE=${2:-}
resolve_device "$DEV"
D="$ROOT/out/devices/$DEV/$FLAVOR"
for f in boot.img userdata.img; do [ -f "$D/$f" ] || { echo "missing $D/$f (run make device DEVICE=$DEV)"; exit 1; }; done
(cd "$D" && sha256sum -c SHA256SUMS --ignore-missing) || { echo "checksum mismatch"; exit 1; }
command -v fastboot >/dev/null || { echo "install fastboot (android-sdk-platform-tools)"; exit 1; }

product=$(fastboot getvar product 2>&1 | sed -n 's/^product: *//p')
echo "phone reports product: '$product' (expected for $DEVICE_NAME: $DEVICE_CODENAME / msmnile)"
unlocked=$(fastboot getvar unlocked 2>&1 | sed -n 's/^unlocked: *//p')
[ "$unlocked" = yes ] || { echo "bootloader is locked; see docs/FLASHING.md"; exit 1; }

echo
echo "This ERASES userdata on the phone (apps, photos, files)."
read -r -p "Type ERASE to continue: " ok
[ "$ok" = ERASE ] || exit 1

fastboot flash userdata "$D/userdata.img"
if [ "$MODE" = --try ]; then
    fastboot boot "$D/boot.img"
    echo "Booting ucrom from RAM. Your boot partition was not changed."
    exit 0
fi
if [ "${DEVICE_AB:-false}" = true ]; then
    slot=$(fastboot getvar current-slot 2>&1 | sed -n 's/^current-slot: *//p')
    echo "flashing boot on slot ${slot:-a}"
fi
fastboot flash boot "$D/boot.img"
[ -f "$D/dtbo.img" ] && fastboot flash dtbo "$D/dtbo.img"
fastboot reboot
