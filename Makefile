# ucrom build entry points. Most targets need root (chroots, loop/overlay mounts).
#
#   make list-devices                  supported phones and chips
#   make rootfs                        common + mainline + halium root filesystems
#   make qemu-image                    emulator image (the test phone)
#   make bridges                       Halium hardware bridge packages
#   make kernel DEVICE=oneplus-hotdog  kernel only
#   make device DEVICE=oneplus-hotdog  flashable boot.img / dtbo.img / userdata.img
#   make validate-socs                 config + boot image checks for every chip
#   make test                          full test suite (boots the emulator)
#   make test-fast                     tests that don't boot the emulator
#   make report                        test report -> docs/test-report/

DEVICE ?= oneplus-hotdog
FLAVOR ?=
PYTEST ?= python3 -m pytest

.PHONY: help list-devices rootfs rootfs-common rootfs-mainline rootfs-halium qemu-image \
        bridges kernel device validate-socs test test-fast report clean

help:
	@sed -n '1,14p' Makefile | sed 's/^# \{0,1\}//'

list-devices:
	@scripts/resolve-device.sh --list

rootfs: rootfs-mainline rootfs-halium

rootfs-common:
	scripts/build-rootfs.sh common

rootfs-mainline:
	scripts/build-rootfs.sh mainline

rootfs-halium: bridges
	scripts/build-rootfs.sh halium

qemu-image: rootfs-mainline
	scripts/build-qemu-image.sh

bridges:
	scripts/build-bridges.sh

kernel:
	scripts/build-kernel.sh $(DEVICE) $(FLAVOR)

device:
	scripts/build-device.sh $(DEVICE) $(FLAVOR)

validate-socs:
	scripts/validate-socs.sh

test:
	$(PYTEST) tests -v

test-fast:
	UCROM_SKIP_VM=1 $(PYTEST) tests -v

report:
	$(PYTEST) tests -v --ucrom-report

clean:
	rm -rf build out
