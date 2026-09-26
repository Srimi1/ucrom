"""ucrom-alertslider: the OnePlus 3-position alert slider.

The vendor kernel's tri-state key driver ("oplus,hall_tri_state_key", older
kernels "tri-state-key") reports KEY_F3 with the value set to the position:
    1 = up (silent), 2 = middle (vibrate), 3 = down (ring)
The current position is also readable from /proc/tristatekey/tri_state.

The slider sets the feedbackd profile (the one Phosh uses for all sounds and
haptics): silent / quiet (vibrate only) / full (ring).
"""

import argparse
import logging
import subprocess
import sys
import time

import evdev

from . import read_text, write_state
from .inputdev import find_device

DEVICE_NAMES = ("oplus,hall_tri_state_key", "tri-state-key", "tri_state_key")
POSITIONS = {1: ("up", "silent"), 2: ("middle", "quiet"), 3: ("down", "full")}
PROC_STATE = "/proc/tristatekey/tri_state"

log = logging.getLogger("ucrom-alertslider")


def apply_profile(position: int) -> str:
    where, profile = POSITIONS[position]
    log.info("alert slider %s -> feedback profile '%s'", where, profile)
    # feedbackd owns the profile; gsettings is the persistent knob Phosh uses
    subprocess.run(["gsettings", "set", "org.sigxcpu.feedbackd", "profile", profile],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    write_state("alertslider", f"{where} {profile}")
    return profile


def initial_position():
    raw = read_text(PROC_STATE)
    try:
        pos = int(raw)
    except ValueError:
        return None
    return pos if pos in POSITIONS else None


def run(once: bool = False) -> int:
    pos = initial_position()
    if pos:
        apply_profile(pos)
    dev = None
    while dev is None:
        dev = find_device(DEVICE_NAMES)
        if dev is None:
            if once:
                log.warning("no alert slider on this device")
                return 1
            log.info("waiting for the alert slider input device")
            time.sleep(10)
    log.info("listening on %s (%s)", dev.path, dev.name)
    write_state("alertslider-device", dev.name)
    for ev in dev.read_loop():
        if ev.type == evdev.ecodes.EV_KEY and ev.code == evdev.ecodes.KEY_F3 and ev.value in POSITIONS:
            apply_profile(ev.value)
            if once:
                return 0
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="handle one event and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    return run(args.once)


if __name__ == "__main__":
    sys.exit(main())
