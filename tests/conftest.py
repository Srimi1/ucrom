"""Shared fixtures for the ucrom test suite.

VM tests share one booted emulator phone (session fixture `phone`); files are
numbered so pytest runs them in a sensible order (boot -> policy -> UX -> apps
-> daemons). Every test can attach evidence (screenshots, notes) that ends up
in docs/test-report/ with --ucrom-report.
"""

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from vm import PhoneVM, VMError

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "docs" / "test-report"
# Only `--ucrom-report` (make report) writes into docs/; any other run keeps
# its evidence under build/ so it never mixes into the committed report.
EVIDENCE_DIR = ROOT / "build" / "test-evidence"
STAGING = ROOT / "build" / "test-report-staging"
SHOTS = EVIDENCE_DIR / "screenshots"
BUILD = ROOT / "build"
OUT = ROOT / "out"

_records: dict[str, dict] = {}


def pytest_addoption(parser):
    parser.addoption("--ucrom-report", action="store_true",
                     help="write docs/test-report/ (REPORT.md, results.json, screenshots)")


def pytest_configure(config):
    config.addinivalue_line("markers", "vm: needs the booted emulator phone")
    global SHOTS
    if config.getoption("--ucrom-report"):
        # built in a staging folder and moved into docs/ only at the end, so
        # the repository never holds a half-written report
        SHOTS = STAGING / "screenshots"
        if STAGING.exists():
            shutil.rmtree(STAGING)
        if SHOTS.exists():
            shutil.rmtree(SHOTS)
        SHOTS.mkdir(parents=True, exist_ok=True)


class Evidence:
    def __init__(self, nodeid: str):
        self.rec = _records.setdefault(nodeid, {"shots": [], "notes": []})
        self.slug = nodeid.split("::")[-1].replace("[", "_").replace("]", "").replace("/", "_")

    def shot_path(self, label: str) -> Path:
        n = len(self.rec["shots"]) + 1
        SHOTS.mkdir(parents=True, exist_ok=True)
        return SHOTS / f"{self.slug}-{n:02d}-{label}.png"

    def screenshot(self, vm: PhoneVM, label: str) -> Path:
        p = vm.screenshot(self.shot_path(label))
        self.rec["shots"].append({"file": str(p.relative_to(SHOTS.parent)), "label": label})
        return p

    def note(self, text: str):
        self.rec["notes"].append(str(text))


@pytest.fixture
def evidence(request):
    return Evidence(request.node.nodeid)


@pytest.fixture(scope="session")
def phone():
    if os.environ.get("UCROM_SKIP_VM"):
        pytest.skip("UCROM_SKIP_VM set")
    try:
        vm = PhoneVM(net=bool(os.environ.get("UCROM_VM_NET", "1") == "1"))
    except VMError as e:
        pytest.skip(str(e))
    vm.start()
    try:
        vm.boot_seconds = vm.wait_for_agent(timeout=float(os.environ.get("UCROM_BOOT_TIMEOUT", "1500")))
        # The guest agent answers before boot has finished. Wait for systemd
        # and for udev to have applied every rule (the touch-only policy is a
        # udev rule), so no test sees a half-booted phone.
        vm.sh("timeout 900 systemctl is-system-running --wait; udevadm settle --timeout=300", timeout=1300)
        yield vm
    finally:
        vm.stop()
        _records.setdefault("_vm", {})["serial_log_tail"] = (
            (vm.dir / "serial.log").read_text(errors="replace")[-4000:]
            if (vm.dir / "serial.log").exists() else "")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    rec = _records.setdefault(item.nodeid, {"shots": [], "notes": []})
    doc = (item.function.__doc__ or "").strip().splitlines()
    rec["title"] = doc[0] if doc else item.name
    if rep.when == "call" or (rep.when == "setup" and rep.outcome != "passed"):
        rec["outcome"] = rep.outcome
        rec["duration"] = round(rep.duration, 1)
        if rep.outcome == "failed":
            rec["error"] = str(rep.longrepr)[-2500:]
        if rep.outcome == "skipped":
            rec["error"] = str(rep.longrepr[-1]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr)


def _versions():
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip().splitlines()[0]
        except (OSError, IndexError):
            return "?"
    v = {"host": platform.platform(), "qemu": run(["qemu-system-aarch64", "--version"]),
         "tesseract": run(["tesseract", "--version"]), "python": platform.python_version()}
    sums = OUT / "qemu" / "SHA256SUMS"
    if sums.exists():
        v["emulator_image"] = sums.read_text().strip().splitlines()
    for bi in sorted(OUT.glob("devices/*/*/BUILD_INFO")):
        v[f"device:{bi.parent.parent.name}/{bi.parent.name}"] = bi.read_text().strip().splitlines()
    return v


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("--ucrom-report"):
        return
    STAGING.mkdir(parents=True, exist_ok=True)
    tests = {k: v for k, v in _records.items() if not k.startswith("_") and "outcome" in v}
    data = {"generated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "versions": _versions(), "tests": tests,
            "vm": _records.get("_vm", {})}
    (STAGING / "results.json").write_text(json.dumps(data, indent=1))
    from report import write_markdown
    write_markdown(data, STAGING / "REPORT.md")
    if REPORT_DIR.exists():
        shutil.rmtree(REPORT_DIR)
    shutil.copytree(STAGING, REPORT_DIR)
