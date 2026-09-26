#!/usr/bin/env python3
"""Boot the emulator phone and leave it running for hands-on work.

    sudo tools/dev/boot-vm.py /tmp/ucrom-vm     # needs out/qemu/ (make qemu-image)

Writes <dir>/AGENT (seconds until the guest agent answered), then releases
the QMP and guest-agent sockets so tools/dev/vm.py can attach. Stop it with
Ctrl+C or by killing qemu-system-aarch64.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from vm import PhoneVM  # noqa: E402

d = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ucrom-vm"
Path(d).mkdir(parents=True, exist_ok=True)
vm = PhoneVM(workdir=d, net=True)
vm.start()
t = vm.wait_for_agent(timeout=1800)
Path(d, "AGENT").write_text(str(round(t)))
print(f"guest agent up after {t:.0f} s; attach with: tools/dev/vm.py {d} ...", flush=True)
vm.qga.close()
vm.qmp.s.close()
while vm.proc.poll() is None:
    time.sleep(30)
