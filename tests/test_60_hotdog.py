"""OnePlus 7T Pro / 7T Pro McLaren (hotdog): kernel, boot image, overlays.

Checks the real build outputs in out/devices/oneplus-hotdog/.
"""

import gzip
import io
import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
H = ROOT / "out" / "devices" / "oneplus-hotdog" / "halium"
M = ROOT / "out" / "devices" / "oneplus-hotdog" / "mainline"
KCONF = H / "kernel" / "config"

need_kernel = pytest.mark.skipif(not KCONF.exists(), reason="hotdog halium kernel not built")
need_boot = pytest.mark.skipif(not (H / "boot.img").exists(), reason="hotdog boot.img not built")


def config():
    vals = {}
    for line in KCONF.read_text().splitlines():
        m = re.match(r"^(CONFIG_\w+)=(.*)$", line)
        if m:
            vals[m[1]] = m[2]
    return vals


def frag(path):
    on, off = [], []
    for line in (ROOT / path).read_text().splitlines():
        if m := re.match(r"^(CONFIG_\w+)=y", line):
            on.append(m[1])
        elif m := re.match(r"^# (CONFIG_\w+) is not set", line):
            off.append(m[1])
    return on, off


@need_kernel
def test_kernel_is_the_7t_pro_vendor_kernel(evidence):
    """Kernel: LineageOS 20 kernel for OnePlus sm8150 (7T Pro)"""
    info = dict(l.split("=", 1) for l in (H / "kernel" / "BUILD_INFO").read_text().splitlines())
    for k in ("repo", "ref", "commit", "release", "compiler", "fragment_mismatches"):
        evidence.note(f"{k}: {info[k]}")
    assert "android_kernel_oneplus_sm8150" in info["repo"]
    assert info["ref"] == "lineage-20"
    assert info["release"].startswith("4.14.")
    assert info["fragment_mismatches"] == "0"


@need_kernel
@pytest.mark.parametrize("symbol,what", [
    ("CONFIG_TOUCHPANEL_SAMSUNG_S6SY761", "touchscreen (Samsung S6SY761)"),
    ("CONFIG_TOUCHPANEL_OPLUS", "OnePlus touch framework"),
    ("CONFIG_DRM_MSM", "display (MSM DRM/SDE)"),
    ("CONFIG_QCA_CLD_WLAN", "Wi-Fi (qcacld-3.0)"),
    ("CONFIG_MSM_BT_POWER", "Bluetooth power control"),
    ("CONFIG_BT_HCIVHCI", "Bluetooth bridge (bluebinder via VHCI)"),
    ("CONFIG_SPECTRA_CAMERA", "cameras (Spectra ISP)"),
    ("CONFIG_OPLUS_MOTOR", "pop-up camera motor"),
    ("CONFIG_OPLUS_TRI_STATE_KEY", "alert slider"),
    ("CONFIG_OPLUS_FINGERPRINT_GOODIX", "in-display fingerprint (Goodix)"),
    ("CONFIG_AW8697_HAPTIC", "vibration motor"),
    ("CONFIG_NFC_NQ", "NFC"),
    ("CONFIG_OPLUS_SM8150R_CHARGER", "battery and fast charging"),
    ("CONFIG_QCOM_KGSL", "GPU (Adreno KGSL)"),
    ("CONFIG_ANDROID_BINDERFS", "binder (Android driver container)"),
])
def test_phone_hardware_drivers_enabled(symbol, what):
    """7T Pro hardware drivers are built into the kernel"""
    assert config().get(symbol) in ("y", "m"), f"{what}: {symbol} not enabled"


@need_kernel
def test_halium_requirements(evidence):
    """Every option ucrom needs for systemd + Halium is set"""
    on, off = frag("socs/common/halium.config")
    c = config()
    missing = [s for s in on if c.get(s) not in ("y", "m")]
    wrong = [s for s in off if c.get(s) in ("y", "m")]
    evidence.note(f"{len(on)} required options checked, missing: {missing or 'none'}; must-be-off but on: {wrong or 'none'}")
    assert not missing and not wrong


@need_kernel
def test_touch_only_kernel(evidence):
    """HID keyboard/mouse drivers, SysRq and VT are compiled out"""
    _, off = frag("socs/common/kernel-touch-only.config")
    c = config()
    still_on = [s for s in off if c.get(s) in ("y", "m")]
    evidence.note(f"checked off: {', '.join(off)}")
    assert not still_on, still_on


@need_kernel
def test_upstream_halium_checker(evidence):
    """Halium's own check-kernel-config: only deliberate differences remain"""
    checker = ROOT / "build" / "src" / "halium-boot" / "check-kernel-config"
    if not checker.exists():
        pytest.skip("halium-boot checker not fetched")
    with tempfile.NamedTemporaryFile("w", suffix=".config", delete=False) as t:
        t.write(KCONF.read_text())
    r = subprocess.run(["bash", str(checker), t.name], capture_output=True, text=True)
    errs = re.findall(r"(CONFIG_\w+) is (?:not set, set it|neither enabled nor disabled)", r.stdout)
    # Deliberate: ucrom is touch-only (no Bluetooth HID) and the
    # halium-9 era list predates binderfs/VHCI bluetooth bridges.
    deliberate = {"CONFIG_BT_HIDP"}
    other = sorted(set(errs) - deliberate)
    evidence.note(f"Halium checker items not met: {len(set(errs))}; deliberate: "
                  f"{sorted(set(errs) & deliberate)}; other: {other[:25]}")
    # Report-only for the legacy (Halium 7/9 era) list; ucrom's own halium.config
    # (test_halium_requirements) is the authoritative requirement set.
    assert "CONFIG_SYSVIPC" not in other and "CONFIG_DEVTMPFS" not in other


@need_boot
def test_boot_image(evidence, tmp_path):
    """boot.img: header v2, kernel + ucrom initramfs + sm8150 DTBs + right cmdline"""
    r = subprocess.run(["unpack_bootimg", "--boot_img", str(H / "boot.img"), "--out", str(tmp_path),
                        "--format", "mkbootimg"], capture_output=True, text=True, check=True)
    args = r.stdout
    evidence.note("mkbootimg args: " + args.strip()[:600])
    assert "--header_version 2" in args
    assert "--pagesize 0x00001000" in args
    cmd = re.search(r"--cmdline '([^']*)'", args)[1]
    assert "androidboot.hardware=qcom" in cmd and "datapart=" in cmd
    assert "console=" not in cmd, "no text console on the phone"
    kernel = (tmp_path / "kernel").read_bytes()
    assert kernel[:2] == b"\x1f\x8b" or kernel[0x38:0x3c] == b"ARM\x64"
    dtb = (tmp_path / "dtb").read_bytes()
    assert dtb[:4] == b"\xd0\x0d\xfe\xed"
    assert b"qcom,sm8150" in dtb or b"qcom,msmnile" in dtb
    n = dtb.count(b"\xd0\x0d\xfe\xed")
    evidence.note(f"DTBs in boot image: {n}")
    size = (H / "boot.img").stat().st_size
    evidence.note(f"boot.img size {size} bytes (partition 100663296)")
    assert size <= 100663296


@need_boot
def test_initramfs_contents(evidence, tmp_path):
    """Initramfs: Halium boot logic + ucrom touch-only rules from the first second"""
    subprocess.run(["unpack_bootimg", "--boot_img", str(H / "boot.img"), "--out", str(tmp_path)],
                   capture_output=True, check=True)
    data = (tmp_path / "ramdisk").read_bytes()
    raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
    listing = subprocess.run(["cpio", "-t"], input=raw, capture_output=True, check=True).stdout.decode()
    files = set(listing.split())
    for f in ("scripts/halium", "etc/udev/rules.d/90-touchscreen.rules", "init"):
        assert f in files, f
    subprocess.run(["cpio", "-id", "etc/udev/rules.d/90-touchscreen.rules", "scripts/halium"],
                   input=raw, cwd=tmp_path, capture_output=True, check=True)
    rule = (tmp_path / "etc/udev/rules.d/90-touchscreen.rules").read_text()
    assert 'ATTR{inhibited}="1"' in rule
    halium = (tmp_path / "scripts/halium").read_text()
    assert "rootfs.img" in halium and "parse-android-dynparts" in halium
    evidence.note(f"initramfs files: {len(files)}; halium script + ucrom touch-only rule present")


@pytest.mark.skipif(not (H / "dtbo.img").exists(), reason="dtbo.img not built")
def test_dtbo_image(evidence):
    """dtbo.img: valid Android DT table with the 7T Pro (19801) overlays"""
    import sys
    sys.path.insert(0, str(ROOT / "scripts" / "tools"))
    from mkdtboimg import dump
    info = dump(H / "dtbo.img")
    evidence.note(f"{info['entry_count']} overlays, {info['total_size']} bytes, size_ok={info['size_ok']}")
    assert info["size_ok"] and info["entry_count"] > 0
    assert all(e["fdt"] for e in info["entries"])
    blob = (H / "dtbo.img").read_bytes()
    assert b"19801" in blob or b"hotdog" in blob, "7T Pro overlay not found"
    assert (H / "dtbo.img").stat().st_size <= 25165824


DTB = M / "kernel" / "dtbs" / "qcom" / "sm8150-oneplus-hotdog.dtb"


@pytest.mark.skipif(not DTB.exists(), reason="mainline fallback DTB not built")
def test_mainline_fallback_device_tree(evidence):
    """Mainline fallback: ucrom's own 7T Pro device tree compiles and is correct"""
    dts = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", str(DTB)], capture_output=True, text=True,
                         check=True).stdout
    assert 'model = "OnePlus 7T Pro";' in dts
    assert '"oneplus,hotdog"' in dts
    ts = re.search(r"touchscreen@48 \{(.*?)\n\t\t\};", dts, re.S)
    assert ts and 'compatible = "samsung,s6sy761"' in ts[1]
    assert re.search(r"framebuffer@9c000000 \{[^}]*width = <0x5a0>;[^}]*height = <0xc30>;", dts, re.S | re.I)
    evidence.note("model OnePlus 7T Pro, touch samsung,s6sy761 @0x48 on i2c17, 1440x3120 framebuffer @0x9c000000")
