# Build records

Small files copied from the build outputs (`out/`, not in git), so a clone
of this repository shows what was built and a rebuild can be compared.

| Path | What |
|---|---|
| `qemu/SHA256SUMS`, `qemu/KERNEL_VERSION` | the emulator image the last test report ran on |
| `oneplus-hotdog/halium/` | 7T Pro (Halium flavor): kernel BUILD_INFO and full `.config`, SHA-256 and sizes of `boot.img`, `dtbo.img`, `initrd.img` |
| `oneplus-hotdog/mainline/` | 7T Pro mainline fallback: kernel BUILD_INFO and `.config` (device trees only) |
| `bridges/status.tsv` | Halium bridge packages: name, result, version, source commit |
| `validate-socs.json` | `make validate-socs` results for every chip profile |

Recorded 2026-09-26. The 7T Pro images were built before the userdata
sizing fix; see [../STATUS.md](../STATUS.md) for what to rebuild.
