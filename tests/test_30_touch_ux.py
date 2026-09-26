"""Using the phone by touch only, like an Android phone.

Every action is a touch gesture sent to the virtio multitouch screen; results
are read back from the screen with OCR. The guest agent is only used to set
up (lock the phone, list favourites) and to check processes.
"""

import time

import pytest

import ui

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
    shot = evidence.shot_path("calculator")
    mod = None
    for _ in range(3):
        phone.screenshot(shot)
        mod = phone.find_text(shot, "mod", case=True)
        if mod:
            break
        # the on-screen keyboard can cover the keypad; its "123" key reveals it
        phone.tap(phone.w * 0.05, phone.h * 0.944, hold=0.12)
        time.sleep(4)
    assert mod, "calculator keypad not visible"
    evidence.rec["shots"].append({"file": str(shot.relative_to(shot.parent.parent)), "label": "calculator"})
    k = phone.h / 1440
    read = []
    for key in ("7", "x", "6", "="):
        dx, dy = ui.CALC_KEYS[key]
        x, y = mod[0] + dx * k, mod[1] + dy * k
        read.append(f"{key}->{phone.read_char(shot, x, y)!r}")
        phone.tap(x, y, hold=0.12)
        time.sleep(1.2)
    evidence.note("calculator keys located from the 'mod' button, read back by OCR: " + ", ".join(read))
    res = ui.wait_for_text(phone, evidence, r"42", timeout=60, label="result")
    evidence.note("display: " + " ".join(phone.ocr(res, box=(0, int(150 * k), phone.w, int(520 * k))).split()))
    assert ui.close_app(phone, "gnome-calculator"), "swipe-to-close failed"
    evidence.note("closed by swiping its card away in the overview")


def test_on_screen_keyboard_typing(phone, evidence):
    """Type text using only on-screen keyboard taps"""
    ui.open_favorite(phone, evidence, "org.gnome.Console.desktop", "kgx", r"ucrom@|\$|~")
    phone.tap(phone.w / 2, phone.h * 0.25, hold=0.12)      # focus the terminal
    kb = ui.wait_for_text(phone, evidence, r"English", timeout=60, label="osk")
    space = phone.find_text(kb, "English", case=True)
    assert space, "on-screen keyboard not shown"
    word = "ucrom"
    read = []
    for ch in word:
        x, y = ui.osk_key(phone, space, ch)
        read.append(f"{ch}->{phone.read_char(kb, x, y)!r}")
        phone.tap(x, y, hold=0.12)
        time.sleep(0.8)
    evidence.note("keys read back by OCR: " + ", ".join(read))
    time.sleep(3)
    typed = evidence.screenshot(phone, "typed")
    text = phone.ocr(typed, box=(0, 0, phone.w, int(phone.h * 0.55))).lower()
    evidence.note("terminal text: " + " ".join(text.split())[:200])
    assert word in text
    ui.close_app(phone, "kgx")


def test_quick_settings_swipe(phone, evidence):
    """Swipe down from the top opens quick settings"""
    phone.swipe(phone.w / 2, 3, phone.w / 2, phone.h * 0.6, duration=0.6, steps=15)
    time.sleep(4)
    shot = evidence.screenshot(phone, "quick-settings")
    text = phone.ocr(shot)
    evidence.note("quick settings text: " + " ".join(text.split())[:200])
    assert any(w in text for w in ("Wi-Fi", "WiFi", "Bluetooth", "Battery", "Airplane", "Torch",
                                   "Rotation", "Mobile", "Location", "Settings"))
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
