# Touch only

ucrom is operated with the touchscreen and nothing else. Keyboards and mice are not hidden or discouraged: they are switched off in the kernel. These layers work together, so defeating one is not enough:

| Layer | File | Effect |
|---|---|---|
| Kernel input inhibit | `/etc/udev/rules.d/90-ucrom-touch-only.rules` | Every keyboard, mouse, touchpad, pointing stick, trackball, joystick and drawing tablet, and **any** input device on USB or Bluetooth, gets `inhibited=1`. The kernel then delivers no events to anybody: not the shell, not a console, not a program reading the device directly. libinput is also told to ignore it. |
| No HID drivers | `/etc/modprobe.d/ucrom-no-hid.conf`, kernel fragment | `usbhid`, `hid_generic`, `hidp` (Bluetooth), `uhid`, `usbkbd`, `usbmouse` can never load (`install ... /bin/false`). Phone kernels are built with USB HID, Bluetooth HID and UHID compiled out. |
| Bluetooth | `bluetooth.service` drop-in | BlueZ runs with `--noplugin=input,hog`, so keyboards and mice cannot even pair as input devices. Audio and file transfer still work. |
| No text console | hooks + logind + sysctl | All getty units masked, `NAutoVTs=0`, SysRq disabled (`kernel.sysrq=0`, `CONFIG_MAGIC_SYSRQ` off), no SSH server, root password locked, no console on the phone's kernel command line. The power key never shuts the phone down from logind. |
| From the first second | initramfs | On halium phones the same udev rule is in the initramfs, so the policy applies before the root filesystem is even mounted. |
| Guard | `ucrom-input-guard.service` | Re-applies the rules to every input device at boot and logs what it blocked. |

What stays allowed: touchscreens, and the phone's own buttons (power, volume, alert slider), which the kernel reports as keys but never as a keyboard.

Everything a keyboard used to do has a touch replacement: the on-screen keyboard is on by default (with a terminal layout that has Ctrl, Esc, Tab and arrows), the lock screen has a PIN pad and fingerprint unlock, and the phone logs in by itself.

## Why the kernel keeps virtual terminals

`CONFIG_VT` stays enabled on purpose. The Phosh session is a login session on a virtual terminal (tty7), and Halium requires it. A virtual terminal without any usable keyboard is not an input path: no login prompt runs on any of them, SysRq is off, and keyboards are inhibited before anything could read them.

## Limits, stated honestly

- An **unlocked bootloader** can still be reflashed over USB with fastboot. That's a flashing path, not an input path, and it's how ucrom gets installed. Relocking the bootloader with your own AVB key closes it; that's a later step and not done by these scripts.
- Someone with root on the running phone could remove the rules. ucrom ships no remote shell and no root password, so there's no way in without the PIN.

## How it's tested

`tests/test_20_touch_only.py` boots the image with a virtio keyboard and mouse attached, types and moves/clicks on them, and hot-plugs a USB keyboard and mouse. It checks that zero events reach the device nodes, the screen doesn't change, no driver binds, and `modprobe usbhid` is refused. See the test report.
