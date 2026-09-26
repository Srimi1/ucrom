"""Using the phone by touch only, like an Android phone."""

import time

import pytest

import ui
from vm import SCREEN_H, SCREEN_W

pytestmark = pytest.mark.vm


def test_unlock_with_pin_pad(phone, evidence):
    """Swipe up, tap the PIN on the pad, phone unlocks"""
    ui.wait_shell_ready(phone)
    if not ui.is_locked(phone):
        phone.sh("gdbus call --session -d org.gnome.ScreenSaver -o /org/gnome/ScreenSaver "
                 "-m org.gnome.ScreenSaver.SetActive true", user=True)
        time.sleep(4)
    assert ui.is_locked(phone)
    ui.unlock(phone, evidence)
    evidence.screenshot(phone, "home")
    assert not ui.is_locked(phone)


def test_calculator_by_touch(phone, evidence):
    """Open Calculator from the app grid and compute 7 × 6 by tapping"""
    ui.open_app(phone, evidence, "Calculator", "gnome-calculator")
    shot = evidence.screenshot(phone, "calculator")
    for key in ("7", "[×x*]", "6", "="):
        pos = phone.find_text(shot, key)
        assert pos, f"calculator key {key} not found"
        phone.tap(*pos)
        time.sleep(1)
    time.sleep(2)
    res = evidence.screenshot(phone, "result")
    text = phone.ocr(res)
    evidence.note("screen text after 7 × 6 =: " + " ".join(text.split())[:200])
    assert "42" in text
    assert ui.close_app(phone, "gnome-calculator"), "swipe-to-close failed"
    evidence.note("closed with a swipe in the overview")


def test_on_screen_keyboard_typing(phone, evidence):
    """Type text using only on-screen keyboard taps"""
    ui.open_app(phone, evidence, "Text Editor", "gnome-text-editor")
    phone.tap(SCREEN_W / 2, SCREEN_H * 0.35)   # focus the document
    time.sleep(4)
    kb = evidence.screenshot(phone, "osk-shown")
    osk = phone.sh("pgrep -f phosh-osk-stub >/dev/null && echo yes").out.strip()
    evidence.note(f"on-screen keyboard process running: {osk or 'no'}")
    for ch in "ucrom":
        pos = phone.find_text(kb, ch)
        assert pos, f"key '{ch}' not found on the on-screen keyboard"
        phone.tap(*pos)
        time.sleep(0.6)
    time.sleep(2)
    typed = evidence.screenshot(phone, "typed")
    text = phone.ocr(typed).lower()
    evidence.note("screen text: " + " ".join(text.split())[:200])
    assert "ucrom" in text
    phone.sh("pkill -f gnome-text-editor; true")


def test_quick_settings_swipe(phone, evidence):
    """Swipe down from the top opens quick settings"""
    phone.swipe(SCREEN_W / 2, 3, SCREEN_W / 2, SCREEN_H * 0.6, duration=0.4)
    time.sleep(3)
    shot = evidence.screenshot(phone, "quick-settings")
    text = phone.ocr(shot)
    evidence.note("quick settings text: " + " ".join(text.split())[:200])
    assert any(w in text for w in ("Wi-Fi", "WiFi", "Bluetooth", "Battery", "Airplane", "Torch", "Rotation"))
    phone.swipe(SCREEN_W / 2, SCREEN_H * 0.6, SCREEN_W / 2, 3, duration=0.4)
    time.sleep(2)


def test_power_button_locks(phone, evidence):
    """The phone's power button blanks and locks the screen (never shuts down)"""
    assert not ui.is_locked(phone)
    phone.power_button()
    phone.wait_until(ui.SS + " | grep -q true", timeout=30, interval=1, user=True)
    time.sleep(2)
    evidence.screenshot(phone, "after-power-button")
    assert phone.sh("systemctl is-system-running").out.strip() in ("running", "degraded")
    evidence.note("locked, system still running")
    phone.power_button()      # wake
    time.sleep(3)
    ui.unlock(phone, evidence)
