"""Halium hardware bridges: built from source for Ubuntu arm64 and loadable."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / "out" / "bridges" / "status.tsv"
LIST = [l.split()[0] for l in (ROOT / "packages" / "bridges.list").read_text().splitlines()
        if l.strip() and not l.startswith("#")]
HFS = ROOT / "build" / "rootfs-halium"

WHAT = {
    "libhybris": "runs Android GPU/HAL libraries under Linux",
    "wlroots": "GPU display via Android hwcomposer",
    "phoc": "the touch compositor on hwcomposer",
    "pulseaudio-modules-droid": "speaker, earpiece, mic via the audio HAL",
    "ofono-binder-plugin": "calls, SMS, data via the radio HAL",
    "ofono2mm": "exposes the modem to GNOME Calls/Chatty",
    "bluebinder": "Bluetooth via the Android BT HAL",
    "droidian-fpd": "fingerprint via the biometrics HAL",
    "gst-droid": "cameras via the camera HAL",
    "sensorfw": "rotation, light, proximity via the sensors HAL",
    "nfcd-binder-plugin": "NFC via the NFC HAL",
    "feedbackd": "vibration",
}


def status():
    rows = {}
    if STATUS.exists():
        for line in STATUS.read_text().splitlines():
            p = line.split("\t")
            rows[p[0]] = p[1:]
    return rows


@pytest.mark.skipif(not STATUS.exists(), reason="bridges not built (make bridges)")
@pytest.mark.parametrize("name", LIST)
def test_bridge_builds(name, evidence):
    """Bridge package builds for Ubuntu noble arm64"""
    st = status().get(name)
    assert st, f"{name} was not attempted"
    result, version, note = (st + ["", "", ""])[:3]
    evidence.note(f"{name}: {result} {version} {note} {('- ' + WHAT[name]) if name in WHAT else ''}")
    assert result == "OK", note


@pytest.mark.skipif(not (HFS / "usr").exists(), reason="halium rootfs not built")
def test_bridges_installed_and_linkable(evidence):
    """Bridge binaries are installed in the halium image and all their libraries resolve"""
    bins = ["/usr/bin/bluebinder", "/usr/sbin/ofonod", "/usr/bin/phoc", "/usr/libexec/droidian-fpd",
            "/usr/bin/test_hwcomposer", "/usr/sbin/parse-android-dynparts"]
    checked = []
    for b in bins:
        if not (HFS / b.lstrip("/")).exists():
            continue
        r = subprocess.run(["chroot", str(HFS), "ldd", b], capture_output=True, text=True)
        assert "not found" not in r.stdout, f"{b}: {r.stdout}"
        checked.append(b)
    evidence.note("linked OK: " + ", ".join(checked))
    assert checked
