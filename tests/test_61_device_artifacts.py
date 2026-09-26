"""Flashable images for every phone built in this run (out/devices/*/*)."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILT = sorted(p.parent for p in (ROOT / "out" / "devices").glob("*/*/BUILD_INFO"))


def info(d):
    return dict(l.split("=", 1) for l in (d / "BUILD_INFO").read_text().splitlines() if "=" in l)


@pytest.mark.skipif(not BUILT, reason="no device images built")
@pytest.mark.parametrize("d", BUILT, ids=[f"{p.parent.name}-{p.name}" for p in BUILT])
def test_device_images(d, evidence, tmp_path):
    """Boot image structure, checksums and userdata filesystem"""
    i = info(d)
    evidence.note(f"{i['name']} | {i['soc']} | {i['flavor']} | kernel {i['kernel']}")
    # checksums of what is on disk
    r = subprocess.run(["sha256sum", "-c", "--ignore-missing", "SHA256SUMS"], cwd=d,
                       capture_output=True, text=True)
    evidence.note("sha256: " + r.stdout.strip().replace("\n", "; "))
    assert r.returncode == 0
    # boot.img structure
    r = subprocess.run(["unpack_bootimg", "--boot_img", str(d / "boot.img"), "--out", str(tmp_path),
                        "--format", "mkbootimg"], capture_output=True, text=True, check=True)
    hv = int(re.search(r"--header_version (\d+)", r.stdout)[1])
    assert hv == int(i["bootimg_header"])
    assert (tmp_path / "kernel").stat().st_size > 5_000_000
    assert (tmp_path / "ramdisk").stat().st_size > 1_000_000
    if hv >= 2:
        assert (tmp_path / "dtb").read_bytes()[:4] == b"\xd0\x0d\xfe\xed"
    # userdata validation recorded at build time (image may be deleted to save disk)
    v = dict(l.split("=", 1) for l in (d / "VALIDATION").read_text().splitlines() if "=" in l)
    evidence.note("userdata: " + ", ".join(f"{k}={x}" for k, x in v.items()))
    for k in ("sparse_roundtrip", "e2fsck"):
        assert v.get(k) == "ok", k
    assert v.get("rootfs_os_release", v.get("has_rootfs_img")) == "ok"
