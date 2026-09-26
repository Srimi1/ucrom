# Testing

`make test` runs everything; `make report` also writes `docs/test-report/`.

## The emulated phone (`tests/vm.py`)

- `qemu-system-aarch64 -M virt`, 4 vCPUs, 4 GB, TCG emulation (no KVM needed).
- The same root filesystem as the phone images, with Ubuntu's generic arm64 kernel.
- Screen: virtio-gpu, 540x1170 (the 7T Pro's 1440x3120 shape, scaled down for speed).
- Input: a **virtio multitouch** screen, the virt board's GPIO power button, and devices ucrom must ignore: a virtio keyboard and mouse from boot, plus a USB keyboard and mouse hot-plugged during the test.
- The tests drive the phone only through QMP touch events (`input-send-event` multitouch begin/update/end): taps, long presses, swipes. They read the screen with `screendump` and tesseract OCR.
- qemu-guest-agent is used only to read state for assertions (is the lock screen active? did the process start?). It starts only when QEMU's agent port exists, so it does nothing on a phone.

## Suites

| File | What |
|---|---|
| `test_00_image_static.py` | the built root filesystem: branding, packages, Node 22, touch-only files, no consoles |
| `test_10_boot.py` | boots to Phosh as the phone user, no failed services |
| `test_20_touch_only.py` | keyboard/mouse inhibited, zero events, USB hot-plug blocked, touch delivered |
| `test_30_touch_ux.py` | unlock with the PIN pad, app grid, calculator by taps, on-screen keyboard typing, quick settings, power button lock |
| `test_40_apps.py` | App Hub installs and opens Claude Code, Codex, VS Code by touch |
| `test_50_daemons.py` | alert slider, pop-up camera, fingerprint, refresh rate, Hardware Check against simulated hardware |
| `test_60_hotdog.py` | 7T Pro kernel config, boot image, initramfs, dtbo, mainline fallback device tree |
| `test_61_device_artifacts.py` | every built phone image: checksums, boot image structure, userdata filesystem |
| `test_62_bridges.py` | every Halium bridge built for arm64 and linkable |
| `test_63_soc_matrix.py` | every phone and chip profile checks out upstream |

`UCROM_SKIP_VM=1 make test` runs only the suites that don't boot the emulator.

## Network in the emulator

App tests need the internet from inside the VM. On build machines behind a proxy the test injects the host proxy address and CA into the VM for that test only (documented in `tests/test_40_apps.py`); the image itself ships no proxy settings.
