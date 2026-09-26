#!/bin/bash
# Resolve a device profile: devices/<dev>/device.conf -> socs/<soc>/soc.conf.
#
#   scripts/resolve-device.sh oneplus-hotdog          print merged variables
#   scripts/resolve-device.sh --list                  table of all devices
#   . scripts/resolve-device.sh; resolve_device X     (from other scripts)
set -euo pipefail
_UC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

resolve_device() {
    local dev=$1
    local dconf="$_UC_ROOT/devices/$dev/device.conf"
    [ -f "$dconf" ] || { echo "unknown device: $dev (see: make list-devices)" >&2; return 1; }
    # shellcheck disable=SC1090
    . "$dconf"
    local sconf="$_UC_ROOT/socs/$DEVICE_SOC/soc.conf"
    [ -f "$sconf" ] || { echo "$dev: unknown SoC $DEVICE_SOC" >&2; return 1; }
    # shellcheck disable=SC1090
    . "$sconf"
    DEVICE_ID=$dev
    DEVICE_DIR="$_UC_ROOT/devices/$dev"
    FLAVOR="${UCROM_FLAVOR:-$DEVICE_FLAVOR}"
    case " $SOC_FLAVORS " in *" $FLAVOR "*) ;; *)
        echo "$dev: flavor '$FLAVOR' not offered by $SOC_ID ($SOC_FLAVORS)" >&2; return 1 ;;
    esac
    local k
    for k in DEVICE_CODENAME DEVICE_NAME DEVICE_SOC DEVICE_FLAVOR DEVICE_SCREEN_W DEVICE_SCREEN_H SOC_ID SOC_MARKETING; do
        [ -n "${!k:-}" ] || { echo "$dev: missing $k" >&2; return 1; }
    done
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    if [ "${1:-}" = --list ]; then
        printf '%-24s %-40s %-22s %-9s %s\n' DEVICE NAME CHIP FLAVOR TIER
        for d in "$_UC_ROOT"/devices/*/device.conf; do
            dev=$(basename "$(dirname "$d")")
            ( resolve_device "$dev" && printf '%-24s %-40s %-22s %-9s %s\n' \
                "$dev" "$DEVICE_NAME" "$SOC_MARKETING" "$FLAVOR" "$DEVICE_TIER" )
        done
    else
        resolve_device "${1:?usage: $0 <device>|--list}"
        set | grep -E '^(DEVICE|SOC|MAINLINE|HALIUM|BOOTIMG)_|^FLAVOR=' | sort
    fi
fi
