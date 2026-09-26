#!/usr/bin/env python3
"""Talk to an emulator phone started by tools/dev/boot-vm.py.

    tools/dev/vm.py DIR sh 'command'          run as root in the guest
    tools/dev/vm.py DIR sh 'command' user     run as the phone user (ucrom)
    tools/dev/vm.py DIR shot out.png          screenshot
    tools/dev/vm.py DIR 'python code'         code with `vm` (a PhoneVM) and
                                              the test helpers importable, e.g.
      tools/dev/vm.py DIR 'import ui; ui.swipe_up_from_bottom(vm)'

Only one client can hold the sockets: not while pytest runs on that VM.
"""
import sys
import time  # noqa: F401  (handy in exec'd snippets)
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from vm import PhoneVM, QMP, GuestAgent  # noqa: E402


class Attached(PhoneVM):
    def __init__(self, d):
        self.dir = Path(d)
        self.qmp = QMP(self.dir / "qmp.sock")
        self.qga = GuestAgent(self.dir / "qga.sock")
        self.tracking_id = 1
        self.usb_devices = []
        self.proc = None
        self.w, self.h = 720, 1440


vm = Attached(sys.argv[1])
cmd = sys.argv[2]
if cmd == "sh":
    r = vm.sh(sys.argv[3], user=len(sys.argv) > 4)
    print(r.out)
    print(r.err, file=sys.stderr)
    print("rc", r.rc)
elif cmd == "shot":
    vm.screenshot(Path(sys.argv[3]))
else:
    exec(cmd)
