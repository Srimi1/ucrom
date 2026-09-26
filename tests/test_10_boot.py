"""ucrom boots on the emulated arm64 phone and starts the touch shell."""

import pytest

pytestmark = pytest.mark.vm


def test_boots_to_touch_shell(phone, evidence):
    """Boots to the Phosh touch shell"""
    evidence.note(f"guest agent answered after {phone.boot_seconds:.0f} s (arm64 under TCG emulation, no KVM)")
    r = phone.wait_until("pgrep -x phosh >/dev/null && pgrep -x phoc >/dev/null", timeout=900)
    assert r.ok
    phone.wait_until("systemctl is-system-running --wait >/dev/null 2>&1; "
                     "s=$(systemctl is-system-running); [ \"$s\" = running ] || [ \"$s\" = degraded ]",
                     timeout=600)
    evidence.screenshot(phone, "first-screen")


def test_identity_in_guest(phone, evidence):
    """The running system is ucrom on an arm64 kernel"""
    r = phone.sh(". /etc/os-release; echo $PRETTY_NAME; uname -m; hostname")
    evidence.note(r.out.strip().replace("\n", " | "))
    assert r.out.splitlines() == ["ucrom 0.1", "aarch64", "ucrom"]


def test_no_failed_services(phone, evidence):
    """No system service failed"""
    r = phone.sh("systemctl --failed --plain --no-legend | awk '{print $1}'")
    failed = [u for u in r.out.split() if u]
    evidence.note("failed units: " + (", ".join(failed) or "none"))
    assert failed == []


def test_touch_session_user(phone, evidence):
    """The phone user's session runs Phosh (not root)"""
    r = phone.sh("ps -o user= -C phosh | sort -u")
    evidence.note(f"phosh runs as: {r.out.strip()}")
    assert r.out.strip() == "ucrom"
