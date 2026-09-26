# Installing ucrom on a phone

**Read all of this first.** Installing ucrom erases the phone's user data. Keep a way back to stock.

## OnePlus 7T Pro / 7T Pro McLaren Edition (hotdog)

### 1. Safety net

Download the **MSM Download Tool** package for your exact model (HD1911 India / HD1913 EU / HD1910 NA) from a trusted source and keep it on a Windows PC. It restores the phone to stock OxygenOS from EDL mode, even if the phone won't boot at all. With it, a bad flash is recoverable.

### 2. Unlock the bootloader

OxygenOS: Settings, About phone, tap Build number 7 times; Developer options, turn on OEM unlocking and USB debugging. Then:

```sh
adb reboot bootloader
fastboot oem unlock        # erases the phone
```

### 3. Install LineageOS 20

Follow the official LineageOS 20 install guide for `hotdog`. ucrom reuses the Android 13 vendor drivers and firmware LineageOS puts on the `vendor`, `odm` and modem partitions, read-only. Boot LineageOS once to make sure everything works on your unit.

### 4. Build ucrom

```sh
scripts/fetch-halium-system.sh 13
sudo HALIUM_SYSTEM_IMAGE=out/halium-system/android-rootfs.img make device DEVICE=oneplus-hotdog
```

### 5. Try it without replacing anything

Phone in fastboot mode (Power + Volume Up + Volume Down), USB connected:

```sh
scripts/flash.sh oneplus-hotdog --try
```

This writes `userdata` (ucrom lives there) and **boots ucrom from RAM once**. The boot partition is not touched, so rebooting returns to LineageOS (which will ask to format data, since userdata now holds ucrom).

### 6. Install for good

```sh
scripts/flash.sh oneplus-hotdog
```

Flashes `boot`, `dtbo` and `userdata` on the active slot and reboots into ucrom.

### 7. First boot

- The lock screen shows. Swipe up, enter the PIN (`147258` by default), change it in Settings.
- Open **Hardware Check**, tap **Run checks**, answer the questions, and keep the report (`~/ucrom-hardware-report.html`).
- Enroll a fingerprint in Settings.

### Going back

LineageOS: flash its `boot.img`/`dtbo.img` from the LineageOS zip and format data in recovery. Stock: MSM Download Tool.

## Mainline phones (OnePlus 6/6T, 8 Pro)

```sh
sudo make device DEVICE=oneplus-fajita       # or oneplus-instantnoodlep
scripts/flash.sh oneplus-fajita --try
```

Mainline phones don't need LineageOS first, but proprietary firmware is fetched from the device's firmware repository at build time.
