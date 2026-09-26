"""ucrom test VM: an emulated arm64 phone driven only by touch.

Boots the ucrom QEMU image (same rootfs as the phone images) with:
  * a phone-shaped virtio-gpu screen (7T Pro aspect ratio, scaled down),
  * a virtio multitouch screen (the only input the OS should accept),
  * a GPIO power button (the phone's own button, allowed),
  * "attack" devices: virtio keyboard + mouse, and hot-pluggable USB
    keyboard + mouse, which ucrom must ignore.

Control:
  * QMP (host -> VM hardware): touch gestures, key/mouse injection,
    screenshots, device hotplug.
  * qemu-guest-agent (host -> guest OS): read state for assertions only.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "qemu"

# 1440x3120 (OnePlus 7T Pro) scaled by 3/8 -> 540x1170, same aspect ratio
SCREEN_W = int(os.environ.get("UCROM_VM_W", "540"))
SCREEN_H = int(os.environ.get("UCROM_VM_H", "1170"))
ABS_MAX = 0x7FFF  # QEMU absolute axis range

USER = "ucrom"
UID = 1000


class VMError(RuntimeError):
    pass


class _JsonSocket:
    """Line-delimited JSON over a UNIX socket (QMP and QGA both use this)."""

    def __init__(self, path: Path, timeout: float = 60):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(str(path))
        self.buf = b""

    def send(self, obj: dict) -> None:
        self.sock.sendall(json.dumps(obj).encode() + b"\n")

    def recv(self) -> dict:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise VMError("socket closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()


class QMP:
    def __init__(self, path: Path):
        self.s = _JsonSocket(path)
        self.events: list[dict] = []
        greeting = self.s.recv()
        if "QMP" not in greeting:
            raise VMError(f"bad QMP greeting: {greeting}")
        self.cmd("qmp_capabilities")

    def cmd(self, name: str, **args):
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        self.s.send(msg)
        while True:
            r = self.s.recv()
            if "event" in r:
                self.events.append(r)
                continue
            if "error" in r:
                raise VMError(f"QMP {name}: {r['error']}")
            return r.get("return")


class GuestAgent:
    def __init__(self, path: Path):
        self.path = path
        self.s: _JsonSocket | None = None

    def _connect(self) -> _JsonSocket:
        if self.s is None:
            self.s = _JsonSocket(self.path, timeout=30)
            # sync so stale replies from a previous connection are discarded
            token = int(time.time() * 1000) % 2**31
            self.s.send({"execute": "guest-sync", "arguments": {"id": token}})
            while self.s.recv().get("return") != token:
                pass
        return self.s

    def cmd(self, name: str, **args):
        s = self._connect()
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        s.send(msg)
        r = s.recv()
        if "error" in r:
            raise VMError(f"QGA {name}: {r['error']}")
        return r.get("return")

    def ping(self) -> bool:
        try:
            self.cmd("guest-ping")
            return True
        except (OSError, VMError, json.JSONDecodeError):
            self.close()
            return False

    def close(self) -> None:
        if self.s:
            self.s.close()
            self.s = None


@dataclass
class Result:
    rc: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.rc == 0


class PhoneVM:
    def __init__(self, workdir: Path | None = None, net: bool = False, memory: str = "4G"):
        self.kernel = OUT / "vmlinuz"
        self.initrd = OUT / "initrd.img"
        self.image = OUT / "ucrom-qemu.qcow2"
        for f in (self.kernel, self.initrd, self.image):
            if not f.exists():
                raise VMError(f"missing {f}; run `make qemu-image` first")
        self.dir = Path(workdir or tempfile.mkdtemp(prefix="ucrom-vm-"))
        self.dir.mkdir(parents=True, exist_ok=True)
        self.net = net
        self.memory = memory
        self.proc: subprocess.Popen | None = None
        self.qmp: QMP | None = None
        self.qga = GuestAgent(self.dir / "qga.sock")
        self.tracking_id = 1
        self.usb_devices: list[str] = []
        self.shots = 0

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        overlay = self.dir / "overlay.qcow2"
        subprocess.run(
            ["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2",
             "-b", str(self.image), str(overlay)],
            check=True,
        )
        cmdline = (
            "root=/dev/vda rw rootwait console=ttyAMA0 quiet loglevel=3 "
            "systemd.show_status=0 ucrom.vm=1"
        )
        args = [
            "qemu-system-aarch64",
            "-M", "virt,gic-version=3",
            "-cpu", "max,pauth-impdef=on",
            "-accel", "tcg,thread=multi,tb-size=512",
            "-smp", str(min(4, os.cpu_count() or 1)),
            "-m", self.memory,
            "-kernel", str(self.kernel),
            "-initrd", str(self.initrd),
            "-append", cmdline,
            "-drive", f"if=none,id=root,file={overlay},format=qcow2,cache=unsafe,discard=unmap",
            "-device", "virtio-blk-pci,drive=root",
            "-device", f"virtio-gpu-pci,xres={SCREEN_W},yres={SCREEN_H}",
            "-display", "none",
            # the phone's touchscreen
            "-device", "virtio-multitouch-pci,id=touch",
            # attack devices: ucrom must ignore these
            "-device", "virtio-keyboard-pci,id=vkbd",
            "-device", "virtio-mouse-pci,id=vmouse",
            "-device", "qemu-xhci,id=xhci",
            # guest agent (read-only assertions)
            "-chardev", f"socket,id=qga,path={self.dir / 'qga.sock'},server=on,wait=off",
            "-device", "virtio-serial-pci",
            "-device", "virtserialport,chardev=qga,name=org.qemu.guest_agent.0",
            "-qmp", f"unix:{self.dir / 'qmp.sock'},server=on,wait=off",
            "-serial", f"file:{self.dir / 'serial.log'}",
            "-monitor", "none",
            "-device", "virtio-rng-pci",
        ]
        if self.net:
            args += ["-netdev", "user,id=net0", "-device", "virtio-net-pci,netdev=net0"]
        else:
            args += ["-nic", "none"]
        self.proc = subprocess.Popen(
            args, stdout=open(self.dir / "qemu.out", "w"), stderr=subprocess.STDOUT
        )
        deadline = time.time() + 30
        while not (self.dir / "qmp.sock").exists():
            if self.proc.poll() is not None or time.time() > deadline:
                raise VMError("QEMU did not start: " + (self.dir / "qemu.out").read_text())
            time.sleep(0.2)
        self.qmp = QMP(self.dir / "qmp.sock")

    def stop(self) -> None:
        self.qga.close()
        if self.proc and self.proc.poll() is None:
            with contextlib.suppress(Exception):
                self.qmp.cmd("quit")
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # ------------------------------------------------------------- guest state
    def wait_for_agent(self, timeout: float = 900) -> float:
        start = time.time()
        while time.time() - start < timeout:
            if self.proc.poll() is not None:
                raise VMError("QEMU exited during boot; see " + str(self.dir / "serial.log"))
            if self.qga.ping():
                return time.time() - start
            time.sleep(3)
        raise VMError(f"guest agent not up after {timeout}s")

    def sh(self, script: str, timeout: float = 300, user: bool = False) -> Result:
        """Run a shell snippet in the guest (as root, or in the phone user's session)."""
        if user:
            env = (
                f"XDG_RUNTIME_DIR=/run/user/{UID} "
                f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{UID}/bus "
                "WAYLAND_DISPLAY=wayland-0 "
                f"HOME=/home/{USER} "
                "PATH=/opt/node/bin:/home/ucrom/.npm-global/bin:/home/ucrom/.local/bin:/usr/local/bin:/usr/bin:/bin "
                "NPM_CONFIG_PREFIX=/home/ucrom/.npm-global "
            )
            argv = ["/usr/sbin/runuser", "-u", USER, "--", "/usr/bin/env",
                    *env.split(), "/bin/bash", "-c", script]
        else:
            argv = ["/bin/bash", "-c", script]
        pid = self.qga.cmd("guest-exec", path=argv[0], arg=argv[1:], **{"capture-output": True})["pid"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.qga.cmd("guest-exec-status", pid=pid)
            if st.get("exited"):
                dec = lambda k: base64.b64decode(st.get(k, "")).decode(errors="replace")
                return Result(st.get("exitcode", -1), dec("out-data"), dec("err-data"))
            time.sleep(0.5)
        raise VMError(f"guest command timed out: {script}")

    def push_file(self, local: Path, remote: str, mode: str = "644") -> None:
        """Copy a host file into the guest (test setup only)."""
        data = Path(local).read_bytes()
        h = self.qga.cmd("guest-file-open", path=remote, mode="wb")
        for i in range(0, len(data), 48000):
            self.qga.cmd("guest-file-write", handle=h,
                         **{"buf-b64": base64.b64encode(data[i:i + 48000]).decode()})
        self.qga.cmd("guest-file-close", handle=h)
        self.sh(f"chmod {mode} {remote}")

    def wait_until(self, script: str, timeout: float = 300, interval: float = 3, user: bool = False) -> Result:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.sh(script, user=user)
            if last.ok:
                return last
            time.sleep(interval)
        raise VMError(f"condition not met in {timeout}s: {script}\nlast: {last}")

    # -------------------------------------------------------------- the screen
    def screenshot(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.qmp.cmd("screendump", filename=str(path), format="png")
        # screendump is async in the UI thread; wait for a complete file
        for _ in range(50):
            if path.exists() and path.stat().st_size > 0:
                break
            time.sleep(0.1)
        time.sleep(0.2)
        return path

    def ocr(self, png: Path, psm: int = 11) -> str:
        """Read text on screen with tesseract (upscaled for small UI text)."""
        big = png.with_suffix(".ocr.png")
        subprocess.run(
            ["python3", "-c",
             "import sys;from PIL import Image;im=Image.open(sys.argv[1]).convert('L');"
             "im=im.resize((im.width*3,im.height*3));im.save(sys.argv[2])", str(png), str(big)],
            check=True,
        )
        r = subprocess.run(
            ["tesseract", str(big), "-", "--psm", str(psm)],
            capture_output=True, text=True, check=False,
        )
        big.unlink(missing_ok=True)
        return r.stdout

    def find_text(self, png: Path, pattern: str, scale: int = 3):
        """Locate text on screen (tesseract TSV). Returns (x, y) centre in
        screen pixels of the first word/phrase matching the regex, or None."""
        import csv
        import re
        big = png.with_suffix(".find.png")
        subprocess.run(
            ["python3", "-c",
             "import sys;from PIL import Image;im=Image.open(sys.argv[1]).convert('L');"
             f"im=im.resize((im.width*{scale},im.height*{scale}));im.save(sys.argv[2])", str(png), str(big)],
            check=True,
        )
        r = subprocess.run(["tesseract", str(big), "-", "--psm", "11", "tsv"],
                           capture_output=True, text=True, check=False)
        big.unlink(missing_ok=True)
        rows = list(csv.DictReader(r.stdout.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE))
        words = [w for w in rows if w.get("text", "").strip() and float(w.get("conf", -1)) > 30]
        rx = re.compile(pattern, re.I)
        # single words first, then adjacent pairs on the same line
        for w in words:
            if rx.fullmatch(w["text"].strip()):
                return self._centre(w, scale)
        for a, b in zip(words, words[1:]):
            if a["line_num"] == b["line_num"] and a["block_num"] == b["block_num"]:
                if rx.fullmatch(f"{a['text'].strip()} {b['text'].strip()}"):
                    x1 = int(a["left"]); y1 = int(a["top"])
                    x2 = int(b["left"]) + int(b["width"]); y2 = int(b["top"]) + int(b["height"])
                    return ((x1 + x2) / 2 / scale, (y1 + y2) / 2 / scale)
        return None

    @staticmethod
    def _centre(w, scale):
        return ((int(w["left"]) + int(w["width"]) / 2) / scale,
                (int(w["top"]) + int(w["height"]) / 2) / scale)

    def tap_text(self, pattern: str, shot: Path, timeout: float = 60, hold: float = 0.08):
        """Wait until `pattern` is visible, then tap it. Returns its position."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.screenshot(shot)
            pos = self.find_text(shot, pattern)
            if pos:
                self.tap(*pos, hold=hold)
                return pos
            time.sleep(2)
        raise VMError(f"text /{pattern}/ never appeared on screen (last: {shot})")

    def wait_text(self, pattern: str, shot: Path, timeout: float = 120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.screenshot(shot)
            pos = self.find_text(shot, pattern)
            if pos:
                return pos
            time.sleep(2)
        raise VMError(f"text /{pattern}/ never appeared on screen (last: {shot})")

    # --------------------------------------------------------------- touch input
    @staticmethod
    def _abs(v: float, size: int) -> int:
        return max(0, min(ABS_MAX, round(v * ABS_MAX / (size - 1))))

    def _mtt(self, kind: str, slot: int, tid: int, axis: str = "x", value: int = 0) -> dict:
        return {"type": "mtt", "data": {"type": kind, "slot": slot, "tracking-id": tid,
                                        "axis": axis, "value": value}}

    def _pos(self, slot: int, tid: int, x: float, y: float) -> list[dict]:
        return [
            self._mtt("update", slot, tid),
            self._mtt("data", slot, tid, "x", self._abs(x, SCREEN_W)),
            self._mtt("data", slot, tid, "y", self._abs(y, SCREEN_H)),
        ]

    def _send(self, events: list[dict]) -> None:
        self.qmp.cmd("input-send-event", events=events)

    def touch_down(self, points: list[tuple[float, float]]) -> list[int]:
        tids = []
        events = []
        for slot, (x, y) in enumerate(points):
            tid = self.tracking_id
            self.tracking_id += 1
            tids.append(tid)
            events.append(self._mtt("begin", slot, tid))
            events += self._pos(slot, tid, x, y)[1:]
        events.append({"type": "btn", "data": {"button": "touch", "down": True}})
        self._send(events)
        return tids

    def touch_move(self, tids: list[int], points: list[tuple[float, float]]) -> None:
        events = []
        for slot, (tid, (x, y)) in enumerate(zip(tids, points)):
            events += self._pos(slot, tid, x, y)
        self._send(events)

    def touch_up(self, tids: list[int]) -> None:
        events = [self._mtt("end", slot, tid) for slot, tid in enumerate(tids)]
        events.append({"type": "btn", "data": {"button": "touch", "down": False}})
        self._send(events)

    def tap(self, x: float, y: float, hold: float = 0.08) -> None:
        tids = self.touch_down([(x, y)])
        time.sleep(hold)
        self.touch_up(tids)

    def long_press(self, x: float, y: float, hold: float = 1.5) -> None:
        self.tap(x, y, hold=hold)

    def swipe(self, x1, y1, x2, y2, duration: float = 0.35, steps: int = 12) -> None:
        tids = self.touch_down([(x1, y1)])
        for i in range(1, steps + 1):
            t = i / steps
            self.touch_move(tids, [(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)])
            time.sleep(duration / steps)
        self.touch_up(tids)

    def pinch(self, cx, cy, start: float, end: float, duration: float = 0.5, steps: int = 12) -> None:
        tids = self.touch_down([(cx - start, cy), (cx + start, cy)])
        for i in range(1, steps + 1):
            d = start + (end - start) * i / steps
            self.touch_move(tids, [(cx - d, cy), (cx + d, cy)])
            time.sleep(duration / steps)
        self.touch_up(tids)

    # ------------------------------------------- the phone's own power button
    def power_button(self) -> None:
        """Press the virt board's GPIO power key (the phone's side button)."""
        self.qmp.cmd("system_powerdown")

    # ------------------------------------------------- forbidden input devices
    def type_on_hardware_keyboard(self, text: str) -> None:
        events = []
        for ch in text:
            code = {" ": "spc", "\n": "ret"}.get(ch, ch.lower())
            for down in (True, False):
                events.append({"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": code}}})
        self._send(events)

    def move_mouse(self, dx: int, dy: int, click: bool = False) -> None:
        events = [
            {"type": "rel", "data": {"axis": "x", "value": dx}},
            {"type": "rel", "data": {"axis": "y", "value": dy}},
        ]
        self._send(events)
        if click:
            self._send([{"type": "btn", "data": {"button": "left", "down": True}}])
            self._send([{"type": "btn", "data": {"button": "left", "down": False}}])

    def hotplug_usb(self, driver: str) -> str:
        dev_id = f"{driver.replace('-', '')}{len(self.usb_devices)}"
        self.qmp.cmd("device_add", driver=driver, id=dev_id, bus="xhci.0")
        self.usb_devices.append(dev_id)
        return dev_id


def have_qemu() -> bool:
    return shutil.which("qemu-system-aarch64") is not None
