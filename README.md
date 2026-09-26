# ucrom

ucrom is a custom operating system for OnePlus phones. It replaces Android with real Linux (Ubuntu 24.04 underneath) but keeps the way you use an Android phone: unlock with a PIN or your fingerprint, open apps from a grid, swipe around, type on an on-screen keyboard.

It is **touch only**. Keyboards, mice and touchpads are switched off inside the Linux kernel the moment they connect, over USB or Bluetooth. Only the touchscreen and the phone's own buttons work.

**Picking this up from a clone or a zip?** Start with [docs/STATUS.md](docs/STATUS.md): what is done, what is proven, what is open, and the commands to continue.

Main target: **OnePlus 7T Pro McLaren Edition** (also the regular 7T Pro, codename `hotdog`, Snapdragon 855+). The same OS adapts to other OnePlus phones from the Snapdragon 820 up to the 888, with Snapdragon 8 Gen 1/2/3 phones as experimental profiles.

> Status, plainly: ucrom is built and tested end to end in an emulated arm64 phone, and the 7T Pro kernel and boot images are built and checked. It has **not been run on a real 7T Pro yet**. The phone's own drivers can only be proven on the phone, which is what the built-in Hardware Check app is for. See [What is proven and what is not](#what-is-proven-and-what-is-not).

## What you get

- **Phosh** touch shell: lock screen with PIN pad, app grid, swipe gestures, quick settings, notifications, on-screen keyboard.
- Phone apps: Calls, Messages (Chatty), Contacts, Web browser, Camera, Calculator, Clocks, Weather, Text Editor, Files, Terminal, Settings.
- **App Hub**: one tap installs AI agents and developer tools from their official sources: Claude Code, Codex CLI, Gemini CLI, Antigravity, VS Code, LLM (Python). Node.js 22, git, pipx and Flatpak are preinstalled.
- **Hardware Check**: a touch app that tests every part of the phone (Wi-Fi, Bluetooth, calls, speaker, mic, cameras, pop-up camera, fingerprint, sensors, NFC, GPS, battery, alert slider, buttons) and saves a report.
- OnePlus extras written for ucrom: alert slider (ring / vibrate / silent), pop-up camera motor with drop protection, in-display fingerprint unlock with sensor lighting, 60/90 Hz panel switch.

## How it works

```
ucrom (Ubuntu 24.04 arm64, systemd, Phosh, apps, touch-only policy)   same on every phone
  └─ chip profile   socs/<soc>/soc.conf        kernel source, config, boot image format
       └─ phone     devices/<phone>/device.conf screen, device tree, cmdline, features
```

Two ways to reach the hardware, picked per phone:

- **mainline**: the phone runs a mainline Linux kernel. Clean and fully open, but only as complete as upstream Linux support for that phone (very good on the OnePlus 6/6T, partial on the 7 series).
- **halium**: the phone runs its own vendor kernel, and a small hidden Android container loads the phone's original hardware drivers. Bridges (libhybris, binder) expose them to normal Linux services: GPU, audio, calls, Bluetooth, fingerprint, cameras, sensors, NFC. This is how Ubuntu Touch and Droidian get full hardware support, and it's what the 7T Pro uses so that nothing is left out.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Supported phones

Run `make list-devices` for the live list. Summary ([docs/DEVICES.md](docs/DEVICES.md) has the details):

| Snapdragon | Phones | Status |
|---|---|---|
| 855 / 855+ | **7T Pro McLaren / 7T Pro** (primary), 7 Pro, 7T, 7T Pro 5G McLaren | halium, full build for 7T Pro |
| 845 | 6, 6T | mainline, full build for 6T |
| 865 | 8 Pro, 8T | mainline, full build for 8 Pro |
| 820/821, 835, 888 | 3/3T, 5, 5T, 9, 9 Pro | profiles verified against upstream trees |
| 8 Gen 2 / 8 Gen 3 | 11, 12 | experimental |

## Build it

On an Ubuntu 24.04 x86_64 or arm64 machine, as root, with ~60 GB free:

```sh
sudo apt install qemu-system-arm qemu-user-static qemu-utils mmdebstrap mkbootimg \
    android-sdk-libsparse-utils device-tree-compiler gcc-aarch64-linux-gnu \
    gcc-arm-linux-gnueabi clang lld bc flex bison libssl-dev cpio kmod e2fsprogs \
    tesseract-ocr python3-pytest python3-pil rsync zstd
sudo make rootfs-mainline qemu-image        # the OS + the emulator image
sudo make test                             # boot it in the emulator and test it by touch
sudo make bridges rootfs-halium            # hardware bridges for the 7T Pro
sudo make device DEVICE=oneplus-hotdog     # boot.img, dtbo.img, userdata.img
```

Full guide: [docs/BUILDING.md](docs/BUILDING.md).

## Put it on a phone

Read [docs/FLASHING.md](docs/FLASHING.md) first. Short version for the 7T Pro: unlock the bootloader, install LineageOS 20 (ucrom reuses its vendor drivers), get the Halium system image (`scripts/fetch-halium-system.sh`), build, then `scripts/flash.sh oneplus-hotdog --try` to boot ucrom once from RAM without touching your boot partition. Keep the OnePlus MSM Download Tool for your model around so you can always restore stock.

## Tests and proof

`make report` boots the real image in QEMU (arm64, virtio multitouch screen, plus keyboards and mice that must be ignored) and drives it **only with touch gestures**: unlock with the PIN pad, open apps, use the calculator, type with the on-screen keyboard, install AI agents from the App Hub, lock with the power button. It also checks every built kernel, boot image, overlay image and bridge package. Results with screenshots: [docs/test-report/REPORT.md](docs/test-report/REPORT.md). How the tests work: [docs/TESTING.md](docs/TESTING.md).

## What is proven and what is not

Proven by the automated tests in this repo:
- the OS builds from source and boots on arm64;
- it is fully usable by touch alone, and keyboards and mice (virtio, USB hot-plug) are blocked in the kernel;
- AI agents and dev tools install and start by touch;
- ucrom's OnePlus helpers (alert slider, pop-up camera, fingerprint, refresh rate) behave correctly against simulated hardware;
- the 7T Pro kernel has every hardware driver enabled plus the Halium and touch-only options, and its boot.img, dtbo.img and initramfs are structurally correct;
- every chip and phone profile points at kernel branches, defconfigs and device trees that really exist.

Only provable on a real phone: that the phone's drivers respond (display, modem, cameras and so on). Run **Hardware Check** on the phone and send the report back. Two areas most likely to need on-phone tuning: carrier VoLTE and the in-display fingerprint timing.

## Documentation

[Status and hand-off](docs/STATUS.md) · [Plan](docs/PLAN.md) · [Architecture](docs/ARCHITECTURE.md) · [Building](docs/BUILDING.md) · [Flashing](docs/FLASHING.md) · [Touch only](docs/TOUCH_ONLY.md) · [Devices](docs/DEVICES.md) · [Apps and AI agents](docs/APPS.md) · [Hardware Check](docs/HARDWARE_CHECK.md) · [Testing](docs/TESTING.md)

## License

Apache 2.0 (see LICENSE) for ucrom's own code. Kernels, bridges and Ubuntu packages keep their own licenses. Proprietary firmware and vendor drivers are never stored in this repository: they are fetched at build time or reused from the phone.
