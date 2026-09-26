"""ucrom Hardware Check: the checks.

Each check probes one part of the phone and returns a Result:
  PASS    the part is present and answered
  FAIL    the part should be there (device profile says so) but did not work
  ABSENT  not present on this machine (e.g. no modem in the emulator)
  ASK     needs the person holding the phone (heard a sound? saw the flash?)

Checks never fake a pass: anything that cannot be proven from software is
ASK, and the touch UI asks it with big Yes/No buttons.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PASS, FAIL, ABSENT, ASK = "PASS", "FAIL", "ABSENT", "ASK"


@dataclass
class Result:
    id: str
    title: str
    status: str
    detail: str = ""
    question: str = ""          # for ASK: what to confirm
    action: str = ""            # for ASK: command that performs the visible/audible test
    evidence: dict = field(default_factory=dict)


def sh(cmd: str, timeout: float = 15) -> tuple[int, str]:
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def expected_features() -> set[str]:
    """Features the device profile promises (empty in the emulator)."""
    try:
        codename = Path("/etc/ucrom-device").read_text().strip()
        for line in open(f"/usr/share/ucrom/devices/{codename}.conf"):
            if line.startswith("DEVICE_FEATURES="):
                return set(line.split("=", 1)[1].strip().strip('"').split())
    except OSError:
        pass
    return set()


EXPECTED = expected_features()


def missing(feature: str, title: str, cid: str, detail: str) -> Result:
    """Absent hardware: FAIL if the device profile says it should exist."""
    return Result(cid, title, FAIL if feature in EXPECTED else ABSENT, detail)


def input_devices() -> list[dict]:
    devs, cur = [], {}
    try:
        text = Path("/proc/bus/input/devices").read_text()
    except OSError:
        return devs
    for line in text.splitlines() + [""]:
        if not line.strip():
            if cur:
                devs.append(cur)
            cur = {}
            continue
        kind, _, val = line.partition(": ")
        if kind == "N":
            cur["name"] = val.split("=", 1)[1].strip('"')
        elif kind == "S":
            cur["sysfs"] = val.split("=", 1)[1]
        elif kind == "H":
            cur["handlers"] = val.split("=", 1)[1].split()
        elif kind == "B":
            k, _, v = val.partition("=")
            cur[k] = v
    return devs


def is_inhibited(dev: dict) -> bool:
    try:
        return Path("/sys" + dev["sysfs"] + "/inhibited").read_text().strip() == "1"
    except (OSError, KeyError):
        return False


def has_abs_mt(dev: dict) -> bool:
    # ABS bitmap: bit 0x35 (ABS_MT_POSITION_X) set
    bits = dev.get("ABS", "").split()
    if not bits:
        return False
    val = int("".join(b.zfill(16) for b in bits), 16)
    return bool(val >> 0x35 & 1)


# ---------------------------------------------------------------- the checks

def check_system() -> Result:
    osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?', Path("/etc/os-release").read_text(), re.M))
    flavor = Path("/etc/ucrom-flavor").read_text().strip() if Path("/etc/ucrom-flavor").exists() else "?"
    device = Path("/etc/ucrom-device").read_text().strip() if Path("/etc/ucrom-device").exists() else "emulator/generic"
    ok = osr.get("ID") == "ucrom"
    return Result("system", "ucrom system", PASS if ok else FAIL,
                  f"{osr.get('PRETTY_NAME')} | device {device} | flavor {flavor} | kernel {os.uname().release}",
                  evidence={"os": osr, "device": device, "flavor": flavor})


def check_touch() -> Result:
    touch = [d for d in input_devices() if has_abs_mt(d) and not is_inhibited(d)]
    if not touch:
        return missing("touch", "Touchscreen", "touch", "no multi-touch input device")
    return Result("touch", "Touchscreen", PASS, ", ".join(d["name"] for d in touch),
                  evidence={"devices": [d["name"] for d in touch]})


def check_touch_only() -> Result:
    bad, blocked = [], []
    for d in input_devices():
        ev = int(d.get("EV", "0"), 16)
        key = d.get("KEY", "").split()
        # keyboard-like (same rule as udev): EV_KEY with all of KEY_ESC..KEY_S
        # (bits 1..31 of the lowest key-bitmap word)
        keyboard = bool(ev & 0x2) and bool(key) and (int(key[-1], 16) & 0xFFFFFFFE) == 0xFFFFFFFE
        mouse = bool(ev & 0x4) and "REL" in d and int(d.get("REL", "0"), 16) & 0x3
        if keyboard or mouse:
            (blocked if is_inhibited(d) else bad).append(d.get("name", "?"))
    if bad:
        return Result("touch-only", "Keyboard/mouse blocked", FAIL, "NOT blocked: " + ", ".join(bad))
    return Result("touch-only", "Keyboard/mouse blocked", PASS,
                  f"{len(blocked)} keyboard/mouse device(s) present and inhibited" if blocked
                  else "no keyboard or mouse connected", evidence={"blocked": blocked})


def check_buttons() -> Result:
    names = [d["name"] for d in input_devices()]
    phone = [n for n in names if re.search(r"gpio-keys|pwrkey|resin|pon|power button|volume", n, re.I)]
    if not phone:
        return missing("buttons", "Power/volume buttons", "buttons", "no button input devices")
    return Result("buttons", "Power/volume buttons", PASS, ", ".join(phone))


def check_display() -> Result:
    if not os.environ.get("WAYLAND_DISPLAY") or not have("wlr-randr"):
        rc, out = 1, "no compositor session"
    else:
        rc, out = sh("wlr-randr")
    modes = re.findall(r"(\d+)x(\d+) px, ([\d.]+) Hz", out)
    if rc or not modes:
        cards = glob.glob("/sys/class/drm/card*-*")
        if cards:
            return Result("display", "Display", PASS, "DRM outputs: " + ", ".join(Path(c).name for c in cards))
        return missing("display", "Display", "display", out[:200])
    rates = sorted({round(float(m[2])) for m in modes})
    res = max(((int(m[0]), int(m[1])) for m in modes), key=lambda wh: wh[0] * wh[1])
    status = PASS
    detail = f"{res[0]}x{res[1]}, refresh rates: {', '.join(map(str, rates))} Hz"
    if "refresh90" in EXPECTED and max(rates) < 89:
        status, detail = FAIL, detail + " (90 Hz expected)"
    return Result("display", "Display", status, detail, evidence={"modes": modes})


def check_gpu() -> Result:
    if glob.glob("/dev/kgsl-3d0"):
        hybris = bool(sh("ldconfig -p | grep -q libhybris")[0] == 0)
        return Result("gpu", "GPU acceleration", PASS,
                      "Adreno (kgsl) " + ("via libhybris" if hybris else "device node present"))
    renders = glob.glob("/dev/dri/renderD*")
    if renders:
        drv = [Path(os.path.realpath(f"/sys/class/drm/{Path(r).name}/device/driver")).name for r in renders]
        if any(d in ("msm", "msm_dpu", "freedreno") for d in drv):
            return Result("gpu", "GPU acceleration", PASS, "freedreno/msm: " + ", ".join(drv))
        return Result("gpu", "GPU acceleration", ABSENT if "gpu" not in EXPECTED else FAIL,
                      "render node driver(s): " + ", ".join(drv) + " (no hardware 3D)")
    return missing("gpu", "GPU acceleration", "gpu", "software rendering (llvmpipe)")


def check_wifi() -> Result:
    if not have("nmcli"):
        return Result("wifi", "Wi-Fi", FAIL, "NetworkManager missing")
    rc, out = sh("nmcli -t -f DEVICE,TYPE,STATE device")
    wifi = [l for l in out.splitlines() if ":wifi:" in l]
    if not wifi:
        return missing("wifi", "Wi-Fi", "wifi", "no Wi-Fi adapter")
    sh("nmcli device wifi rescan", timeout=20)
    time.sleep(3)
    _, scan = sh("nmcli -t -f SSID device wifi list")
    n = len([s for s in scan.splitlines() if s.strip()])
    return Result("wifi", "Wi-Fi", PASS if n else FAIL, f"{wifi[0]}; {n} network(s) visible")


def check_bluetooth() -> Result:
    rc, out = sh("busctl --system tree org.bluez 2>/dev/null | grep -oE '/org/bluez/hci[0-9]+$' | head -1")
    if rc or not out:
        return missing("bluetooth", "Bluetooth", "bluetooth", "no Bluetooth adapter (BlueZ)")
    adapter = out.strip()
    sh(f"busctl --system set-property org.bluez {adapter} org.bluez.Adapter1 Powered b true")
    _, powered = sh(f"busctl --system get-property org.bluez {adapter} org.bluez.Adapter1 Powered")
    plugins = sh("ps -o args= -C bluetoothd")[1]
    hid_off = "--noplugin=input,hog" in plugins
    ok = "true" in powered
    return Result("bluetooth", "Bluetooth", PASS if ok else FAIL,
                  f"{adapter} powered={'yes' if ok else 'no'}; keyboard/mouse profiles {'disabled' if hid_off else 'ENABLED'}")


def check_modem() -> Result:
    if not have("mmcli"):
        return Result("modem", "Mobile network", FAIL, "ModemManager missing")
    rc, out = sh("mmcli -L")
    m = re.search(r"/Modem/(\d+)", out)
    if not m:
        return missing("calls", "Mobile network (calls/SMS/data)", "modem", "no modem found")
    _, info = sh(f"mmcli -m {m[1]}")
    state = re.search(r"state: '?([^\n']+)", info)
    op = re.search(r"operator name: '?([^\n']+)", info)
    sig = re.search(r"signal quality: '?([^\n']+)", info)
    good = state and state[1].strip() in ("registered", "connected", "enabled")
    return Result("modem", "Mobile network (calls/SMS/data)", PASS if good else FAIL,
                  f"state {state[1] if state else '?'}; operator {op[1] if op else '-'}; signal {sig[1] if sig else '-'}")


def check_audio() -> Result:
    rc, out = sh("pactl list short sinks 2>/dev/null || wpctl status 2>/dev/null")
    sinks = [l for l in out.splitlines() if l.strip() and "auto_null" not in l and "Dummy" not in l]
    if rc or not sinks:
        return missing("audio", "Speaker and microphone", "audio", "no audio output device")
    snd = "/usr/share/sounds/freedesktop/stereo/bell.oga"
    player = "paplay" if have("paplay") else "pw-play"
    return Result("audio", "Speaker and microphone", ASK, f"{len(sinks)} output(s)",
                  question="Did you hear a bell from the speaker?",
                  action=f"{player} {snd}")


def check_camera() -> Result:
    rc, _ = sh("gst-inspect-1.0 droidcamsrc >/dev/null 2>&1")
    if rc == 0:
        return Result("camera", "Cameras", ASK, "Android camera bridge (gst-droid) present",
                      question="Did the camera preview show a live picture?",
                      action="droidian-camera")
    vids = glob.glob("/dev/video*")
    if vids:
        return Result("camera", "Cameras", ASK, ", ".join(vids),
                      question="Did the camera preview show a live picture?", action="megapixels")
    return missing("camera-rear", "Cameras", "camera", "no camera")


def check_popup_camera() -> Result:
    motor = Path("/sys/class/motor")
    if not (motor / "enable").exists():
        return missing("popup-camera", "Pop-up camera", "popup-camera", "no camera motor")
    pos = (motor / "position").read_text().strip()
    return Result("popup-camera", "Pop-up camera", ASK, f"motor present, position {'up' if pos == '0' else 'down'}",
                  question="Did the selfie camera rise and go back down?",
                  action="sh -c 'touch /run/ucrom/front-camera; sleep 3; rm -f /run/ucrom/front-camera'")


def check_fingerprint() -> Result:
    rc, out = sh("busctl --system call org.droidian.fingerprint /org/droidian/fingerprint "
                 "org.droidian.fingerprint GetState 2>&1")
    if rc == 0:
        return Result("fingerprint", "Fingerprint", ASK, "droidian-fpd: " + out,
                      question="Place your finger on the sensor. Did the phone react (vibrate/unlock)?",
                      action="busctl --system call org.droidian.fingerprint /org/droidian/fingerprint org.droidian.fingerprint Identify")
    rc, out = sh("busctl --system call net.reactivated.Fprint /net/reactivated/Fprint/Manager "
                 "net.reactivated.Fprint.Manager GetDefaultDevice 2>&1")
    if rc == 0:
        return Result("fingerprint", "Fingerprint", PASS, "fprintd device: " + out)
    return missing("fingerprint-fod", "Fingerprint", "fingerprint", "no fingerprint service/device")


def check_sensors() -> Result:
    props = {}
    for p in ("HasAccelerometer", "HasAmbientLight", "HasProximity", "HasCompass"):
        rc, out = sh(f"busctl --system get-property net.hadess.SensorProxy /net/hadess/SensorProxy "
                     f"net.hadess.SensorProxy {p}")
        props[p] = rc == 0 and "true" in out
    found = [k[3:] for k, v in props.items() if v]
    if not found:
        return missing("accel", "Sensors", "sensors", "no rotation/light/proximity sensors")
    want = {"accel": "Accelerometer", "light": "AmbientLight", "proximity": "Proximity"}
    lacking = [v for k, v in want.items() if k in EXPECTED and v not in found]
    return Result("sensors", "Sensors", FAIL if lacking else PASS,
                  "found: " + ", ".join(found) + (f"; missing: {', '.join(lacking)}" if lacking else ""))


def check_vibration() -> Result:
    if glob.glob("/sys/class/leds/vibrator*") or glob.glob("/sys/class/timed_output/vibrator") \
            or any("haptic" in d.get("name", "").lower() or "vibra" in d.get("name", "").lower()
                   for d in input_devices()):
        return Result("vibration", "Vibration", ASK, "vibrator present",
                      question="Did the phone vibrate?",
                      action="fbcli -t 2 -E phone-incoming-call")
    return missing("vibration", "Vibration", "vibration", "no vibration motor")


def check_flashlight() -> Result:
    leds = [p for p in glob.glob("/sys/class/leds/*") if re.search(r"flash|torch", p)]
    if not leds:
        return missing("flashlight", "Flashlight", "flashlight", "no flash LED")
    return Result("flashlight", "Flashlight", ASK, ", ".join(Path(l).name for l in leds),
                  question="Did the flashlight turn on for a moment?",
                  action=f"sh -c 'echo 255 > {leds[0]}/brightness; sleep 1; echo 0 > {leds[0]}/brightness'")


def check_nfc() -> Result:
    rc, out = sh("busctl --system call org.sailfishos.nfc.daemon / org.sailfishos.nfc.Daemon GetAdapters 2>&1")
    if rc == 0:
        return Result("nfc", "NFC", PASS, out)
    return missing("nfc", "NFC", "nfc", "no NFC adapter")


def check_gps() -> Result:
    rc, out = sh("mmcli -m any --location-status 2>&1")
    if rc == 0 and "gps" in out.lower():
        return Result("gps", "GPS", PASS, "modem GNSS available")
    if Path("/usr/libexec/geoclue").exists() or have("geoclue"):
        return missing("gps", "GPS", "gps", "geoclue present, no GNSS source")
    return missing("gps", "GPS", "gps", "no location service")


def check_battery() -> Result:
    rc, out = sh("upower -e | grep -i battery | head -1")
    if rc or not out:
        return missing("battery", "Battery and charging", "battery", "no battery (mains/emulator)")
    _, info = sh(f"upower -i {out}")
    pct = re.search(r"percentage:\s+(\S+)", info)
    st = re.search(r"state:\s+(\S+)", info)
    return Result("battery", "Battery and charging", PASS,
                  f"{pct[1] if pct else '?'} ({st[1] if st else '?'})")


def check_alert_slider() -> Result:
    p = Path("/proc/tristatekey/tri_state")
    if not p.exists():
        return missing("alert-slider", "Alert slider", "alert-slider", "no alert slider")
    pos = {"1": "up/silent", "2": "middle/vibrate", "3": "down/ring"}.get(p.read_text().strip(), "?")
    return Result("alert-slider", "Alert slider", ASK, f"now: {pos}",
                  question="Move the slider. Did the ring/vibrate/silent icon follow it?")


ALL_CHECKS = [check_system, check_touch, check_touch_only, check_buttons, check_display, check_gpu,
              check_wifi, check_bluetooth, check_modem, check_audio, check_camera, check_popup_camera,
              check_fingerprint, check_sensors, check_vibration, check_flashlight, check_nfc, check_gps,
              check_battery, check_alert_slider]


def run_all() -> list[Result]:
    results = []
    for fn in ALL_CHECKS:
        try:
            results.append(fn())
        except Exception as e:  # a broken check must never look like a pass
            name = fn.__name__.removeprefix("check_")
            results.append(Result(name, name, FAIL, f"check crashed: {e!r}"))
    return results


def save_report(results: list[Result], answers: dict | None = None, directory: Path | None = None) -> Path:
    answers = answers or {}
    directory = directory or Path.home()
    directory.mkdir(parents=True, exist_ok=True)
    final = []
    for r in results:
        d = asdict(r)
        if r.status == ASK and r.id in answers:
            d["status"] = PASS if answers[r.id] else FAIL
            d["detail"] += f" | person confirmed: {'yes' if answers[r.id] else 'no'}"
        final.append(d)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    (directory / "ucrom-hardware-report.json").write_text(json.dumps({"time": stamp, "results": final}, indent=2))
    rows = "".join(
        f"<tr class='{d['status'].lower()}'><td>{d['title']}</td><td>{d['status']}</td><td>{d['detail']}</td></tr>"
        for d in final)
    html = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>ucrom Hardware Check</title>
<style>body{{font-family:sans-serif;margin:16px}}td{{padding:6px;border-bottom:1px solid #ccc}}
.pass td:nth-child(2){{color:#2a7}}.fail td:nth-child(2){{color:#c33}}.absent td:nth-child(2){{color:#888}}
.ask td:nth-child(2){{color:#b80}}</style>
<h1>ucrom Hardware Check</h1><p>{stamp}</p><table>{rows}</table>"""
    out = directory / "ucrom-hardware-report.html"
    out.write_text(html)
    return out
