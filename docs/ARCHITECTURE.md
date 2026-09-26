# Architecture

## Layers

```
┌───────────────────── ucrom root filesystem (same on every phone) ─────────────────────┐
│ Ubuntu 24.04 arm64 · systemd · Phosh + phoc · phone apps · App Hub · Hardware Check    │
│ touch-only policy (udev + modprobe + BlueZ + no consoles) · ucrom hardware helpers    │
├──────────────────────────── hardware flavor (per phone) ───────────────────────────────┤
│ mainline: mainline kernel + device tree + linux-firmware                               │
│ halium:   vendor kernel + Halium Android container + bridge services                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Build inputs:

| Layer | Where | What it holds |
|---|---|---|
| OS | `config/`, `rootfs/`, `apps/`, `ucrom/` | package lists, overlay files, chroot hooks, ucrom apps and helpers |
| Chip | `socs/<soc>/soc.conf` | kernel repos and branches (both flavors), defconfig, boot image header and offsets |
| Phone | `devices/<phone>/device.conf` | name, models, screen, flavor, device tree, kernel cmdline, firmware, sensor geometry, feature list |
| Kernel fragments | `socs/common/*.config` | `halium.config`, `mainline.config`, `kernel-touch-only.config` |
| Bridges | `packages/bridges.list` | source repos and branches of the Halium bridge packages |

`scripts/resolve-device.sh` merges phone and chip profiles; every build script uses it.

## The halium flavor (OnePlus 7T Pro)

Mainline Linux for the Snapdragon 855 phones drives touch, a boot framebuffer, Wi-Fi, USB and the modem, but not the GPU, audio, cameras, fingerprint or sensors. To make the phone fully functional, ucrom uses the approach Ubuntu Touch and Droidian use:

1. **Kernel**: the phone's own LineageOS 20 kernel (`LineageOS/android_kernel_oneplus_sm8150`, Linux 4.14) with every OnePlus driver, plus `halium.config` (namespaces, binderfs, loop/dm for dynamic partitions, Bluetooth VHCI, systemd needs) and the touch-only fragment.
2. **Boot**: an Android boot image (header v2, DTB included, separate `dtbo.img`) whose initramfs is Halium's boot logic: it finds `rootfs.img` on the userdata partition, maps the dynamic `super` partition (vendor, odm) with `parse-android-dynparts`, and starts ucrom's systemd.
3. **Android container**: a minimal Android system image (Halium) runs in LXC. It only loads the phone's hardware drivers (HALs) from the phone's own vendor partition, which LineageOS 20 installed.
4. **Bridges**: Linux services reach those drivers:

| Hardware | Bridge | Linux side |
|---|---|---|
| GPU, display, 90 Hz | libhybris + wlroots hwcomposer backend | phoc / Phosh |
| Audio (speaker, earpiece, mic, headset) | pulseaudio-modules-droid | PulseAudio |
| Calls, SMS, mobile data | ofono + ofono-binder-plugin + ofono2mm | ModemManager API (GNOME Calls, Chatty) |
| Bluetooth | bluebinder (HAL to VHCI) | BlueZ |
| Fingerprint | droidian-fpd | D-Bus, `ucrom-fod` |
| Cameras | droidmedia + gst-droid | droidian-camera |
| Sensors | sensorfw hybris backend | iio-sensor-proxy clients |
| Vibration, flashlight | feedbackd, flashlightd | Phosh |
| NFC | nfcd + nfcd-binder-plugin | nfcd D-Bus |
| Wi-Fi, battery, charging | vendor kernel drivers directly | NetworkManager, UPower |

All bridges are built from source for Ubuntu noble arm64 by `scripts/build-bridges.sh`.

## ucrom's own OnePlus helpers (`ucrom/ucromhw`)

| Helper | Hardware interface (from the vendor kernel / LineageOS) | Behaviour |
|---|---|---|
| `ucrom-alertslider` | input device `oplus,hall_tri_state_key`, KEY_F3 value 1/2/3; `/proc/tristatekey/tri_state` | up = silent, middle = vibrate, down = ring (feedbackd profile) |
| `ucrom-popup-camera` | `/sys/class/motor/{direction,enable,position}` | camera up while the front camera (id 1) is open, down after; pulled in on free fall |
| `ucrom-fod` | droidian-fpd D-Bus; `/sys/kernel/oplus_display/dimlayer_bl_en`; sensor at (720, 2728) r=132 | lights the sensor during scans, unlocks the lock screen on a match |
| `ucrom-refresh-rate` | output modes via wlr-randr | 60 / 90 Hz |

Each helper reads hardware paths through `UCROM_HW_ROOT`, so the test suite runs the same code against simulated hardware.

## The mainline flavor

Used where upstream Linux support is good (OnePlus 6/6T, 8 Pro) and as the 7T Pro fallback. Kernel from the chip's mainline tree with postmarketOS's base config, `mainline.config` and the touch-only fragment. For the 7T Pro, ucrom ships its own device tree (`devices/oneplus-hotdog/dts/sm8150-oneplus-hotdog.dts`), derived from the 7 Pro and cross-checked against the vendor tree for project 19801.

## The emulator image

`scripts/build-qemu-image.sh` takes the mainline-flavor root filesystem and adds Ubuntu's generic arm64 kernel, nothing else. The tests therefore exercise the same userspace that goes on the phone.
