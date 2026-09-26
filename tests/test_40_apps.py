"""AI agents and developer apps, installed and opened by touch from App Hub.

Test-only network plumbing: build sandboxes reach the internet through an
HTTPS proxy on the host. The test tells the emulated phone about it (proxy
address as seen from the VM + the proxy's CA) and restarts the session so
apps inherit it. The shipped image has no proxy settings.
"""

import os
import time
from pathlib import Path

import pytest

import ui

pytestmark = pytest.mark.vm


@pytest.fixture(scope="module")
def online(phone):
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    ca = os.environ.get("SSL_CERT_FILE")
    env = []
    if proxy:
        vm_proxy = proxy.replace("127.0.0.1", "10.0.2.2").replace("localhost", "10.0.2.2")
        env = [f"https_proxy={vm_proxy}", f"HTTPS_PROXY={vm_proxy}", f"http_proxy={vm_proxy}",
               f"npm_config_https_proxy={vm_proxy}", "NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/test-proxy.crt"]
        if ca and Path(ca).exists():
            phone.push_file(Path(ca), "/usr/local/share/ca-certificates/test-proxy.crt")
            phone.sh("update-ca-certificates >/dev/null 2>&1")
        phone.sh("printf '%s\\n' " + " ".join(f"'{e}'" for e in env) + " >> /etc/environment")
        phone.sh("systemctl restart phosh.service")
        time.sleep(20)
    r = phone.sh(". /etc/environment 2>/dev/null; export https_proxy HTTPS_PROXY; "
                 "curl -sS -o /dev/null -w '%{http_code}' https://registry.npmjs.org/", timeout=90)
    if r.out.strip() not in ("200", "301", "302"):
        pytest.skip(f"no internet from the emulator (curl -> {r.out} {r.err})")
    return env


def open_hub(phone, evidence):
    ui.open_favorite(phone, evidence, "io.ucrom.AppHub.desktop", "apphub.py", r"App Hub|Install|Claude")


def install_and_open(phone, evidence, app_label, app_id, process, timeout=1500):
    """Tap Install on the App Hub row, wait, then tap Open."""
    shot = evidence.shot_path(f"hub-{app_id}")
    phone.screenshot(shot)
    row = phone.find_text(shot, app_label)
    for _ in range(4):
        if row:
            break
        phone.swipe(phone.w / 2, 900, phone.w / 2, 400, duration=0.5)
        time.sleep(2)
        phone.screenshot(shot)
        row = phone.find_text(shot, app_label)
    assert row, f"{app_label} not listed in App Hub"
    btn = phone.find_text(shot, "Install")
    # buttons are right-aligned; tap the button column on the app's row
    x_btn = btn[0] if btn else phone.w - 60
    phone.tap(x_btn, row[1])
    evidence.screenshot(phone, f"installing-{app_id}")
    log = "/home/ucrom/.local/state/ucrom/apphub.log"
    phone.wait_until(f"grep -qE '^(INSTALLED|FAILED) {app_id}' {log}", timeout=timeout, interval=10)
    out = phone.sh(f"tail -5 {log}").out
    evidence.note(f"App Hub log: {out.strip()}")
    assert f"INSTALLED {app_id}" in out
    time.sleep(3)
    evidence.screenshot(phone, f"installed-{app_id}")
    phone.screenshot(shot)
    opened = phone.find_text(shot, "Open")
    phone.tap(opened[0] if opened else x_btn, row[1])
    phone.wait_until(f"pgrep -f '{ui._self_safe(process)}' >/dev/null", timeout=300, interval=3)
    time.sleep(15)
    evidence.screenshot(phone, f"running-{app_id}")


def test_app_hub_opens(phone, online, evidence):
    """App Hub opens from the app grid by touch"""
    if ui.is_locked(phone):
        ui.unlock(phone, evidence)
    open_hub(phone, evidence)
    evidence.screenshot(phone, "app-hub")


@pytest.mark.parametrize("label,app_id,process,version_cmd", [
    ("Claude Code", "claude-code", "claude", "claude --version"),
    ("Codex CLI", "codex", "codex", "codex --version"),
])
def test_ai_agent(phone, online, evidence, label, app_id, process, version_cmd):
    """AI coding agent installs from its official source and starts in the touch terminal"""
    if not phone.sh("pgrep -f '[a]pphub.py' >/dev/null").ok:
        open_hub(phone, evidence)
    install_and_open(phone, evidence, label, app_id, process)
    v = phone.sh(version_cmd, user=True)
    evidence.note(f"{version_cmd}: {v.out.strip() or v.err.strip()}")
    assert v.ok
    arch = phone.sh(f"file -L $(readlink -f $(runuser -u ucrom -- bash -lc 'command -v {process}')) || true").out
    evidence.note(arch.strip()[:200])
    phone.sh("pkill -x kgx; true")
    time.sleep(3)


def test_vscode(phone, online, evidence):
    """VS Code (same Electron/VS Code base as Antigravity) installs and runs, scaled to the phone"""
    if not phone.sh("pgrep -f '[a]pphub.py' >/dev/null").ok:
        open_hub(phone, evidence)
    install_and_open(phone, evidence, "Visual Studio Code", "vscode", "vscode/usr/share/code/code", timeout=1800)
    v = phone.sh("cat ~/.local/share/ucrom-apps/vscode/VERSION; "
                 "file ~/.local/share/ucrom-apps/vscode/usr/share/code/code", user=True)
    evidence.note(v.out.strip())
    assert "aarch64" in v.out
    phone.sh("pkill -f '[v]scode/usr/share/code'; true")


def test_python_ai_tool_via_pipx(phone, online, evidence):
    """A Python AI tool (llm) installs with pipx"""
    r = phone.sh("bash /usr/lib/ucrom/apps/installers/llm.sh 2>&1 | tail -3", user=True, timeout=900)
    evidence.note(r.out.strip())
    assert phone.sh("~/.local/bin/llm --version", user=True).ok
