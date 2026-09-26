# ucrom: status and hand-off

Last updated 2026-09-26, 19:40 UTC. This file is the place to start if you
pick the work up from a clone or a zip of this repository. It says what is
done, what is proven and how, what is still open, and the exact commands to
carry on.

Related: [PLAN.md](PLAN.md) (the agreed plan), [BUILDING.md](BUILDING.md),
[TESTING.md](TESTING.md), [test-report/REPORT.md](test-report/REPORT.md),
[build-records/](build-records/) (checksums, configs and results of the
builds made so far).

## What is in git and what is not

Everything needed to rebuild is in git: build scripts, package lists,
overlays, chip and phone profiles, kernel config fragments and patches,
ucrom's own daemons and apps, the tests, docs, and the last test report.

Built outputs are **not** in git (they live in `build/` and `out/`, both in
`.gitignore`). They are large and they are rebuilt by `make`:

| Output | Size | Rebuild with |
|---|---|---|
| Emulator image `out/qemu/ucrom-qemu.qcow2` | 2.5 GB | `make qemu-image` |
| 7T Pro `boot.img`, `dtbo.img`, `initrd.img` | 70 MB, 3 MB, 10 MB | `make device DEVICE=oneplus-hotdog` |
| Bridge packages `out/bridges/*.deb` | 3 MB so far | `make bridges` |
| Root filesystems `build/rootfs-*` | several GB | `make rootfs` |

Their checksums, kernel configs and validation results are copied into
[build-records/](build-records/) so a rebuild can be compared.

## Setting up a machine to continue

Ubuntu 24.04 (x86_64 or arm64) with root, about 60 GB free disk, 8 GB RAM
and internet. Install the host packages listed in
[BUILDING.md](BUILDING.md#host) (one `apt install` line).

Then, from the repository root (most targets need root):

```sh
sudo make rootfs-mainline qemu-image     # the emulator phone
sudo make test-fast                      # tests that need no emulator
sudo tools/dev/run-tests-paused.sh report  # full suite + docs/test-report/
```

## Done

- **OS image.** Ubuntu 24.04 arm64 root filesystem with Phosh, the touch
  apps, ucrom branding, Node 22 for AI agents, App Hub and Hardware Check.
  Builds from scratch with `make rootfs-mainline`.
- **Touch-only policy.** Keyboards, mice, touchpads and anything on USB or
  Bluetooth input are inhibited in the kernel and ignored by libinput; HID
  drivers blocked; BlueZ input plugins off; no text consoles, SysRq or SSH.
- **Emulator test phone.** QEMU arm64 with a real multitouch screen plus
  attack keyboards and mice, driven only by touch events and read back by
  OCR (`tests/vm.py`, `tests/ui.py`).
- **OnePlus 7T Pro kernel.** LineageOS 20 kernel (4.14.180) builds with the
  Halium and touch-only fragments, 0 fragment mismatches, 20 DTBs and 10
  DTBO overlays. `boot.img` (header v2) and `dtbo.img` build and pass their
  structure tests (see build-records/oneplus-hotdog/halium/).
- **Mainline fallback for the 7T Pro.** DTBs build from the sm8150-mainline
  6.14 tree with a new `sm8150-oneplus-hotdog.dts`.
- **ucrom hardware helpers.** Alert slider, pop-up camera (with free-fall
  retract), in-display fingerprint helper and refresh-rate helper. All pass
  against simulated hardware in the emulator.
- **Chip matrix.** Nine chip profiles and fifteen phone profiles resolve and
  validate (`make validate-socs`, 67 checks).

## Proven by the latest full test run

`docs/test-report/` holds the run of 2026-09-26 17:15 UTC:
**79 passed, 27 failed, 1 skipped**. What passed includes: the image
contents, boot to the touch shell, keyboard/mouse inhibited in the kernel,
USB keyboard/mouse hot-plug blocked, touch delivered, unlock by PIN taps,
the on-screen keyboard in the terminal, quick settings, the power button,
all hardware helper tests, Hardware Check reporting every missing part as
ABSENT, and the Python AI tool (llm via pipx) installing over the network.

The 27 failures, at that time:

- 21 are Halium bridge packages that were not built yet.
- 6 were test problems that have fixes merged since: the keyboard-attack
  screenshot (panel not lit yet), the calculator (keypad moving when the
  on-screen keyboard slides in), and the four App Hub / AI agent / VS Code
  tests (the restarted shell was still locked).

## Open items, in order

1. **Re-run the emulator suite and commit a fresh report.** A verification
   run at 17:38 UTC failed 12 tests. Findings, all fixed in the test harness
   (the OS itself behaved correctly):
   - The run started with the touch-only tests straight after boot. The
     guest agent answers before udev has applied its rules, so the
     keyboard/mouse were not inhibited *yet*. On a fully booted emulator
     they are (checked by hand: keyboard and mouse `inhibited=1`, libinput
     sees only the touchscreen and power keys). The emulator fixture now
     waits for `systemctl is-system-running --wait` and `udevadm settle`.
   - Unlock: Phosh sometimes drops PIN taps under emulation (libinput
     receives every tap; the PIN pad shows fewer dots). The unlock helper
     now counts the dots it sees and clears and retypes more slowly if
     digits are missing. Checked by hand: unlocked twice in a row.
   - The full run at 18:31 still failed unlock, and every touch test after
     it. Cause (proven on the emulator): the USB hot-plug test leaves a USB
     mouse attached, and QEMU then routes the injected touch button events
     to that mouse, so no tap or swipe reaches the touchscreen. Unlock
     failed with the USB mouse plugged in and worked right after unplugging
     it. The hot-plug test now unplugs its devices when it ends. This is a
     QEMU input-injection quirk; a real phone is not affected.
   Most other failures followed from the phone staying locked. Run
   `sudo tools/dev/run-tests-paused.sh report` on a quiet machine and
   commit `docs/test-report/`.
2. **Finish the bridge packages.** 5 of 27 build (see
   build-records/bridges/status.tsv): libglibutil, libgbinder,
   android-headers-30, libhybris, parse-android-dynparts. Fixes for the next
   ones (build order, libdroid, generated changelog) are merged but were
   still building. Continue with `sudo make bridges`: it skips packages
   already built. Each failure's log is in `out/bridges/logs/<name>.log`.
3. **Rebuild the Halium root filesystem with the bridges**
   (`sudo make rootfs-halium`), then **rebuild the 7T Pro images**
   (`sudo make device DEVICE=oneplus-hotdog`). The userdata sizing fix is
   merged but these images were built before it. The last `VALIDATION` file
   only has the sparse size because the userdata step ran out of disk then.
4. **Halium Android system image.** It cannot be built on a small machine;
   fetch it with `scripts/fetch-halium-system.sh 13` (or build it with
   `scripts/build-halium-system.sh` on a machine with 250 GB free), then
   pass `HALIUM_SYSTEM_IMAGE=out/halium-system/android-rootfs.img` to
   `make device` (see [BUILDING.md](BUILDING.md)).
5. **Mainline 7T Pro kernel config.** `fragment_mismatches=1`
   (build-records/oneplus-hotdog/mainline/kernel-BUILD_INFO): one option in
   the fragments does not stick on 6.14. Find it in the kernel build log and
   fix the fragment or document why.
6. **Other phones.** Build and test the mainline images for fajita (6T,
   sdm845) and instantnoodlep (8 Pro, sm8250): `sudo make device
   DEVICE=oneplus-fajita`, `DEVICE=oneplus-instantnoodlep`.
7. **Cosmetic.** A mouse pointer sprite is visible in the emulator (the
   virtio touchscreen also reports pointer capability). The tests ignore
   its resting spot; on a phone there is no such device.
8. **On the real phone.** Flash per [FLASHING.md](FLASHING.md), run
   Hardware Check, and send back its HTML report. That is the only proof of
   the phone's own drivers that no emulator can give.

## Lessons learned (save yourself time)

- **Keep the machine quiet while the emulator tests run.** There is no KVM,
  so the arm64 phone is emulated in software. If anything else is busy
  (the bridge builds, a big `find`, a kernel build), touch gestures arrive
  late, libinput logs "event processing lagging behind" and Phosh ignores
  swipes. `tools/dev/run-tests-paused.sh` pauses the bridge builder for you.
- **`pkill -f` / `pgrep -f` match their own shell.** A command line that
  contains the pattern (for example `pkill -f qemu-system` inside
  `bash -c "..."`) kills or finds itself. Write the pattern as
  `'[q]emu-system'`. The tests use `ui._self_safe()` for the same reason.
- **A frozen (SIGSTOP) shell wakes up when anything sends it SIGCONT.** A
  shell that had stopped itself at 13:20 was resumed hours later by a
  "resume the builder" step whose pattern matched its command line, and it
  started a stale `make report`. Check `ps -eo stat,pid,args | grep '^T'`
  for leftovers before long runs.
- **Do not edit a shell script while it runs.** Bash reads scripts as it
  goes; an edit in place corrupts the running copy. Write a new file and
  rename it over the old one, or wait for the run to end.
- **Background processes started through the guest agent must detach their
  output** (`>/dev/null 2>&1 &`), or `phone.sh()` waits until they exit.
- **`nohup VAR=value cmd` does not work**; use `nohup env VAR=value cmd`.
- **Phosh 0.38 in the emulator:** `ScreenSaver.GetActive` and logind's
  `LockedHint` read false while the lock screen shows, so the tests check
  the screen itself. The PIN page goes back to the clock after about 5 s
  without input, so the PIN is tapped in one go.

## Hands-on with the emulator

```sh
sudo tools/dev/boot-vm.py /tmp/ucrom-vm &          # boot, keep running
sudo tools/dev/vm.py /tmp/ucrom-vm shot /tmp/s.png  # screenshot
sudo tools/dev/vm.py /tmp/ucrom-vm sh 'libinput list-devices'
sudo tools/dev/vm.py /tmp/ucrom-vm 'import ui; ui.swipe_up_from_bottom(vm)'
```

The phone user is `ucrom`, PIN `147258` (config/ucrom.conf).

## Git

Work was done on `claude/custom-linux-rom-oneplus-chbmxa` and merged to
`main` through PR #1 and PR #2. Continue on a new branch from `main`.
