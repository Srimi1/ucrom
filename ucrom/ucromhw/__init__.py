"""ucrom hardware helpers: small daemons that give OnePlus-specific hardware
(alert slider, pop-up camera, in-display fingerprint, 90 Hz panel) a proper
Linux behaviour on ucrom.

Every path goes through hw_path(), so tests can point the daemons at a fake
/sys, /proc and input devices with UCROM_HW_ROOT.
"""

import os
from pathlib import Path


def hw_root() -> Path:
    return Path(os.environ.get("UCROM_HW_ROOT", "/"))


def hw_path(path: str) -> Path:
    return hw_root() / path.lstrip("/")


def state_dir() -> Path:
    d = Path(os.environ.get("UCROM_STATE_DIR")
             or (os.environ.get("XDG_RUNTIME_DIR", "/run") + "/ucrom"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_state(name: str, value: str) -> None:
    (state_dir() / name).write_text(value + "\n")


def read_text(path: str, default: str = "") -> str:
    try:
        return hw_path(path).read_text().strip()
    except OSError:
        return default


def write_text(path: str, value: str) -> bool:
    try:
        hw_path(path).write_text(value)
        return True
    except OSError:
        return False
