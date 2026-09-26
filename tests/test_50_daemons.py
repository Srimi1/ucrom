"""ucrom's own OnePlus hardware helpers, run inside the emulator against
simulated hardware (virtual input devices, fake sysfs, fake D-Bus services).
They are the same programs that run on the phone."""

import json
import time

import pytest

pytestmark = pytest.mark.vm

PY = "PYTHONPATH=/usr/lib/ucrom/daemons python3"


SLIDER = r"""
cat > /tmp/slider.py <<'PY'
# A virtual OnePlus alert slider: same input device name and events as the
# vendor tri-state-key driver (KEY_F3, value = position).
import sys, time
from evdev import UInput, ecodes as e
pos = int(sys.argv[1])
ui = UInput({e.EV_KEY: [e.KEY_F3]}, name="oplus,hall_tri_state_key")
time.sleep(1)
open("/tmp/hw/ucrom-input-map", "w").write(f"oplus,hall_tri_state_key={ui.device.path}\n")
time.sleep(5)
ui.write(e.EV_KEY, e.KEY_F3, pos); ui.syn()
ui.write(e.EV_KEY, e.KEY_F3, 0); ui.syn()
time.sleep(2)
PY
rm -rf /tmp/hw && mkdir -p /tmp/hw/proc/tristatekey && echo 3 > /tmp/hw/proc/tristatekey/tri_state
chmod -R a+rwX /tmp/hw
"""


def test_alert_slider(phone, evidence):
    """Alert slider: up/middle/down switch silent / vibrate / ring"""
    phone.sh(SLIDER)
    for pos, want in ((1, "up silent"), (2, "middle quiet"), (3, "down full")):
        phone.sh(f"rm -f /tmp/hw/ucrom-input-map; nohup python3 /tmp/slider.py {pos} >/tmp/slider.log 2>&1 &")
        phone.wait_until("test -s /tmp/hw/ucrom-input-map", timeout=20, interval=0.5)
        if pos == 1:
            dev = phone.sh("udevadm settle; udevadm info -q property -n $(sed 's/.*=//' /tmp/hw/ucrom-input-map)").out
            evidence.note("virtual slider is ID_INPUT_KEY=1, not a keyboard, not blocked: "
                          + str("ID_INPUT_KEYBOARD" not in dev and "UCROM_BLOCKED" not in dev))
            assert "UCROM_BLOCKED" not in dev, "the slider must not be blocked by the touch-only policy"
        r = phone.sh(f"UCROM_HW_ROOT=/tmp/hw UCROM_STATE_DIR=/tmp/hwstate timeout 20 {PY} -m ucromhw.alertslider --once; "
                     "cat /tmp/hwstate/alertslider", user=True, timeout=60)
        got = r.out.strip().splitlines()[-1] if r.out.strip() else ""
        prof = phone.sh("gsettings get org.sigxcpu.feedbackd profile", user=True).out.strip().strip("'")
        evidence.note(f"slider position {pos} -> '{got}', feedbackd profile '{prof}'")
        assert got == want, r.out + r.err
        assert prof == want.split()[1]


MOTOR_SIM = r"""
set -e
rm -rf /tmp/hw2 && mkdir -p /tmp/hw2/sys/class/motor /tmp/hw2/run/ucrom /tmp/hw2/proc
mkdir -p /tmp/hw2/sys/bus/iio/devices/iio:device0
cd /tmp/hw2/sys/class/motor
echo 1 > position; echo 0 > direction; : > enable
cd /tmp/hw2/sys/bus/iio/devices/iio:device0
echo 0 > in_accel_x_raw; echo 0 > in_accel_y_raw; echo 981 > in_accel_z_raw; echo 0.01 > in_accel_scale
# the "motor": when 1 is written to enable, move to the requested direction
cat > /tmp/motor-sim.sh <<'SH'
while true; do
  if [ -s /tmp/hw2/sys/class/motor/enable ]; then
    d=$(cat /tmp/hw2/sys/class/motor/direction)
    : > /tmp/hw2/sys/class/motor/enable
    sleep 0.3
    if [ "$d" = 1 ]; then echo 0 > /tmp/hw2/sys/class/motor/position; else echo 1 > /tmp/hw2/sys/class/motor/position; fi
    echo "$(date +%s.%N) dir=$d" >> /tmp/motor-moves.log
  fi
  sleep 0.05
done
SH
rm -f /tmp/motor-moves.log
nohup bash /tmp/motor-sim.sh >/dev/null 2>&1 &
ln -s /proc/* /tmp/hw2/proc/ 2>/dev/null || true
UCROM_HW_ROOT=/tmp/hw2 UCROM_STATE_DIR=/tmp/hw2state nohup %s -m ucromhw.popupcamera --mode mainline > /tmp/popup.log 2>&1 &
sleep 3
""" % PY


def test_popup_camera(phone, evidence):
    """Pop-up camera rises with the front camera and drops on a fall"""
    phone.sh(MOTOR_SIM, timeout=60)
    pos = lambda: phone.sh("cat /tmp/hw2/sys/class/motor/position").out.strip()
    assert pos() == "1", "starts down"
    phone.sh("touch /tmp/hw2/run/ucrom/front-camera")
    phone.wait_until("[ $(cat /tmp/hw2/sys/class/motor/position) = 0 ]", timeout=20, interval=1)
    evidence.note("front camera opened -> motor up")
    phone.sh("rm /tmp/hw2/run/ucrom/front-camera")
    phone.wait_until("[ $(cat /tmp/hw2/sys/class/motor/position) = 1 ]", timeout=20, interval=1)
    evidence.note("front camera closed -> motor down")
    # up again, then drop the phone (accelerometer reads ~0 g)
    phone.sh("touch /tmp/hw2/run/ucrom/front-camera")
    phone.wait_until("[ $(cat /tmp/hw2/sys/class/motor/position) = 0 ]", timeout=20, interval=1)
    t0 = phone.sh("date +%s.%N").out.strip()
    phone.sh("cd /tmp/hw2/sys/bus/iio/devices/iio:device0 && echo 5 > in_accel_z_raw")
    phone.wait_until("[ $(cat /tmp/hw2/sys/class/motor/position) = 1 ]", timeout=10, interval=0.5)
    log = phone.sh("cat /tmp/popup.log; tail -3 /tmp/motor-moves.log").out
    evidence.note(f"free fall at {t0}; helper log:\n" + log.strip())
    assert "free fall" in log
    phone.sh("pkill -f ucromhw.popupcamera; pkill -f motor-sim.sh; true")


def test_dumpsys_parser():
    """Front-camera detection from Android's camera service output"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ucrom"))
    from ucromhw.popupcamera import parse_dumpsys_front_open
    assert parse_dumpsys_front_open("== Camera device 1 dynamic info: ==\n  Device 1 is open. Client instance dump:\n")
    assert not parse_dumpsys_front_open("== Camera device 0 dynamic info: ==\n  Device 0 is open.\n  Device 1 is closed.\n")
    assert parse_dumpsys_front_open("Active Camera Clients:\n  Camera ID: 1\n    Client PID: 1234\n")
    assert not parse_dumpsys_front_open("")


FAKE_FPD = r"""
cat > /etc/dbus-1/system.d/ucrom-test-fpd.conf <<'XML'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><policy context="default">
 <allow own="org.droidian.fingerprint"/><allow send_destination="org.droidian.fingerprint"/>
</policy></busconfig>
XML
busctl call org.freedesktop.DBus / org.freedesktop.DBus ReloadConfig >/dev/null
cat > /tmp/fake-fpd.py <<'PY'
# Stand-in for droidian-fpd (which needs the Android fingerprint HAL):
# same bus name, object, interface, methods and signals.
from gi.repository import Gio, GLib
XML = '''<node><interface name="org.droidian.fingerprint">
<method name="Identify"><arg type="i" direction="out"/></method>
<method name="GetState"><arg type="s" direction="out"/></method>
<signal name="StateChanged"><arg type="s"/></signal>
<signal name="Identified"><arg type="s"/></signal>
</interface></node>'''
bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
state = ["FPSTATE_IDLE"]
def emit(name, value):
    bus.emit_signal(None, "/org/droidian/fingerprint", "org.droidian.fingerprint", name, GLib.Variant("(s)", (value,)))
def call(conn, sender, path, iface, method, params, inv):
    if method == "GetState":
        inv.return_value(GLib.Variant("(s)", (state[0],)))
    elif method == "Identify":
        open("/tmp/fpd-identify-called", "w").write("1")
        state[0] = "FPSTATE_IDENTIFYING"; emit("StateChanged", state[0])
        inv.return_value(GLib.Variant("(i)", (0,)))
        def touch():   # the finger lands on the sensor 2 s later
            emit("Identified", "right-thumb")
            state[0] = "FPSTATE_IDLE"; emit("StateChanged", state[0])
            return False
        GLib.timeout_add(2000, touch)
bus.register_object("/org/droidian/fingerprint", Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], call, None, None)
Gio.bus_own_name_on_connection(bus, "org.droidian.fingerprint", 0, None, None)
GLib.MainLoop().run()
PY
nohup python3 /tmp/fake-fpd.py > /tmp/fake-fpd.log 2>&1 &
mkdir -p /tmp/hw3/sys/kernel/oplus_display && echo 0 > /tmp/hw3/sys/kernel/oplus_display/dimlayer_bl_en
chmod -R a+rw /tmp/hw3
sleep 2
"""


def test_fingerprint_unlock_and_sensor_light(phone, evidence):
    """In-display fingerprint: locking starts a scan, the sensor lights up, a match unlocks"""
    phone.sh(FAKE_FPD, timeout=60)
    phone.sh(f"UCROM_HW_ROOT=/tmp/hw3 UCROM_STATE_DIR=/tmp/hw3state nohup {PY} -m ucromhw.fod > /tmp/fod.log 2>&1 &",
             user=True)
    time.sleep(4)
    # lock the phone
    phone.sh("gdbus call --session -d org.gnome.ScreenSaver -o /org/gnome/ScreenSaver "
             "-m org.gnome.ScreenSaver.SetActive true", user=True)
    phone.wait_until("test -f /tmp/fpd-identify-called", timeout=20, interval=1)
    evidence.screenshot(phone, "locked-scanning")
    lit = phone.sh("cat /tmp/hw3/sys/kernel/oplus_display/dimlayer_bl_en; cat /tmp/hw3state/fod-light 2>/dev/null").out
    evidence.note("while scanning: dimlayer_bl_en/light = " + lit.replace("\n", " "))
    phone.wait_until("gdbus call --session -d org.gnome.ScreenSaver -o /org/gnome/ScreenSaver "
                     "-m org.gnome.ScreenSaver.GetActive | grep -q false", timeout=20, interval=1, user=True)
    time.sleep(2)
    evidence.screenshot(phone, "unlocked-by-fingerprint")
    log = phone.sh("cat /tmp/fod.log; cat /tmp/hw3state/fod-unlock; cat /tmp/hw3/sys/kernel/oplus_display/dimlayer_bl_en").out
    evidence.note(log.strip())
    assert "right-thumb" in log
    assert "sensor light on" in log and "sensor light off" in log
    assert log.strip().endswith("0"), "sensor light is off again after the scan"
    phone.sh("pkill -f ucromhw.fod; pkill -f fake-fpd.py; rm -f /etc/dbus-1/system.d/ucrom-test-fpd.conf; true")


def test_refresh_rate_helper(phone, evidence):
    """Refresh-rate helper finds the panel and applies a mode"""
    r = phone.sh(f"{PY} -m ucromhw.refreshrate 60 2>&1; wlr-randr", user=True)
    evidence.note(r.out.strip()[:600])
    assert r.ok and " -> " in r.out


def test_hardware_check_in_emulator(phone, evidence):
    """Hardware Check runs and tells the truth about the emulator"""
    r = phone.sh("ucrom-hwcheck --auto 2>/dev/null", user=True, timeout=180)
    results = {x["id"]: x for x in json.loads(r.out)}
    for x in results.values():
        evidence.note(f"{x['title']}: {x['status']} - {x['detail']}")
    for must in ("system", "touch", "touch-only", "display"):
        assert results[must]["status"] == "PASS", must
    # nothing that the emulator lacks may be reported as working
    for absent in ("modem", "fingerprint", "popup-camera", "alert-slider", "nfc", "gpu"):
        assert results[absent]["status"] == "ABSENT", absent
    assert not [x for x in results.values() if x["status"] == "FAIL"]
    assert "ucrom-hardware-report.html" in phone.sh("ls /home/ucrom").out
