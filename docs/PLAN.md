# ucrom: touch-only Linux phone OS for OnePlus devices

## Context

The repo (`srimi1/ucrom`) is empty (README, LICENSE, an Android .gitignore). The user wants their own Linux-based "ROM" for OnePlus phones that behaves like Android: everything is done by touch, and keyboards and mice must be impossible to use, not just discouraged. They have no phone to test on, so all proof must come from an environment built here.

Decisions made with the user:
- **Name:** ucrom.
- **Main phone:** OnePlus 7T Pro McLaren Edition (oneplus.in/7t-pro-mclaren, India model HD1911, codename `hotdog`, Snapdragon 855+, 1440x3120 90 Hz AMOLED, 12 GB RAM, 256 GB UFS 3.0, in-display fingerprint, pop-up camera, alert slider, NFC).
- **Must be fully functional** on that phone with nothing compromised: WiFi, Bluetooth, fingerprint, calls, audio, cameras, GPU, sensors and so on.
- **Adaptable across Snapdragon generations:** older (820 to 855+) and newer (865, 888, 8 Gen x).
- **Touch shell:** Phosh (GNOME phone shell: PIN pad lock screen, app grid, swipe gestures, on-screen keyboard).
- **Must run Linux apps**, including AI agents and dev tools (Claude Code, Codex, Antigravity, and others).

### Why the 7T Pro uses a hardware bridge (this replaces the earlier "mainline only" answer)

I checked the mainline Linux kernel for this phone (`sm8150-mainline`, branch `sm8150/6.14`). Today it drives touch, a basic framebuffer, WiFi, USB and the modem. **GPU, audio, cameras, fingerprint, sensors and panel power are disabled upstream.** Writing those drivers from scratch is years of reverse engineering, so mainline alone can't meet the "fully functional" requirement.

The proven way to get full hardware under a real Linux userspace is how Droidian and Ubuntu Touch do it. ucrom keeps Linux, systemd and Phosh as the OS. Underneath, it boots the phone's own vendor kernel, and a tiny sandboxed Android container (Halium) loads the phone's original hardware drivers. Bridge daemons (libhybris, binder) then expose each device to normal Linux services. Everything the user touches is Linux; Android is only a driver host.

All the source for this is reachable from this session (checked with `git ls-remote`):
- Kernel: `LineageOS/android_kernel_oneplus_sm8150` (`lineage-20` = Android 13; it covers 7, 7 Pro, 7T and 7T Pro), plus `android_device_oneplus_hotdog` and `android_device_oneplus_sm8150-common`.
- Boot image tooling: `gitlab.com/ubports/porting/community-ports/halium-generic-adaptation-build-tools`.
- Bridges (GitHub, `droidian/*` and `mer-hybris/*`): `libhybris`, `wlroots` + `phoc` (GPU hwcomposer backend), `pulseaudio-modules-droid`, `ofono`, `ofono-binder-plugin`, `ofono2mm`, `libgbinder`, `bluebinder`, `droidian-fpd`, `droidmedia`, `gst-droid`, `droidian-camera`, `feedbackd`, `flashlightd`, `batman` (battery saver), `halium-wrappers`, `nfcd-binder-plugin`.

The earlier mainline design is kept as a **second flavor** for chips where mainline is strong (845, 865), and as a fallback for the 7T Pro.

### Environment limits (checked)

Reachable: Ubuntu 24.04 archive and `ports.ubuntu.com` arm64, gitlab.com, GitHub over git, npm, nodejs.org, packages.microsoft.com. Blocked: postmarketOS/Alpine/Debian mirrors, Droidian/UBports package repos, GitHub release downloads, the Antigravity download site. No KVM (arm64 VM runs under TCG, slow but works). 4 cores, 15 GB RAM, ~30 GB disk. **The Halium Android system image (GSI) can't be built here** (it needs a full Android source tree, 200+ GB). The build script fetches or builds it on the user's machine.

## What "100% ready with proof" can honestly mean

- **Proven here, by tests:** the OS builds from source; it boots; it's fully usable by touch alone; keyboards and mice are blocked at the kernel level; AI and dev apps install and run by touch; every bridge component compiles for arm64; the 7T Pro kernel and boot image build and have the correct structure; ucrom's own hardware daemons pass tests against simulated hardware.
- **Only provable on the phone:** that the phone's real drivers respond. For that, ucrom ships **ucrom Hardware Check**, a touch app that tests every component on the phone and writes a pass/fail report. The user can send that back to finish the job.

## Name and branding

**ucrom** everywhere: `/etc/os-release` (`NAME="ucrom"`, `ID=ucrom`, `ID_LIKE=ubuntu`, `PRETTY_NAME="ucrom 0.1"`), `/etc/issue`, hostname, default user `ucrom`, image names (`ucrom-<device>-boot.img`, `ucrom-<device>-rootfs.img`, `ucrom-qemu.qcow2`), the Settings About page and all docs. Tests assert it.

## Architecture

```
┌──────────────────── ucrom (Ubuntu 24.04 arm64, systemd) ────────────────────┐
│ Phosh + apps + App Hub + Hardware Check + touch-only policy     (all devices)│
├─────────── hardware flavor, picked per device ───────────────────────────────┤
│ mainline flavor:  mainline kernel + DTB + linux-firmware        (845, 865 …) │
│ halium flavor:    vendor kernel + Halium container + bridges    (7T Pro …)   │
│   GPU      phoc/wlroots hwcomposer backend → libhybris → Adreno driver       │
│   Audio    PulseAudio + pulseaudio-modules-droid → audio HAL                 │
│   Calls/SMS/data  ofono + binder plugin → ofono2mm → ModemManager API        │
│   Bluetooth       bluebinder → BlueZ (audio, file transfer; HID blocked)     │
│   Fingerprint     droidian-fpd → fprintd-style D-Bus → Phosh unlock          │
│   Camera   droidmedia + gst-droid → droidian-camera app                      │
│   Sensors  hybris sensor backend → iio-sensor-proxy (rotation, proximity…)   │
│   WiFi     vendor kernel qcacld driver → NetworkManager (native Linux)       │
│   Battery/charging  kernel power_supply → UPower (native Linux)              │
│   Vibration, flashlight, NFC, GPS  feedbackd / flashlightd / nfcd / geoclue  │
│   ucrom-made: alert slider daemon, pop-up camera motor daemon, FOD helper    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Layers so one OS adapts to many Snapdragon chips

```
common rootfs                        same for every phone
  └─ socs/<soc>/soc.conf             flavor(s), kernel source+ref, config fragments, boot.img defaults
       └─ devices/<codename>/device.conf   flavor, DTB or vendor kernel defconfig, screen, cmdline, firmware, quirks
```

Adding a phone is one `device.conf`. Adding a chip is one `soc.conf`. `make DEVICE=<codename>` resolves everything. `docs/DEVICES.md` is generated from these files.

| Snapdragon | SoC | Mainline flavor | Halium flavor (LineageOS kernel) | OnePlus devices | Built and tested this session |
|---|---|---|---|---|---|
| 820/821 | msm8996 | pmOS qcom-msm8996 | `android_kernel_oneplus_msm8996` | 3, 3T | config + DTB/defconfig check |
| 835 | msm8998 | msm8998-mainline | `android_kernel_oneplus_msm8998` (UBports port exists) | 5, 5T | config check |
| 845 | sdm845 | sdm845-mainline (very good) | `android_kernel_oneplus_sdm845` | 6, 6T | **mainline full build** |
| 855/855+ | sm8150 | sm8150-mainline 6.14 (partial) | `android_kernel_oneplus_sm8150` | **7T Pro McLaren (hotdog)**, 7 Pro, 7T | **halium full build (primary)** + mainline fallback build |
| 865 | sm8250 | sm8250-mainline 6.11 | `android_kernel_oneplus_sm8250` | 8, 8 Pro, 8T | **mainline full build** |
| 888 | sm8350 | sm8350-mainline | `android_kernel_oneplus_sm8350` | 9, 9 Pro | config check |
| 8 Gen 1/2/3 | sm8450/8550/8650 | upstream SoC only | GKI-based halium (`ubports halium-gki` exists) | 10 Pro, 11, 12 | experimental profile only |

Out of scope, stated: Snapdragon 800/801 (OnePlus One, X) are 32-bit, and 810 (OnePlus 2) has too little support.

## OnePlus 7T Pro McLaren (`hotdog`) in detail

**Starting state the user must reach first (documented step by step in `docs/FLASHING.md`):** unlock bootloader, flash official **LineageOS 20** (Android 13) for hotdog. This puts matching Android 13 vendor drivers and firmware on the `vendor`, `odm` and `modem` partitions. ucrom reuses them read-only and never ships them. Keep the OnePlus **MSM Download Tool** package for hotdog at hand. It restores the phone from EDL mode even after a bad flash, so the phone can't be hard-bricked by a bad ucrom flash. The first ucrom boot uses `fastboot boot` (RAM only, nothing written).

**Kernel:** `LineageOS/android_kernel_oneplus_sm8150` `lineage-20`, `vendor/sm8150-perf_defconfig`, plus:
- `socs/sm8150/halium.config`: the Halium-required options (SYSVIPC, namespaces, cgroups, `ANDROID_BINDERFS`, `DEVTMPFS`, `FHANDLE`, `AUTOFS`, `VT=n`, etc.), validated with the Halium `check-kernel-config` script from the build tools.
- `socs/common/kernel-touch-only.config`: HID off (`USB_HID`, `BT_HIDP`, `UHID`), `MAGIC_SYSRQ=n`.
- Built with Ubuntu's cross toolchain (`clang` + `aarch64-linux-gnu` binutils as LineageOS expects). Out-of-tree `qcacld-3.0` WiFi and other vendor modules are built if the branch has them in-tree; otherwise the phone's own `vendor_dlkm` modules are loaded as-is.

**Boot:** `halium-generic-adaptation-build-tools` style `boot.img` (header v2 as the 7T Pro bootloader expects, DTB/DTBO from the kernel build), with a small ucrom initramfs that finds the rootfs on `userdata`, mounts `vendor`/`odm` read-only, and starts systemd. ucrom rootfs is a file `ucrom-rootfs.img` on `userdata` (the Droidian approach), so the Android partitions stay untouched.

**Android side (Halium 13 system image):** `scripts/fetch-halium-system.sh` downloads the official prebuilt Halium 13 arm64 system image from UBports/Droidian (hosts blocked here, so it runs on the user's machine; the checksum is recorded on first fetch). `scripts/build-halium-system.sh` is the alternative for a machine with 250 GB free: it syncs LineageOS 20 + Halium patches and builds it. The container runs with the `lxc` package from Ubuntu and `halium-wrappers`.

**Bridges:** each listed repo is packaged as a Debian package for Ubuntu noble arm64 under `packages/<name>/` (pinned commit + ucrom packaging tweaks), built with `sbuild`/`dpkg-buildpackage` in an arm64 chroot, and installed only in halium-flavor images. The mainline flavor keeps upstream Ubuntu `phoc`, PipeWire and so on.

**Things ucrom builds itself for this phone ("our own way"):**
- `ucrom-alertslider`: reads the 3-position alert slider (`tri-state-key` from the vendor kernel) and switches Phosh between ring, vibrate and silent.
- `ucrom-popup-camera`: raises and lowers the pop-up camera motor through the vendor kernel's motor driver (sysfs) whenever the front camera opens or closes. It also retracts the camera on a drop (accelerometer free-fall), like OxygenOS does.
- `ucrom-fod`: in-display fingerprint helper. It shows the touch target on the lock screen, sets panel high-brightness mode during a scan, and talks to `droidian-fpd`.
- `ucrom-90hz`: sets the panel refresh rate via hwcomposer (60/90 Hz toggle in Settings).
- **ucrom Hardware Check:** a touch app that tests display, multi-touch (draw test), GPU, WiFi scan/connect, Bluetooth scan/pair, speaker, earpiece and mic loopback, a test call, SMS, mobile data, GPS fix, all cameras and the pop-up motor, fingerprint enrol and verify, rotation, proximity, light sensor, vibration, flashlight, NFC read, charging, alert slider and buttons. It saves an HTML report on the phone.

**Features on the 7T Pro with the halium flavor:** GPU acceleration at 90 Hz, touch, brightness and screen off, WiFi, Bluetooth (headphones, speakers, file transfer), calls, SMS and mobile data (VoLTE depends on carrier and vendor HAL, flagged as a known risk), speaker/earpiece/mic/headset, front pop-up and rear cameras (photo; video depends on the gst-droid encoder), in-display fingerprint unlock, rotation, proximity (screen off during calls), light sensor, vibration, flashlight, NFC, GPS, battery and fast charging, alert slider, power and volume buttons. Each one is listed in `docs/DEVICES.md` as "built, verified on hardware: pending" until a Hardware Check report from the real phone marks it verified.

## Touch-only enforcement (core requirement, both flavors)

1. **Kernel input inhibit (udev):** `90-ucrom-touch-only.rules` sets `ATTR{inhibited}="1"` and `LIBINPUT_IGNORE_DEVICE=1` on every input device tagged keyboard, mouse, touchpad, pointing stick, trackball, joystick or tablet (unless it is a touchscreen). Inhibited devices deliver zero events to anyone. Allowed: touchscreens and the phone's own buttons (power, volume, alert slider), which are `ID_INPUT_KEY` but not `ID_INPUT_KEYBOARD`.
2. **No HID drivers:** kernel config has USB/BT HID off, and `modprobe.d` hard-blocks `usbhid`, `hid_generic`, `hidp`, `uhid`. BlueZ `input` and `hog` plugins are disabled, so Bluetooth keyboards and mice can't even pair as input.
3. **No text console:** gettys masked, `NAutoVTs=0`, `kernel.sysrq=0`, `CONFIG_VT=n`, no SSH server, no serial console on the phone.
4. **Touch replacements:** `phosh-osk-stub` on-screen keyboard always on (with a terminal layout that has Ctrl, Esc, Tab and arrows), PIN pad plus fingerprint unlock, autologin to the phone user.

`docs/TOUCH_ONLY.md` states the limit: an unlocked bootloader can still be reflashed over USB with fastboot. That is a flashing path, not an input path. Relocking with a custom AVB key is documented as a later step.

## Rootfs and apps

Packages (Ubuntu noble): `ubuntu-minimal`, `systemd`, `network-manager`, `modemmanager`, `bluez`, `phosh`, `phosh-osk-stub`, `phosh-mobile-settings`, `feedbackd`, `iio-sensor-proxy`, `gnome-calls`, `chatty`, `gnome-contacts`, `epiphany-browser`, `gnome-calculator`, `gnome-clocks`, `gnome-text-editor`, a file manager, `gnome-console`, `flatpak`, `git`, `python3`, `pipx`, `libinput-tools`, `qemu-guest-agent` (only starts when a QEMU port exists, so it does nothing on the phone). Mainline flavor adds `phoc` and PipeWire; halium flavor adds the bridge packages.

**Linux apps and AI agents** (ARM64 builds checked):

| App | Source | Tested here |
|---|---|---|
| Claude Code | official installer / npm (`claude-code-linux-arm64`), Node 22 from nodejs.org | yes |
| Codex CLI | npm (`codex-linux-arm64`) | yes |
| Antigravity | Google's official Linux download, fetched on the phone | host blocked here, so VS Code ARM64 (same VS Code/Electron base) is tested in its place, stated clearly |
| VS Code, Electron apps | Microsoft apt repo | yes |
| Python AI tools | `pipx` | yes, one example |
| Flathub apps | `flatpak` with the Flathub remote | config only (blocked here) |

**ucrom App Hub** (Python + GTK4/libadwaita): big tiles, one tap installs from the official source and adds a launcher. Proprietary apps aren't baked in (licensing); `UCROM_PREINSTALL_AI=1` preinstalls them for personal builds. Agent launchers open straight into a terminal in the home project folder. Desktop-sized apps get Phosh scale-to-fit. x86-only apps are unsupported (no box64 available), listed in `docs/APPS.md`.

## Repo layout (all new)

```
README.md, Makefile, config/ucrom.conf, config/packages/*.list
socs/<soc>/{soc.conf,halium.config}, socs/common/kernel-touch-only.config
devices/<codename>/device.conf (+ dts/ patches for mainline, + quirks/ for halium)
packages/<bridge>/             pinned source refs + Debian packaging for the halium bridges
ucrom/{alertslider,popup-camera,fod,refresh-rate}/   ucrom's own hardware daemons (Python, systemd units)
apps/{apphub,hwcheck}/, apps/catalog.yaml, apps/installers/*.sh
rootfs/overlay/, rootfs/hooks/*.chroot
scripts/{lib,resolve-device,build-rootfs,build-kernel,build-bootimg,build-rootfs-img,build-qemu-image,build-bridges,fetch-halium-system,build-halium-system,flash}.sh
tests/  (pytest harness, below)
docs/{ARCHITECTURE,BUILDING,FLASHING,TOUCH_ONLY,DEVICES,APPS,HARDWARE_CHECK,TESTING}.md, docs/test-report/
.github/workflows/build-test.yml
```

`.gitignore` gets `out/`, `build/`, `*.img`, `*.qcow2`.

## Build flow

1. `build-rootfs.sh`: `mmdebstrap --arch=arm64` from `ports.ubuntu.com`, overlay, chroot hooks. For arm64 execution, try binfmt + `qemu-user-static` first; if the container blocks binfmt, run the chroot stage inside a TCG QEMU VM instead.
2. `build-bridges.sh`: build each `packages/<bridge>` as arm64 .debs in the chroot (dependency order: libglibutil → libgbinder → libhybris → wlroots → phoc → the rest).
3. `build-kernel.sh DEVICE=…`: mainline (DTB) or LineageOS (defconfig + fragments), cross-compiled, modules into the rootfs.
4. `build-bootimg.sh`, `build-rootfs-img.sh`: `boot.img` and the rootfs image (a sparse `userdata` image for mainline, `ucrom-rootfs.img` for halium).
5. `build-qemu-image.sh`: the same rootfs with Ubuntu's generic arm64 kernel for the emulator.

Proprietary firmware and vendor blobs are never committed. Mainline firmware is fetched at build time; halium reuses what LineageOS put on the phone.

## Test environment and tests (pytest)

`tests/vm.py` boots the same rootfs in `qemu-system-aarch64 -M virt` with a phone-shaped `virtio-gpu` screen (proportioned like the 7T Pro, scaled for speed), **`virtio-multitouch-pci`** (a real multitouch device), and attack devices: virtio keyboard/mouse plus hot-plugged USB keyboard/mouse. QMP drives touches (`input-send-event` multitouch) and screenshots; qemu-guest-agent does guest checks; `tesseract` OCR reads the screen. Every test starts from a clean qcow2 overlay.

- `test_image_static.py`: packages, overlay, udev rules (`udevadm verify`), masks, modprobe blocks, BlueZ plugins off, sysctl, no sshd, ucrom branding.
- `test_boot.py`: reaches `graphical.target`, Phosh running, no failed units (small allowlist for hardware-absent services), boot time.
- `test_touch_only.py`: only the touchscreen is visible to libinput; keyboard/mouse devices are `inhibited=1`; injected keys and mouse moves (virtio and hot-plugged USB) produce zero events and no screen change; `usbhid` never loads; SysRq off; no VT login.
- `test_touch_ux.py`: swipe to unlock, PIN pad; tap Calculator, `7 × 6 =`, OCR reads 42; type text with on-screen keyboard taps; quick settings swipe; long-press; close an app; lock with the power button.
- `test_apps.py`: by touch, App Hub installs and launches Claude Code, Codex (version/help screen only, no accounts) and VS Code ARM64; one pipx tool; a terminal command typed with on-screen keys.
- `test_ucrom_daemons.py`: alert slider, pop-up camera, FOD and refresh-rate daemons run against **simulated hardware** (uinput tri-state switch, fake sysfs motor, fake D-Bus fingerprint service) and must react correctly. Hardware Check runs in the VM and correctly reports "not present" for each missing component (it doesn't fake passes).
- `test_bridges.py`: every bridge .deb built for arm64, installs cleanly in the halium-flavor rootfs, and its binaries and libraries load (`ldd` / `--help` under qemu-user). Services stay idle without `/android` instead of crash-looping.
- `test_hotdog.py`: LineageOS kernel `.config` passes Halium `check-kernel-config`, has the touch-only options, and has the 7T Pro drivers on (touch, panel, qcacld, audio, camera, fingerprint, motor, tri-state key). `boot.img` unpacks with the right header version, cmdline, kernel and DTB/DTBO for hotdog. The initramfs contains the halium mount logic. Also builds and checks the mainline fallback: a new `sm8150-oneplus-hotdog.dts` derived from the 7 Pro, cross-checked against the LineageOS device tree.
- `test_soc_matrix.py`: every `device.conf` resolves; boot images assemble for all full-build devices; the fragments apply cleanly to every listed kernel.
- `tests/report.py`: `docs/test-report/REPORT.md` + HTML with screenshots, pass/fail, timings, versions and image SHA-256s.

## Verification (what "done" means)

1. From a clean checkout: `make rootfs bridges qemu-image`, `make device DEVICE=oneplus-hotdog` (halium + mainline fallback), `make device DEVICE=oneplus-fajita` and `DEVICE=oneplus-instantnoodlep` (mainline), and `make validate-socs` all succeed.
2. `make test` passes every suite on the real built images. Failures get fixed, never skipped.
3. The test report with screenshots is committed and published as an Artifact page.
4. Commit to `claude/custom-linux-rom-oneplus-chbmxa`, push, open a draft PR and watch it. Large binaries aren't committed; the report lists their hashes.

## Risks and fallbacks

- The Halium system image can't be fetched or built here, so the full 7T Pro stack can't boot in this session. This is covered by the build and structure tests plus Hardware Check on the phone, and stated plainly.
- Bridge packaging for Ubuntu (they target Debian bookworm/trixie): patch the build deps per package, and record each patch in `packages/<name>/`.
- binfmt blocked: run the chroot stage inside a TCG VM.
- Disk (30 GB): clone kernels shallow, one at a time, and delete them after the build.
- Carrier-specific VoLTE and in-display fingerprint tuning are the two areas most likely to need on-phone fixes. Hardware Check pinpoints them.
- Time: this is large. Order of work: (1) common OS, touch-only policy, VM tests, apps; (2) 7T Pro halium kernel, boot image and bridges; (3) ucrom daemons and Hardware Check; (4) other SoCs. Each phase is committed and pushed when it's green.

## Summary: what ucrom is

ucrom is a custom operating system for OnePlus phones. It replaces Android with real Linux (Ubuntu 24.04 underneath) but keeps the Android way of using a phone. You unlock it with a PIN or your fingerprint, open apps from a grid, swipe to move around, and type on an on-screen keyboard. It includes calls, messages, contacts, a browser, a camera, a calculator, clocks, a text editor and a file manager. Because it's real Linux, it also runs Linux ARM64 apps, including AI agents and dev tools like Claude Code, Codex, VS Code-style editors such as Antigravity, and Python AI tools. A touch-friendly App Hub installs them with one tap.

It is touch-only by design. Keyboards, mice and touchpads are shut off at the Linux kernel level the moment they connect, over USB or Bluetooth. Their drivers are blocked, and the text console is removed. Only the touchscreen and the phone's own buttons work.

The main phone is the OnePlus 7T Pro McLaren Edition, and the goal there is a fully working phone: GPU, 90 Hz display, WiFi, Bluetooth, calls, audio, cameras including the pop-up, in-display fingerprint, sensors, NFC, GPS, charging and the alert slider. Pure Linux drivers for this phone don't exist yet. So ucrom runs Linux on top of the phone's own original hardware drivers through a small hidden driver container (the approach Ubuntu Touch and Droidian use). It adds its own helpers for OnePlus-specific parts like the pop-up camera, the alert slider and the in-display fingerprint. One OS also adapts to other Snapdragon chips (820 through 888, with 8 Gen chips experimental) through a short profile per chip and per phone.

It's proven two ways. Here, in an emulated arm64 phone with a real multitouch screen, automated tests drive the exact same OS only by touch, show that keyboard and mouse input is ignored, install AI apps, and check every built kernel, boot image and driver bridge. On the real phone, the built-in Hardware Check app tests every component and produces a report. That on-phone report is the part no emulator can replace.
