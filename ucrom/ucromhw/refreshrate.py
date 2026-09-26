"""ucrom-refresh-rate: choose the panel refresh rate (e.g. 60/90 Hz).

Reads the wanted rate from ~/.config/ucrom/refresh-rate (written by
Settings/Hardware Check, default: the highest the device profile lists) and
applies it to the built-in panel with wlr-randr, picking the output mode with
the panel's current resolution and the closest refresh rate.
"""

import argparse
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("ucrom-refresh-rate")
PREF = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ucrom" / "refresh-rate"


def parse_modes(text):
    """Parse `wlr-randr` output -> {output: [(w, h, hz, current)]}."""
    outputs, cur = {}, None
    for line in text.splitlines():
        if line and not line[0].isspace():
            cur = line.split()[0]
            outputs[cur] = []
        m = re.match(r"\s+(\d+)x(\d+) px, ([\d.]+) Hz(.*)", line)
        if m and cur:
            outputs[cur].append((int(m[1]), int(m[2]), float(m[3]), "current" in m[4]))
    return outputs


def pick(modes, want_hz):
    """Only the refresh rate changes: keep the panel's current resolution
    (outputs can list far larger modes than the panel really has)."""
    if not modes:
        return None
    current = [m for m in modes if m[3]]
    w, h = (current[0][0], current[0][1]) if current else (modes[0][0], modes[0][1])
    same = [m for m in modes if (m[0], m[1]) == (w, h)]
    return min(same, key=lambda m: abs(m[2] - want_hz))


def apply(want_hz, runner=subprocess.run):
    out = runner(["wlr-randr"], capture_output=True, text=True, check=False).stdout
    for name, modes in parse_modes(out).items():
        mode = pick(modes, want_hz)
        if not mode:
            continue
        spec = f"{mode[0]}x{mode[1]}@{mode[2]:.3f}Hz"
        log.info("%s -> %s", name, spec)
        runner(["wlr-randr", "--output", name, "--mode", spec], check=False)
        return spec
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("hz", nargs="?", type=float)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    hz = args.hz
    if hz is None:
        try:
            hz = float(PREF.read_text())
        except (OSError, ValueError):
            hz = 90.0
    else:
        PREF.parent.mkdir(parents=True, exist_ok=True)
        PREF.write_text(f"{hz:g}\n")
    return 0 if apply(hz) else 1


if __name__ == "__main__":
    sys.exit(main())
