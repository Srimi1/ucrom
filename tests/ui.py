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


def open_overview(phone, tries=3):
    """Swipe up from the bottom edge: Phosh's overview (running apps + app
    grid). Returns the position of its search field, or None. Retried: with
    the on-screen keyboard up, the first edge swipe can land on the keyboard."""
    import tempfile
    from pathlib import Path
    shot = Path(tempfile.mkdtemp()) / "overview.png"
    for _ in range(tries):
        phone.swipe(phone.w / 2, phone.h - 3, phone.w / 2, phone.h * 0.55, duration=0.6, steps=15)
        time.sleep(4)
        phone.screenshot(shot)
        # the field's grey placeholder text OCRs with low confidence
        pos = phone.find_text(shot, r"Search( apps\.*)?", min_conf=15)
        if pos:
            return pos
    return None


def _k(phone):
    return phone.h / 1440


def open_favorite(phone, evidence, desktop_id, process, ready_text, timeout=300):
    """Tap an app in the favourites rows of the app grid. Favourites are a
    4-column grid right under the "Search apps" field; their order is the
    configured favourites list (read from gsettings, state only)."""
    favs = phone.sh("gsettings get sm.puri.phosh favorites", user=True).out
    order = [x.strip(" '[]\n") for x in favs.split(",")]
    i = order.index(desktop_id)
    shot = evidence.shot_path("app-grid")
    search = None
    for _ in range(8):
        search = open_overview(phone)
        phone.screenshot(shot)
        if search and search[1] < phone.h * 0.2:
            break
        if search:
            # running apps' cards push the grid down and fold the favourites
            # away: swipe the cards off first, like a user clearing recents
            phone.swipe(phone.w / 2, phone.h * 0.26, phone.w / 2, 10, duration=0.4, steps=12)
            time.sleep(3)
    if not search or search[1] >= phone.h * 0.2:
        raise VMError(f"app grid not found (search field at {search})")
    evidence.rec["shots"].append({"file": str(shot.relative_to(shot.parent.parent)), "label": "app-grid"})
    x = phone.w * (0.125 + 0.25 * (i % 4))
    y = search[1] + (131 if i < 4 else 284) * _k(phone)
    phone.tap(x, y, hold=0.12)
    phone.wait_until(f"pgrep -f '{_self_safe(process)}' >/dev/null", timeout=timeout, interval=3)
    wait_for_text(phone, evidence, ready_text, timeout=timeout)


def wait_for_text(phone, evidence, pattern, timeout=300, label="screen", threshold=0):
    """Wait until OCR finds `pattern` on screen (apps render slowly under TCG)."""
    import re
    shot = evidence.shot_path(label)
    deadline = time.time() + timeout
    while time.time() < deadline:
        phone.screenshot(shot)
        if re.search(pattern, phone.ocr(shot, threshold=threshold)):
            return shot
        time.sleep(5)
    raise VMError(f"/{pattern}/ not on screen after {timeout}s")


def _self_safe(process):
    """'kgx' -> '[k]gx': the regex still matches the app, but no longer the
    guest shell running pgrep (whose own command line contains the name)."""
    return f"[{process[0]}]{process[1:]}"


def close_app(phone, process, timeout=90, gone=None):
    """Open the overview and swipe the app's card up and away. `gone` is a
    guest shell test for "the window is closed" (default: no such process;
    Console keeps a background service, so its test is "no shell left")."""
    gone = gone or f"! pgrep -f '{_self_safe(process)}' >/dev/null"
    if not open_overview(phone):
        return False
    phone.swipe(phone.w / 2, phone.h * 0.26, phone.w / 2, 10, duration=0.4, steps=12)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if phone.sh(gone).ok:
            return True
        time.sleep(2)
    return False


# Console's window is closed when kgx has no shell child left (kgx itself may
# linger a while as a background service)
KGX_CLOSED = "k=$(pgrep -d, -x kgx) || exit 0; ! pgrep -P \"$k\" >/dev/null"


# GNOME Calculator (46) basic keypad, anchored on its "mod" button
CALC_KEYS = {"C": (-411, 0), "7": (-411, 89), "8": (-273, 89), "9": (-136, 89), "x": (0, 180),
             "4": (-411, 180), "5": (-273, 180), "6": (-136, 180), "=": (136, 315),
             "1": (-411, 270), "2": (-273, 270), "3": (-136, 270), "0": (-411, 360),
             "+": (0, 360), "-": (0, 270)}

# phosh-osk-stub letter layers, anchored on the space bar label: row offset
# above the space bar (1440-px units), first key x and key pitch (fractions
# of the width). Terminals get the "Terminal" layout (extra ~, Tab, ESC keys).
OSK_LAYOUTS = {
    "English": {"qwertyuiop": (-298, 0.05, 0.10), "asdfghjkl": (-199, 0.10, 0.10),
                "zxcvbnm": (-98, 0.20, 0.10)},
    "Terminal": {"qwertyuiop": (-300, 0.133, 0.091), "asdfghjkl": (-200, 0.133, 0.091),
                 "zxcvbnm": (-100, 0.225, 0.091)},
}


def osk_key(phone, space, ch, layout="English"):
    for row, (dy, x0, pitch) in OSK_LAYOUTS[layout].items():
        if ch in row:
            return (phone.w * (x0 + pitch * row.index(ch)), space[1] + dy * _k(phone))
    raise KeyError(ch)
