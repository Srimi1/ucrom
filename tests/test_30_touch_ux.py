"""Using the phone by touch only, like an Android phone.

Every action is a touch gesture sent to the virtio multitouch screen; results
are read back from the screen with OCR. The guest agent is only used to set
up (lock the phone, list favourites) and to check processes.
"""

import time

import pytest

import ui
from vm import VMError

pytestmark = pytest.mark.vm


def test_unlock_with_pin_pad(phone, evidence):
    """Swipe up, tap the PIN on the pad, phone unlocks"""
    ui.wait_shell_ready(phone)
    if not ui.is_locked(phone):
        ui.lock(phone)
        time.sleep(6)
    assert ui.is_locked(phone)
    t = time.time()
    ui.unlock(phone, evidence)
    evidence.note(f"unlocked by touch in {time.time() - t:.0f} s")
    evidence.screenshot(phone, "home")
    assert not ui.is_locked(phone)


def test_calculator_by_touch(phone, evidence):
    """Open Calculator from the app grid and compute 7 × 6 by tapping"""
    ui.open_favorite(phone, evidence, "org.gnome.Calculator.desktop", "gnome-calculator", r"Basic|Undo")
    try:
        _calculate(phone, evidence)
    finally:
        closed = ui.close_app(phone, "gnome-calculator")
    assert closed, "swipe-to-close failed"
    evidence.note("closed by swiping its card away in the overview")


def _calculate(phone, evidence):
    shot = evidence.shot_path("calculator")
    k = phone.h / 1440
    # The window re-lays out when the on-screen keyboard slides in: wait
    # until the keypad ("mod" row) sits still in the upper part of the screen
    mod, last = None, None
    for _ in range(12):
        phone.screenshot(shot)
        pos = phone.find_text(shot, "mod", case=True)
        if pos and pos[1] < phone.h * 0.6 and last and abs(pos[1] - last[1]) < 5:
            mod = pos
            break
        last = pos
        time.sleep(3)
    assert mod, f"calculator keypad not visible (last 'mod' at {last})"
    evidence.rec["shots"].append({"file": str(shot.relative_to(shot.parent.parent)), "label": "calculator"})
    read = []
    for key in ("C", "7", "x", "6", "="):
        dx, dy = ui.CALC_KEYS[key]
        x, y = mod[0] + dx * k, mod[1] + dy * k
        read.append(f"{key}->{phone.read_char(shot, x, y)!r}")
        phone.tap(x, y, hold=0.12)
        time.sleep(1.2)
    evidence.note("calculator keys located from the 'mod' button, read back by OCR: " + ", ".join(read))
    res = None
    for attempt in range(3):
        try:
            res = ui.wait_for_text(phone, evidence, r"42", timeout=30, label="result")
            break
        except VMError:
            # under emulation a tap can be dropped while the app is busy
            dx, dy = ui.CALC_KEYS["="]
            evidence.note(f"no result yet, tapping '=' again (attempt {attempt + 2})")
            phone.tap(mod[0] + dx * k, mod[1] + dy * k, hold=0.12)
    assert res, "calculator never showed 42"
    evidence.note("display: " + " ".join(phone.ocr(res, box=(0, int(150 * k), phone.w, int(520 * k))).split()))


def test_on_screen_keyboard_typing(phone, evidence):
    """Type text using only on-screen keyboard taps"""
    ui.open_favorite(phone, evidence, "org.gnome.Console.desktop", "kgx", r"ucrom@|\$|~")
    try:
        _type_in_console(phone, evidence)
    finally:
        closed = ui.close_app(phone, "kgx", gone=ui.KGX_CLOSED)
    assert closed, "swipe-to-close failed"


def _type_in_console(phone, evidence):
    phone.tap(phone.w / 2, phone.h * 0.25, hold=0.12)      # focus the terminal
    # key labels are light grey-on-grey: OCR them with a white-text threshold
    kb = ui.wait_for_text(phone, evidence, r"English|Terminal", timeout=60, label="osk", threshold=190)
    layout = next((n for n in ui.OSK_LAYOUTS if phone.find_text(kb, n, case=True, threshold=190)), None)
    assert layout, "on-screen keyboard not shown"
    space = phone.find_text(kb, layout, case=True, threshold=190)
    evidence.note(f"on-screen keyboard layout: {layout}")
    word = "ucrom"
    read = []
    for ch in word:
        x, y = ui.osk_key(phone, space, ch, layout)
        read.append(f"{ch}->{phone.read_char(kb, x, y, half=26, threshold=190)!r}")
        phone.tap(x, y, hold=0.12)
        time.sleep(0.8)
    evidence.note("keys read back by OCR: " + ", ".join(read))
    time.sleep(3)
    typed = evidence.screenshot(phone, "typed")
    text = phone.ocr(typed, box=(0, 0, phone.w, int(phone.h * 0.55))).lower()
    evidence.note("terminal text: " + " ".join(text.split())[:200])
    assert word in text


def test_quick_settings_swipe(phone, evidence):
    """Swipe down from the top opens quick settings"""
    phone.swipe(phone.w / 2, 3, phone.w / 2, phone.h * 0.9, duration=1.0, steps=25)
    time.sleep(6)
    shot = evidence.screenshot(phone, "quick-settings")
    text = phone.ocr(shot)
    evidence.note("quick settings text: " + " ".join(text.split())[:200])
    # quick-setting tiles only (app names like "Mobile Settings" do not count)
    tiles = [w for w in ("Wi-Fi", "WiFi", "Bluetooth", "Battery", "Airplane", "Torch",
                         "Portrait", "Landscape", "Rotation", "VPN", "Location", "Do Not Disturb")
             if w in text]
    evidence.note(f"quick-setting tiles seen: {tiles}")
    assert len(tiles) >= 2
    phone.swipe(phone.w / 2, phone.h * 0.6, phone.w / 2, 3, duration=0.5, steps=12)
    time.sleep(3)


def test_power_button_locks(phone, evidence):
    """The phone's power button blanks and locks the screen (never shuts down)"""
    assert not ui.is_locked(phone)
    phone.power_button()
    time.sleep(6)
    deadline = time.time() + 60
    while not ui.is_locked(phone) and time.time() < deadline:
        time.sleep(3)
    evidence.screenshot(phone, "after-power-button")
    assert ui.is_locked(phone)
    assert phone.sh("systemctl is-system-running").out.strip() in ("running", "degraded")
    evidence.note("locked; the system kept running (logind ignores the power key)")
    ui.unlock(phone, evidence)
    assert not ui.is_locked(phone)
