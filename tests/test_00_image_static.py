"""The built ucrom root filesystem, inspected on disk (no boot needed)."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FS = ROOT / "build" / "rootfs-mainline"

pytestmark = pytest.mark.skipif(not (FS / "usr").exists(), reason="rootfs not built (make rootfs-mainline)")


def installed(pkg):
    r = subprocess.run(["chroot", str(FS), "dpkg-query", "-W", "-f=${Status}", pkg],
                       capture_output=True, text=True, check=False)
    return "install ok installed" in r.stdout


def read(p):
    return (FS / p.lstrip("/")).read_text()


def test_branding(evidence):
    """The OS identifies itself as ucrom"""
    osr = read("/etc/os-release")
    evidence.note(osr.strip().replace("\n", " | "))
    assert re.search(r'^NAME="ucrom"$', osr, re.M)
    assert re.search(r"^ID=ucrom$", osr, re.M)
    assert read("/etc/hostname").strip() == "ucrom"
    assert "ucrom" in read("/etc/issue")


@pytest.mark.parametrize("pkg", [
    "phosh", "phoc", "phosh-osk-stub", "gnome-calls", "chatty", "epiphany-browser",
    "gnome-calculator", "gnome-console", "network-manager", "modemmanager", "bluez",
    "feedbackd", "iio-sensor-proxy", "flatpak", "pipx", "git", "qemu-guest-agent"])
def test_packages(pkg):
    """Phone shell, apps and services are installed"""
    assert installed(pkg), pkg


def test_node22_for_ai_agents(evidence):
    """Node.js 22 is present for Claude Code / Codex"""
    r = subprocess.run(["chroot", str(FS), "/opt/node/bin/node", "--version"],
                       capture_output=True, text=True, check=True)
    evidence.note(f"node {r.stdout.strip()}")
    assert r.stdout.startswith("v22.")


def test_udev_touch_only_rule(evidence):
    """Touch-only udev rule is installed and valid"""
    rule = FS / "etc/udev/rules.d/90-ucrom-touch-only.rules"
    text = rule.read_text()
    for needed in ('ATTR{inhibited}="1"', 'ENV{LIBINPUT_IGNORE_DEVICE}="1"', "ID_INPUT_KEYBOARD",
                   "ID_INPUT_MOUSE", "ID_INPUT_TOUCHPAD", 'ATTRS{id/bustype}=="0003"',
                   'ATTRS{id/bustype}=="0005"'):
        assert needed in text, needed
    # use the image's own udevadm (the build host may have none)
    r = subprocess.run(["chroot", str(FS), "udevadm", "verify", "--no-style",
                        "/etc/udev/rules.d/90-ucrom-touch-only.rules"], capture_output=True, text=True)
    evidence.note(f"udevadm verify: rc={r.returncode} {r.stdout.strip() or r.stderr.strip()}")
    assert r.returncode == 0, r.stdout + r.stderr


def test_hid_drivers_blocked():
    """USB/Bluetooth keyboard & mouse drivers can never load"""
    conf = read("/etc/modprobe.d/ucrom-no-hid.conf")
    for mod in ("usbhid", "hid_generic", "hidp", "uhid"):
        assert f"install {mod} /bin/false" in conf, mod


def test_bluetooth_input_plugins_off():
    """BlueZ cannot pair keyboards or mice"""
    drop = read("/etc/systemd/system/bluetooth.service.d/90-ucrom-no-hid.conf")
    assert "--noplugin=input,hog" in drop


def test_no_text_console():
    """No login consoles, SysRq off, no SSH server, root locked"""
    for unit in ("getty@.service", "serial-getty@.service", "console-getty.service", "autovt@.service"):
        link = FS / "etc/systemd/system" / unit
        assert link.is_symlink() and str(link.readlink()) == "/dev/null", unit
    assert "kernel.sysrq = 0" in read("/etc/sysctl.d/90-ucrom.conf")
    logind = read("/etc/systemd/logind.conf.d/90-ucrom.conf")
    assert "NAutoVTs=0" in logind and "HandlePowerKey=ignore" in logind
    assert not installed("openssh-server")
    shadow = read("/etc/shadow")
    assert re.search(r"^root:!", shadow, re.M), "root must have no usable password"


def test_on_screen_keyboard_default():
    """The on-screen keyboard is on by default"""
    db = read("/etc/dconf/db/local.d/00-ucrom")
    assert "screen-keyboard-enabled=true" in db
    assert (FS / "etc/dconf/db/local").exists(), "dconf database compiled"


def test_ucrom_apps_installed():
    """App Hub, Hardware Check and the hardware helpers are installed"""
    for f in ("usr/bin/ucrom-apphub", "usr/bin/ucrom-hwcheck", "usr/bin/ucrom-alertslider",
              "usr/bin/ucrom-popup-camera", "usr/bin/ucrom-fod", "usr/bin/ucrom-refresh-rate",
              "usr/share/applications/io.ucrom.AppHub.desktop",
              "usr/share/applications/io.ucrom.HardwareCheck.desktop"):
        p = FS / f
        if p.is_symlink():  # absolute links resolve inside the image, not on the host
            target = Path(os.readlink(p))
            p = FS / str(target).lstrip("/") if target.is_absolute() else p.parent / target
        assert p.exists(), f


def test_network_manager_manages_all_devices():
    """NetworkManager manages every network device (USB Ethernet, USB tethering too)"""
    override = FS / "etc/NetworkManager/conf.d/10-globally-managed-devices.conf"
    assert override.exists(), "Ubuntu's 'only Wi-Fi and WWAN are managed' default must be overridden"
    assert not [ln for ln in override.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
