"""Touch-only UI helpers for the ucrom emulator tests (Phosh).

Everything here acts through PhoneVM.tap/swipe (multitouch events) and reads
the screen with OCR; guest-agent calls are only used to *check* state.
"""

import time

from vm import VMError

PIN = "147258"
SS = ("gdbus call --session -d org.gnome.ScreenSaver -o /org/gnome/ScreenSaver "
      "-m org.gnome.ScreenSaver.GetActive")


LOCK_TEXT = r"Slide up to unlock|Slide|Enter Passcode|Passcode|Unlock"


def is_locked(phone) -> bool:
    """Ground truth from the screen: Phosh's ScreenSaver.GetActive and logind's
    LockedHint both read false while the lock screen is showing (checked on
    Phosh 0.38), so look for the lock screen itself."""
    import tempfile
    from pathlib import Path
    shot = Path(tempfile.mkdtemp()) / "lockcheck.png"
    wake(phone)
    phone.screenshot(shot)
    text = phone.ocr(shot)
    return any(k in text for k in ("Slide up to unlock", "Enter Passcode", "Passcode"))


def lock(phone):
    """Lock via Phosh's ScreenSaver API (setup only; tests unlock by touch)."""
    phone.sh(SS.replace("GetActive", "SetActive") + " true", user=True)


def wait_shell_ready(phone, timeout=900):
    phone.wait_until(f"{SS} >/dev/null", timeout=timeout, interval=5, user=True)
    # Test-only: no idle blanking. Under emulation (no KVM) a touch sequence
    # checked by OCR can outlast the phone's 2 minute idle timeout.
    phone.sh("gsettings set org.gnome.desktop.session idle-delay 0", user=True)
    time.sleep(10)


def wake(phone):
    """Tap the screen if it is blanked (Phosh wakes on touch)."""
    import tempfile
    from pathlib import Path
    shot = Path(tempfile.mkdtemp()) / "wake.png"
    phone.screenshot(shot)
    if "not active" in phone.ocr(shot):
        phone.tap(phone.w / 2, phone.h / 2, hold=0.15)
        time.sleep(4)


def swipe_up_from_bottom(phone):
    phone.swipe(phone.w / 2, phone.h * 0.90, phone.w / 2, phone.h * 0.30, duration=0.8, steps=20)


# Phosh keypad geometry (Phosh 0.38): key rows sit at fixed offsets above the
# "Unlock" button (in 1440-px-tall screen units); columns are fractions of the
# width.
KEY_COLS = {"1": 0, "2": 1, "3": 2, "4": 0, "5": 1, "6": 2, "7": 0, "8": 1, "9": 2, "0": 1}
KEY_ROWS = {"1": 0, "2": 0, "3": 0, "4": 1, "5": 1, "6": 1, "7": 2, "8": 2, "9": 2, "0": 3}
COL_X = (0.26, 0.50, 0.74)
ROW_UP = (700, 528, 357, 185)


def _keys(phone, unlock_y):
    k = phone.h / 1440
    return {d: (phone.w * COL_X[KEY_COLS[d]], unlock_y - ROW_UP[KEY_ROWS[d]] * k) for d in KEY_COLS}


def _find_unlock(phone, shot, tries=3):
    """The PIN pad's "Unlock" button (case-sensitive: the clock page says
    "Slide up to unlock"), only while "Enter Passcode" is on screen."""
    for _ in range(tries):
        phone.screenshot(shot)
        if phone.find_text(shot, "Enter Passcode|Passcode", case=True):
            pos = phone.find_text(shot, "Unlock", case=True)
            if pos:
                return pos
        time.sleep(1)
    return None


def unlock(phone, evidence, pin=PIN):
    """Unlock the lock screen with a swipe and taps on the PIN pad."""
    evidence.screenshot(phone, "lockscreen")
    pad = evidence.shot_path("pin-pad")
    button = None
    for _attempt in range(3):
        wake(phone)
        swipe_up_from_bottom(phone)
        time.sleep(3)
        button = _find_unlock(phone, pad, tries=1)
        if button:
            break
    if not button:
        raise VMError("PIN pad did not appear after swiping up")
    evidence.rec["shots"].append({"file": str(pad.relative_to(pad.parent.parent)), "label": "pin-pad"})
    # Phosh returns to the clock after ~5 s without input, so the whole PIN
    # is tapped in one go on the measured
    # layout (no screenshots/OCR in between; the pad does not move while typing).
    keys = _keys(phone, button[1])
    for d in pin:
        phone.tap(*keys[d], hold=0.15)
        time.sleep(1.0)
    after = evidence.shot_path("pin-typed")
    phone.screenshot(after)
    evidence.rec["shots"].append({"file": str(after.relative_to(after.parent.parent)), "label": "pin-typed"})
    phone.tap(*button, hold=0.15)
    # evidence: the keys we tapped really are those digits (OCR of each cell)
    seen = {d: phone.read_char(after, *keys[d]) for d in sorted(set(pin))}
    evidence.note("PIN pad keys located and read back by OCR: " + ", ".join(f"{d}->{seen[d]!r}" for d in seen))
    for _ in range(10):
        time.sleep(3)
        if not is_locked(phone):
            return
    raise VMError("still locked after entering the PIN")


def open_overview(phone, evidence=None):
    """Open the app grid (tap the home bar / swipe up)."""
    phone.tap(phone.w / 2, phone.h - 12)
    time.sleep(3)


def open_app(phone, evidence, label, process, timeout=240):
    """Open an app by tapping its icon label in the app grid (search by
    scrolling the grid with swipes if it is not on the first screen)."""
    open_overview(phone)
    for page in range(6):
        shot = evidence.shot_path(f"grid-{label.split()[0].lower()}-{page}")
        phone.screenshot(shot)
        pos = phone.find_text(shot, label)
        if pos:
            phone.tap(*pos)
            phone.wait_until(f"pgrep -f '{process}' >/dev/null", timeout=timeout, interval=3)
            time.sleep(8)
            return pos
        phone.swipe(phone.w / 2, phone.h * 0.75, phone.w / 2, phone.h * 0.35, duration=0.5)
        time.sleep(2)
    raise VMError(f"app '{label}' not found in the app grid")


def close_app(phone, process):
    """Close the foreground app from the overview by swiping its card up."""
    open_overview(phone)
    time.sleep(2)
    phone.swipe(phone.w / 2, phone.h * 0.30, phone.w / 2, 10, duration=0.3)
    time.sleep(4)
    return not phone.sh(f"pgrep -f '{process}' >/dev/null").ok
