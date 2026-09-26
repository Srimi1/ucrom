# Building ucrom

## Host

Ubuntu 24.04 (x86_64 or arm64), root, about 60 GB free disk and 8 GB RAM. On an x86_64 host the arm64 root filesystem is built through `qemu-user-static` (binfmt), which is slow but needs no arm64 hardware. No KVM needed.

```sh
sudo apt install qemu-system-arm qemu-user-static qemu-utils mmdebstrap mkbootimg \
    android-sdk-libsparse-utils device-tree-compiler gcc-aarch64-linux-gnu \
    gcc-arm-linux-gnueabi clang lld bc flex bison libssl-dev cpio kmod e2fsprogs \
    tesseract-ocr python3-pytest python3-pil rsync zstd git curl jq
```

Behind a TLS-intercepting proxy, set `UCROM_BUILD_CA=/path/to/proxy-ca.pem`; it is trusted inside the build chroots only while building and removed afterwards.

## Steps

| Command | Time (4 cores, no KVM) | Output |
|---|---|---|
| `make rootfs-common` | 30 to 60 min | `build/rootfs-common.tar.zst` (cached) |
| `make rootfs-mainline` | 10 to 20 min | `build/rootfs-mainline/` |
| `make qemu-image` | 10 min | `out/qemu/ucrom-qemu.qcow2`, `vmlinuz`, `initrd.img` |
| `make bridges` | hours (emulated arm64 builds) | `out/bridges/*.deb`, `status.tsv` |
| `make rootfs-halium` | 10 to 20 min | `build/rootfs-halium/` |
| `make kernel DEVICE=oneplus-hotdog` | 30 to 60 min | `out/devices/oneplus-hotdog/halium/kernel/` |
| `make device DEVICE=oneplus-hotdog` | 10 min | `boot.img`, `dtbo.img`, `userdata.img` |
| `make validate-socs` | 5 min | `out/validate-socs.json` |
| `make test` / `make report` | 1 to 2 h | test results, `docs/test-report/` |

Pick another phone with `DEVICE=` (see `make list-devices`) and force a flavor with `FLAVOR=mainline` or `FLAVOR=halium`.

## The Android side for halium phones

The Halium system image is not built by these steps (it needs a full Android tree). Get it with `scripts/fetch-halium-system.sh 13` (downloads the official UBports Halium 13 image and verifies its GPG signatures), or build it yourself with `scripts/build-halium-system.sh` on a machine with about 250 GB free. Then:

```sh
sudo HALIUM_SYSTEM_IMAGE=out/halium-system/android-rootfs.img make device DEVICE=oneplus-hotdog
```

Without it the image still builds and boots Linux, but the bridges have no Android drivers to talk to.

## Settings

`config/ucrom.conf`: Ubuntu release and mirror, phone user name, the lock screen PIN (default `147258`, change it in Settings after the first boot), hostname, Node.js version, root filesystem size, `UCROM_PREINSTALL_AI`.

Package lists: `config/packages/*.list`. Files copied into the image: `rootfs/overlay/`. Configuration steps run inside the image: `rootfs/hooks/*.chroot` (`1-*` for every image, `2-*` final, `<flavor>-*` per flavor).

## Adding a phone

1. Find its chip in `socs/`. If missing, add `socs/<soc>/soc.conf` (copy a neighbour).
2. Add `devices/oneplus-<codename>/device.conf` with name, models, chip, flavor, screen, cmdline and device tree.
3. `make validate-socs` checks the kernel branch, defconfig and device tree upstream.
4. `make device DEVICE=oneplus-<codename>`.
