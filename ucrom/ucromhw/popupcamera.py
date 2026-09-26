"""ucrom-popup-camera: drives the OnePlus 7 Pro / 7T Pro pop-up selfie camera.

Motor interface (vendor kernel oplus_motor driver, same one LineageOS uses):
    /sys/class/motor/direction   write 1 = up, 0 = down
    /sys/class/motor/enable      write 1 = move now
    /sys/class/motor/position    read  0 = up, 1 = down

Behaviour:
  * Raises the camera while the front camera (Android camera id 1) is open and
    lowers it when it closes. "Open" comes from a pluggable probe:
      - halium: the Android camera service (dumpsys media.camera in the
        Halium container), polled only while a camera app is running;
      - file: /run/ucrom/front-camera exists (written by ucrom's camera
        launcher and usable by any app).
  * Drop protection: if the accelerometer reads free fall (|a| < 3 m/s^2 for
    at least 100 ms) while the camera is up, it is pulled down at once,
    like OxygenOS does.
"""

import argparse
import logging
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from . import hw_path, read_text, write_state, write_text

MOTOR = "/sys/class/motor"
POSITION_UP, POSITION_DOWN = "0", "1"
DIRECTION_UP, DIRECTION_DOWN = "1", "0"
FRONT_CAMERA_ID = "1"
FRONT_FLAG = "/run/ucrom/front-camera"
CAMERA_APPS = ("droidian-camera", "megapixels", "gst-launch-1.0", "ucrom-camera", "snapshot")
FREE_FALL_MS2 = 3.0
FREE_FALL_TIME = 0.10
# The accelerometer is sampled every loop; the (costlier) camera probe only
# every PROBE_EVERY loops (0.5 s at the default 50 ms interval).
PROBE_EVERY = int(os.environ.get("UCROM_POPUP_PROBE_EVERY", "10"))

log = logging.getLogger("ucrom-popup-camera")


class Motor:
    def present(self) -> bool:
        return hw_path(MOTOR + "/enable").exists()

    def position(self) -> str:
        return read_text(MOTOR + "/position", "?")

    def is_up(self) -> bool:
        return self.position() == POSITION_UP

    def move(self, up: bool, reason: str) -> None:
        want = POSITION_UP if up else POSITION_DOWN
        if self.position() == want:
            return
        log.info("camera %s (%s)", "up" if up else "down", reason)
        write_text(MOTOR + "/direction", DIRECTION_UP if up else DIRECTION_DOWN)
        write_text(MOTOR + "/enable", "1")
        write_state("popup-camera", f"{'up' if up else 'down'} {reason}")


class FrontCameraProbe:
    """Is the front camera in use right now?"""

    def __init__(self, mode: str):
        self.mode = mode

    def camera_app_running(self) -> bool:
        proc = hw_path("/proc")
        for pid in os.listdir(proc):
            if not pid.isdigit():
                continue
            try:
                comm = (proc / pid / "comm").read_text().strip()
            except OSError:
                continue
            if comm in CAMERA_APPS:
                return True
        return False

    def front_open(self) -> bool:
        if hw_path(FRONT_FLAG).exists():
            return True
        if self.mode != "halium" or not self.camera_app_running():
            return False
        try:
            out = subprocess.run(
                ["lxc-attach", "-n", "android", "--", "/system/bin/dumpsys", "media.camera"],
                capture_output=True, text=True, timeout=5, check=False).stdout
        except (OSError, subprocess.TimeoutExpired):
            return False
        return parse_dumpsys_front_open(out)


def parse_dumpsys_front_open(text: str) -> bool:
    """True if `dumpsys media.camera` shows camera id 1 with an active client."""
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("== Camera device") or line.startswith("Device ") or line.startswith("== Service global"):
            current = None
        if line.startswith("Device ") and " is open" in line:
            parts = line.split()
            if len(parts) > 1 and parts[1] == FRONT_CAMERA_ID:
                return True
        if line.startswith("Camera ID:"):
            current = line.split(":", 1)[1].strip()
        if current == FRONT_CAMERA_ID and ("Client PID" in line or "Client package" in line):
            return True
    return False


class Accelerometer:
    """Reads an IIO accelerometer (mainline or halium-exported)."""

    def __init__(self):
        self.dev = None
        base = hw_path("/sys/bus/iio/devices")
        if base.exists():
            for d in sorted(base.iterdir()):
                if (d / "in_accel_x_raw").exists():
                    self.dev = d
                    break

    def magnitude(self):
        if not self.dev:
            return None
        try:
            scale = float((self.dev / "in_accel_scale").read_text()) if (self.dev / "in_accel_scale").exists() else 1.0
            vals = [float((self.dev / f"in_accel_{a}_raw").read_text()) * scale for a in "xyz"]
        except (OSError, ValueError):
            return None
        return math.sqrt(sum(v * v for v in vals))


def run(mode: str, interval: float, iterations: int | None = None) -> int:
    motor = Motor()
    if not motor.present():
        log.warning("no camera motor on this device; nothing to do")
        write_state("popup-camera", "absent")
        return 0 if iterations is None else 1
    probe = FrontCameraProbe(mode)
    accel = Accelerometer()
    falling_since = None
    # Start safe: camera down
    motor.move(False, "startup")
    n = 0
    while iterations is None or n < iterations:
        n += 1
        mag = accel.magnitude()
        now = time.monotonic()
        if mag is not None and mag < FREE_FALL_MS2:
            falling_since = falling_since or now
            if motor.is_up() and now - falling_since >= FREE_FALL_TIME:
                motor.move(False, "free fall")
                write_state("popup-camera-drop", str(time.time()))
        else:
            falling_since = None
            if (n - 1) % PROBE_EVERY == 0:
                want_up = probe.front_open()
                if want_up != motor.is_up():
                    motor.move(want_up, "front camera " + ("opened" if want_up else "closed"))
        time.sleep(interval)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default=Path("/etc/ucrom-flavor").read_text().strip()
                    if Path("/etc/ucrom-flavor").exists() else "mainline")
    ap.add_argument("--interval", type=float, default=0.05)
    ap.add_argument("--iterations", type=int, default=None, help="for tests")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    return run(args.mode, args.interval, args.iterations)


if __name__ == "__main__":
    sys.exit(main())
