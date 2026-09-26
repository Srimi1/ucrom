"""Touch-only UI helpers for the ucrom emulator tests (Phosh).

Everything here acts through PhoneVM.tap/swipe (multitouch events) and reads
the screen with OCR; guest-agent calls are only used to *check* state.
"""

import time

from vm import SCREEN_H, SCREEN_W, VMError

PIN = "147258"
SS = ("gdbus call --session -d org.gnome.ScreenSaver -o /org/gnome/ScreenSaver "
      "-m org.gnome.ScreenSaver.GetActive")


def is_locked(phone) -> bool:
    return "true" in phone.sh(SS, user=True).out


def wait_shell_ready(phone, timeout=900):
    phone.wait_until(f"{SS} >/dev/null", timeout=timeout, interval=5, user=True)
    time.sleep(10)


def swipe_up_from_bottom(phone):
    phone.swipe(SCREEN_W / 2, SCREEN_H - 8, SCREEN_W / 2, SCREEN_H * 0.35, duration=0.4)


def unlock(phone, evidence, pin=PIN):
    """Unlock the lock screen with a swipe and taps on the PIN pad."""
    shot = evidence.shot_path("lockscreen")
    phone.screenshot(shot)
    evidence.screenshot(phone, "lockscreen")
    for attempt in range(3):
        swipe_up_from_bottom(phone)
        time.sleep(3)
        pad = evidence.shot_path("keypad-probe")
        phone.screenshot(pad)
        if phone.find_text(pad, "5") and phone.find_text(pad, "8"):
            break
    else:
        raise VMError("PIN pad did not appear after swiping up")
    evidence.screenshot(phone, "pin-pad")
    positions = {}
    for d in set(pin):
        p = phone.find_text(pad, d)
        if not p:
            raise VMError(f"digit {d} not found on the PIN pad")
        positions[d] = p
    for d in pin:
        phone.tap(*positions[d])
        time.sleep(0.4)
    time.sleep(1)
    evidence.screenshot(phone, "pin-entered")
    after = evidence.shot_path("after-pin")
    phone.screenshot(after)
    unlock_btn = phone.find_text(after, "Unlock")
    if unlock_btn:
        phone.tap(*unlock_btn)
    for _ in range(15):
        time.sleep(2)
        if not is_locked(phone):
            return
    raise VMError("still locked after entering the PIN")


def open_overview(phone, evidence=None):
    """Open the app grid (tap the home bar / swipe up)."""
    phone.tap(SCREEN_W / 2, SCREEN_H - 12)
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
        phone.swipe(SCREEN_W / 2, SCREEN_H * 0.75, SCREEN_W / 2, SCREEN_H * 0.35, duration=0.5)
        time.sleep(2)
    raise VMError(f"app '{label}' not found in the app grid")


def close_app(phone, process):
    """Close the foreground app from the overview by swiping its card up."""
    open_overview(phone)
    time.sleep(2)
    phone.swipe(SCREEN_W / 2, SCREEN_H * 0.30, SCREEN_W / 2, 10, duration=0.3)
    time.sleep(4)
    return not phone.sh(f"pgrep -f '{process}' >/dev/null").ok
