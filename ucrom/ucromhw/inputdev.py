"""Find kernel input devices by name, honoring UCROM_HW_ROOT for tests."""

import os
from pathlib import Path

import evdev

from . import hw_root


def find_device(names):
    """Return an evdev.InputDevice whose name is in `names`, or None.

    With UCROM_HW_ROOT set, devices listed in <root>/ucrom-input-map
    ("<name>=<path>" lines) are used instead of scanning /dev/input, so
    tests can hand in uinput devices they created.
    """
    names = set(names)
    mapping = hw_root() / "ucrom-input-map"
    if os.environ.get("UCROM_HW_ROOT") and mapping.exists():
        for line in mapping.read_text().splitlines():
            name, _, path = line.partition("=")
            if name in names:
                return evdev.InputDevice(path)
        return None
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if dev.name in names:
            return dev
        dev.close()
    return None
