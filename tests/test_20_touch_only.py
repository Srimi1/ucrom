"""Touch only: keyboards and mice are shut off, touch works.

The emulated phone has a virtio multitouch screen plus a virtio keyboard and
mouse attached from boot, and USB keyboards/mice get hot-plugged during the
test. ucrom must ignore every one of them.
"""

import time

import pytest

pytestmark = pytest.mark.vm

INPUTS = r"""
for d in /sys/class/input/input*; do
  printf '%s|%s\n' "$(cat $d/name)" "$(cat $d/inhibited 2>/dev/null)"
done
"""


def inputs(phone):
    out = phone.sh(INPUTS).out
    return dict(line.split("|", 1) for line in out.strip().splitlines())


def test_kernel_inhibits_keyboard_and_mouse(phone, evidence):
    """Keyboard and mouse are inhibited in the kernel; touchscreen is live"""
    devs = inputs(phone)
    for name, inh in devs.items():
        evidence.note(f"{name}: {'BLOCKED' if inh == '1' else 'allowed'}")
    kb = [n for n in devs if "Keyboard" in n]
    mouse = [n for n in devs if "Mouse" in n]
    touch = [n for n in devs if "Multitouch" in n or "MultiTouch" in n]
    assert kb and mouse and touch, devs
    assert all(devs[n] == "1" for n in kb + mouse)
    assert all(devs[n] == "0" for n in touch)


def test_compositor_sees_only_touch(phone, evidence):
    """libinput (what the shell uses) only sees the touchscreen and the power button"""
    r = phone.sh("libinput list-devices 2>/dev/null | sed -n 's/^Device: *//p'")
    names = [n.strip() for n in r.out.splitlines() if n.strip()]
    evidence.note("libinput devices: " + ", ".join(names))
    assert any("multitouch" in n.lower() for n in names)
    assert not any("Keyboard" in n or "Mouse" in n for n in names)


def _read_events(phone, name_part, seconds):
    """Start a raw evdev reader in the guest on the named device."""
    script = f"""
python3 - >/dev/null 2>&1 <<'PY' &
import evdev, select, time
devs = [evdev.InputDevice(p) for p in evdev.list_devices()]
dev = next(d for d in devs if '{name_part}' in d.name)
open('/tmp/ucrom-evready-{name_part.replace(" ", "_")}', 'w').write('1')
n = 0
end = time.time() + {seconds}
while time.time() < end:
    r, _, _ = select.select([dev.fd], [], [], 0.2)
    if r:
        n += len([e for e in dev.read() if e.type != 0])
open('/tmp/ucrom-evcount-{name_part.replace(" ", "_")}', 'w').write(str(n))
PY
"""
    tag = name_part.replace(" ", "_")
    phone.sh(f"rm -f /tmp/ucrom-evready-{tag} /tmp/ucrom-evcount-{tag}")
    phone.sh(script)
    # python3 + evdev start slowly under emulation: only inject once the
    # reader really holds the device open, or a zero count would prove nothing
    phone.wait_until(f"test -f /tmp/ucrom-evready-{tag}", timeout=60, interval=1)


def test_hardware_keyboard_typing_does_nothing(phone, evidence):
    """Typing on the keyboard delivers zero events and changes nothing on screen"""
    # the lock screen shows a big clock: start just after a minute turns over
    # so the only thing that could change the screen is the keyboard
    while int(phone.sh("date +%S").out.strip() or 0) > 15:
        time.sleep(2)
    _read_events(phone, "Keyboard", 20)
    time.sleep(1)
    before = evidence.screenshot(phone, "before-typing")
    phone.type_on_hardware_keyboard("hello ucrom\n")
    phone.type_on_hardware_keyboard("rm -rf /\n")
    time.sleep(8)
    after = evidence.screenshot(phone, "after-typing")
    phone.wait_until("test -f /tmp/ucrom-evcount-Keyboard", timeout=60, interval=1)
    n = phone.sh("cat /tmp/ucrom-evcount-Keyboard").out.strip()
    evidence.note(f"events that reached the keyboard device node: {n}")
    assert n == "0"
    from PIL import Image, ImageChops
    a, b = Image.open(before).convert("RGB"), Image.open(after).convert("RGB")
    # ignore the status bar (clock may tick)
    box = (0, 40, a.width, a.height)
    diff = ImageChops.difference(a.crop(box), b.crop(box)).getbbox()
    evidence.note(f"screen change below status bar: {diff}")
    assert diff is None


def test_mouse_does_nothing(phone, evidence):
    """Moving and clicking the mouse delivers zero events"""
    _read_events(phone, "Mouse", 20)
    time.sleep(1)
    for _ in range(10):
        phone.move_mouse(40, 60, click=True)
    time.sleep(6)
    phone.wait_until("test -f /tmp/ucrom-evcount-Mouse", timeout=60, interval=1)
    n = phone.sh("cat /tmp/ucrom-evcount-Mouse").out.strip()
    evidence.note(f"events that reached the mouse device node: {n}")
    assert n == "0"


def test_usb_keyboard_and_mouse_hotplug_blocked(phone, evidence):
    """Plugging in a USB keyboard and mouse: no driver ever binds"""
    before = set(inputs(phone))
    phone.hotplug_usb("usb-kbd")
    phone.hotplug_usb("usb-mouse")
    time.sleep(8)
    usb = phone.sh("for d in /sys/bus/usb/devices/*; do [ -f $d/product ] && "
                   "echo \"$(cat $d/product)|$(basename $(readlink -f $d/*:1.0/driver 2>/dev/null) 2>/dev/null)\"; done").out
    evidence.note("USB devices (product|bound driver): " + usb.strip().replace("\n", "; "))
    assert "QEMU USB Keyboard" in usb and "QEMU USB Mouse" in usb
    for line in usb.splitlines():
        if "Keyboard" in line or "Mouse" in line:
            assert line.split("|")[1] in ("", "."), f"a driver bound: {line}"
    after = set(inputs(phone))
    evidence.note(f"new input devices: {sorted(after - before) or 'none'}")
    assert not (after - before)
    lsmod = phone.sh("lsmod | grep -E '^(usbhid|hid_generic|usbkbd|usbmouse) ' || true").out
    assert lsmod.strip() == ""
    r = phone.sh("modprobe usbhid")
    evidence.note(f"explicit 'modprobe usbhid' -> rc={r.rc} {r.err.strip()}")
    assert not r.ok


def test_no_keyboard_escape_hatches(phone, evidence):
    """No SysRq, no text consoles, no SSH"""
    assert phone.sh("cat /proc/sys/kernel/sysrq").out.strip() == "0"
    gettys = phone.sh("pgrep -a agetty || true").out.strip()
    evidence.note(f"getty processes: {gettys or 'none'}")
    assert gettys == ""
    assert not phone.sh("ss -ltn | grep -q ':22 '").ok


def test_touch_is_delivered(phone, evidence):
    """Touches on the screen do reach the system"""
    _read_events(phone, "MultiTouch", 15)
    time.sleep(1)
    phone.tap(phone.w / 2, phone.h / 2)
    time.sleep(5)
    phone.wait_until("test -f /tmp/ucrom-evcount-MultiTouch", timeout=60, interval=1)
    n = int(phone.sh("cat /tmp/ucrom-evcount-MultiTouch").out.strip() or 0)
    evidence.note(f"touch events delivered for one tap: {n}")
    assert n > 0
