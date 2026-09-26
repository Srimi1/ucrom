"""Every supported chip and phone profile checks out against real kernel trees."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "out" / "validate-socs.json"


def test_all_profiles_resolve(evidence):
    """All phone profiles resolve to a chip profile"""
    r = subprocess.run([str(ROOT / "scripts" / "resolve-device.sh"), "--list"],
                       capture_output=True, text=True, check=True)
    lines = r.stdout.strip().splitlines()[1:]
    for l in lines:
        evidence.note(" ".join(l.split()))
    assert len(lines) >= 15
    assert any("oneplus-hotdog" in l and "primary" in l for l in lines)


@pytest.mark.skipif(not RES.exists(), reason="run make validate-socs")
def test_kernel_sources_and_device_trees(evidence):
    """Kernel branches, defconfigs and device trees exist upstream"""
    rows = json.loads(RES.read_text())
    fails = [r for r in rows if r["result"] == "FAIL"]
    by = {}
    for r in rows:
        by.setdefault(r["result"], 0)
        by[r["result"]] += 1
    evidence.note(f"checks: {by}")
    for r in fails:
        evidence.note(f"FAIL {r['device']} {r['check']}: {r['detail']}")
    assert not fails
