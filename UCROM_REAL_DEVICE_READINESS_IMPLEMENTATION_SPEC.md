---
title: "UCROM Real-Device Readiness and Safe Flashing Implementation Specification"
document_id: "UCROM-RDR-001"
document_version: "1.0"
repository: "Srimi1/ucrom"
baseline_commit: "5b42d790b062c3a268f6b9117eaaa4d756ad718f"
default_branch: "main"
primary_device_profile: "oneplus-hotdog"
intended_hardware_family: "OnePlus 7T Pro / 7T Pro McLaren, non-5G hotdog variants"
initial_allowed_models:
  - "HD1910"
  - "HD1911"
  - "HD1913"
explicitly_not_covered:
  - "HD1925 / hotdogg / OnePlus 7T Pro 5G McLaren"
  - "Any model not positively identified before flashing"
project_type: "Ubuntu 24.04 + Phosh Linux phone OS using Halium for Android hardware drivers"
document_status: "Implementation plan; not a statement that the ROM is ready to flash"
---

# 1. Purpose

This file is the implementation specification for converting the current UCROM repository from an emulator-tested prototype into a controlled, evidence-driven real-device port for the OnePlus 7T Pro family.

The implementing AI must treat this document as an engineering contract. It must not interpret it as permission to flash a real device immediately. The work is divided into gated phases. A later phase must not begin until the acceptance criteria and evidence requirements of every dependency phase are satisfied.

The immediate objective is:

> Produce a genuinely non-destructive diagnostic boot path, a reproducible and fail-closed build pipeline, a model-locked installer, and a documented recovery process before any persistent UCROM installation is attempted.

The longer-term objective is:

> Reach a laboratory-quality UCROM installation on an exact supported device, then bring up hardware one subsystem at a time, and only afterward evaluate whether it can become a daily-driver candidate.

## 1.1 Important product clarification

UCROM is not an Android 16 custom ROM. It is a Linux phone operating system based on Ubuntu 24.04 and Phosh. The Android/Halium component exists to load and bridge proprietary Android hardware drivers. It is not automatically a normal Android application environment and does not automatically provide Google Play Store, Play Services, Android banking apps, or Android SafetyNet/Play Integrity compatibility.

The implementing AI must not claim that:

- Halium makes UCROM an Android ROM.
- Google Play Store will work merely because an Android container exists.
- Passing QEMU tests proves real phone hardware.
- A successful kernel build proves that calls, cameras, fingerprint, charging, suspend, or mobile data work.
- An unlocked bootloader provides the same security guarantees as a locked stock installation.

If the actual product requirement is Android 16 plus Play Store plus an Android launcher, that is a separate project based on a maintained Android ROM tree. Do not quietly change UCROM into that project while implementing this plan.

# 2. AI implementation contract

## 2.1 Operating rules

The implementing AI must follow these rules throughout the project:

1. **Read before editing.** Open every file named in a phase before changing it. Never infer file contents from the filename.
2. **Work from the recorded baseline.** Confirm that the working tree is based on commit `5b42d790b062c3a268f6b9117eaaa4d756ad718f`, or explicitly document all later commits before applying this plan.
3. **Use a dedicated branch.** Suggested branch: `hardening/real-device-readiness`.
4. **Make small, reversible commits.** One concern per commit. Do not combine flashing safety, build reproducibility, hardware enablement, and cosmetic changes.
5. **Do not execute destructive phone commands.** The AI may write and test code using fake `adb` and `fastboot` executables. It must not run `fastboot flash`, `fastboot erase`, `fastboot format`, `fastboot set_active`, bootloader unlock, EDL, or partition-writing commands against a real device.
6. **Do not create an automatic destructive fallback.** If `fastboot boot` is unsupported or fails, stop. Never automatically replace it with `fastboot flash boot`.
7. **Fail closed.** Missing files, unknown models, ambiguous image types, failed bridge packages, skipped critical tests, checksum mismatches, or unverified signatures must stop the release path.
8. **Never convert warnings into success for critical operations.** Remove patterns such as `|| true` from safety-critical, identity, build, packaging, and validation operations unless the ignored failure is explicitly documented and tested as non-critical.
9. **Pin external dependencies.** Branch names are insufficient for release builds. Record immutable commit SHAs and expected artifacts.
10. **Separate claims by evidence level.** Use only these labels:
    - `SOURCE_REVIEWED`
    - `STATIC_TESTED`
    - `EMULATOR_TESTED`
    - `BUILT_FOR_DEVICE`
    - `DIAGNOSTIC_BOOT_TESTED`
    - `REAL_DEVICE_TESTED`
    - `DAILY_DRIVER_VALIDATED`
11. **Never promote evidence.** For example, `BUILT_FOR_DEVICE` must never be described as `REAL_DEVICE_TESTED`.
12. **Record uncertainty.** When device behaviour or an upstream interface is unknown, add it to `docs/BLOCKERS.md`; do not invent a value.
13. **Do not relock the bootloader.** AVB key enrollment and relocking are out of scope until a separate, reviewed verified-boot design exists. A wrong relock procedure can make recovery significantly harder.
14. **Do not touch radio, bootloader, security, calibration, or persistent identity partitions.** The initial installer may eventually be allowed to write only the specifically audited partitions described in this document.
15. **Do not enable all hardware at once.** Each dangerous or vendor-specific subsystem must be feature-gated and enabled only after the previous subsystem has passed.
16. **Protect personal data.** No primary SIM, banking accounts, authenticator secrets, or irreplaceable files may be used during laboratory testing.
17. **Treat Windows as a supported flashing host.** Build on Ubuntu, but make the verification and flashing controller cross-platform.

## 2.2 Source-of-truth order

When two sources disagree, use this order and record the disagreement:

1. Real-device information captured from the exact test unit.
2. Image metadata generated by the current build.
3. Pinned upstream source at the exact locked commit.
4. Official device-maintainer documentation.
5. Current repository documentation.
6. Community posts only as leads, never as final proof.

## 2.3 Anti-hallucination protocol

For every phase, the AI must:

- List the exact facts it verified.
- List the assumptions it did not verify.
- Include command output or test artifacts supporting each completed acceptance criterion.
- Use `UNKNOWN` rather than a guessed model, partition size, image type, service name, sysfs path, slot layout, or tool behaviour.
- Stop and create a blocker when a required fact cannot be verified.
- Never write “ready to flash” unless all gates named in Section 6.2 are green.
- Never write “hardware works” unless the feature was tested on the exact physical device and the evidence bundle contains the result.
- Never use the presence of a driver config symbol as proof that the hardware works.
- Never use a service starting successfully as proof that the underlying hardware works.
- Never use a generic OnePlus model name as proof of the exact model code.

## 2.4 Required AI report after each phase

The AI must return a report in this format:

```markdown
## Phase report

- Phase ID:
- Baseline commit:
- Ending commit:
- Evidence level reached:
- Files changed:
- Tests added:
- Tests executed:
- Exact test results:
- Generated artifacts:
- Assumptions remaining:
- Blockers:
- Safety impact:
- Rollback instructions:
- Next phase allowed: yes/no
- Reason:
```

# 3. Baseline facts that must remain visible

The current repository has several important properties that drive this plan:

- `scripts/flash.sh oneplus-hotdog --try` writes `userdata.img` before executing `fastboot boot`. Therefore the existing “try” mode is destructive to user data.
- The current script reads the fastboot product but does not enforce an exact allowlist match.
- The current build can continue without a Halium Android image.
- The current build path may rename or place `android-rootfs.img` and `system.img` in a way that loses their distinct mounting semantics.
- `scripts/build-bridges.sh` records failures but exits successfully.
- The normal GitHub Actions workflow does not build the complete hotdog Halium release candidate.
- Device-specific tests can skip when artifacts are absent.
- The tracked configuration contains a public fixed PIN.
- The normal phone user is placed in `sudo` and several hardware groups.
- Hardware-control daemons, including the pop-up camera helper, are enabled during image creation.
- The touch-only release policy removes useful early-port recovery and debugging paths.
- The current README accurately states that the OS has not yet been run on a real OnePlus 7T Pro.

These are not merely documentation issues. They are release blockers.

# 4. Target architecture

## 4.1 Build host and flashing host

Use two distinct roles:

### Build host

- Ubuntu 24.04 virtual machine or dedicated Linux machine.
- No personal SSH keys, browser profiles, cloud credentials, or private files.
- Enough disk for the root filesystem, bridge packages, kernel, and artifacts.
- External downloads pinned and verified.
- Produces a self-contained release bundle.

### Flashing host

- Windows, Linux, or macOS.
- Uses a cross-platform Python controller.
- Uses a pinned Android Platform Tools version supplied separately by the user.
- Verifies the release bundle before communicating with the device.
- Never builds source code and flashes it in one opaque action.

## 4.2 Replace the destructive shell entry point with a controller

Create a standard-library-only Python command-line program:

```text
tools/ucromctl.py
```

Suggested commands:

```text
ucromctl capture-device
ucromctl verify-bundle
ucromctl diagnostic-boot
ucromctl plan-install
ucromctl install
ucromctl collect-evidence
ucromctl print-rollback
```

Keep `scripts/flash.sh` only as a compatibility wrapper that:

- Prints a deprecation message.
- Refuses the old `--try` syntax.
- Delegates to `ucromctl.py` only after explicit arguments are supplied.
- Contains no direct partition-writing command.

Python is preferred because it provides deterministic argument parsing, JSON validation, subprocess handling, SHA-256 verification, Windows support, and straightforward fake-tool testing.

## 4.3 Release bundle layout

Every candidate must be packaged as:

```text
ucrom-hotdog-<version>-<commit>/
├── manifest.json
├── manifest.sha256
├── signatures/
│   └── manifest.sig
├── images/
│   ├── diagnostic-boot.img
│   ├── boot.img
│   ├── dtbo.img
│   └── userdata.img
├── metadata/
│   ├── source-lock.json
│   ├── halium-image.json
│   ├── bridge-status.json
│   ├── build-info.json
│   ├── test-summary.json
│   └── known-limitations.md
├── tools/
│   └── ucromctl.py
└── recovery/
    └── README.md
```

A laboratory bundle may omit large images only when its manifest explicitly says they are absent. The installer must never silently search nearby directories for replacement files.

## 4.4 Release states

Use these exact states:

| State | Meaning |
|---|---|
| `UNSAFE` | Source exists, but no release candidate may be used on a phone. |
| `BUILD_VERIFIED` | Required artifacts built from pinned inputs and passed static checks. |
| `DIAGNOSTIC_ONLY` | A zero-write diagnostic image exists. No persistent install permitted. |
| `DIAGNOSTIC_BOOT_VERIFIED` | Diagnostic image booted on the exact device with evidence. |
| `LAB_INSTALL` | Persistent install permitted only on a sacrificial/test device under the laboratory protocol. |
| `HARDWARE_BETA` | Required hardware matrix passed, but security or reliability work remains. |
| `DAILY_DRIVER_CANDIDATE` | Security, update, recovery, and soak-test gates passed. Still not a guarantee. |

The build must default to `UNSAFE`. State advancement must be based on evidence, not a manually edited README sentence.

# 5. Machine-readable execution manifest

The following JSON is a summary for orchestration. The detailed instructions later in this file remain authoritative.

```json
{
  "schema_version": 1,
  "project": "ucrom",
  "baseline_commit": "5b42d790b062c3a268f6b9117eaaa4d756ad718f",
  "target_profile": "oneplus-hotdog",
  "phases": [
    {
      "id": "P0",
      "name": "Baseline, evidence model, and repository guardrails",
      "depends_on": [],
      "gate": "G0"
    },
    {
      "id": "P1",
      "name": "Model-locked cross-platform device controller",
      "depends_on": ["P0"],
      "gate": "G1"
    },
    {
      "id": "P2",
      "name": "True zero-write diagnostic boot image",
      "depends_on": ["P0", "P1"],
      "gate": "G2"
    },
    {
      "id": "P3",
      "name": "Halium image identity and layout correctness",
      "depends_on": ["P0"],
      "gate": "G3"
    },
    {
      "id": "P4",
      "name": "Pinned and fail-closed bridge build",
      "depends_on": ["P0"],
      "gate": "G4"
    },
    {
      "id": "P5",
      "name": "Reproducible device build and signed manifest",
      "depends_on": ["P3", "P4"],
      "gate": "G5"
    },
    {
      "id": "P6",
      "name": "Release CI with no critical skips",
      "depends_on": ["P1", "P2", "P3", "P4", "P5"],
      "gate": "G6"
    },
    {
      "id": "P7",
      "name": "Debug and release profiles with hardware feature gates",
      "depends_on": ["P2", "P5"],
      "gate": "G7"
    },
    {
      "id": "P8",
      "name": "Exact-device recovery readiness",
      "depends_on": ["P1", "P6"],
      "gate": "G8"
    },
    {
      "id": "P9",
      "name": "First real-device diagnostic boot",
      "depends_on": ["P2", "P6", "P7", "P8"],
      "gate": "G9",
      "requires_human_device_operator": true
    },
    {
      "id": "P10",
      "name": "Controlled laboratory installation",
      "depends_on": ["P9"],
      "gate": "G10",
      "requires_human_device_operator": true
    },
    {
      "id": "P11",
      "name": "Subsystem-by-subsystem hardware bring-up",
      "depends_on": ["P10"],
      "gate": "G11",
      "requires_human_device_operator": true
    },
    {
      "id": "P12",
      "name": "Security, updates, encryption, and daily-driver qualification",
      "depends_on": ["P11"],
      "gate": "G12"
    },
    {
      "id": "P13",
      "name": "Release documentation and maintenance process",
      "depends_on": ["P12"],
      "gate": "G13"
    }
  ],
  "forbidden_automatic_actions": [
    "bootloader unlock",
    "bootloader relock",
    "fastboot flash",
    "fastboot erase",
    "fastboot format",
    "fastboot set_active",
    "EDL flashing",
    "radio partition writes",
    "bootloader partition writes",
    "calibration partition writes"
  ]
}
```

# 6. Gates and definitions of done

## 6.1 Gate evidence format

Create:

```text
out/evidence/<device-serial>/<yyyy-mm-ddThhmmssZ>/
```

Each evidence directory must contain:

```text
device-preflight.json
bundle-manifest.json
command-transcript.txt
test-results.xml
dmesg.txt
journal.txt
hardware-matrix.json
operator-observations.md
evidence.json
```

`evidence.json` must include the repository commit, bundle hash, device serial hash, exact model, slot state, timestamps, tests, failures, and release state reached.

Do not publish raw IMEI, phone number, SIM identifiers, Wi-Fi credentials, or unredacted device serials.

## 6.2 Global gates

### G0 — Repository guardrails

- Baseline recorded.
- Safety policy added.
- Blocker log added.
- No functional claims changed.

### G1 — Controller safety

- Diagnostic mode contains zero write commands.
- Unknown device or model is rejected.
- Multiple connected devices are rejected.
- Explicit serial is required.
- Fastbootd versus bootloader fastboot is detected.
- Fake-fastboot tests pass on Linux and Windows CI.

### G2 — Diagnostic image

- Entire root filesystem is in RAM.
- No userdata, super, vendor, odm, persist, modem, or calibration partition is mounted read-write.
- No hardware-control daemon starts.
- USB log channel or another reviewed log extraction path exists.
- Image can be structurally unpacked and validated.
- `ucromctl diagnostic-boot` performs only verification plus `fastboot boot`.

### G3 — Halium image correctness

- Image type is explicitly `android-rootfs` or `system`.
- Original type is preserved.
- GPG/signature verification is recorded.
- Source version and immutable checksum are recorded.
- Ambiguous or missing image stops the build.

### G4 — Bridge correctness

- Every required bridge uses an immutable commit.
- Any required bridge failure returns non-zero.
- Expected Debian packages and binaries are listed and verified.
- Root filesystem contains all required packages.
- Linker checks show no unresolved required libraries.

### G5 — Reproducible device bundle

- Build manifest contains every input commit and output hash.
- Kernel, boot, DTBO, userdata, Halium image, and bridge metadata agree.
- No tracked default credential exists.
- Release state remains no higher than `BUILD_VERIFIED`.

### G6 — Release CI

- Full hotdog Halium build completed.
- Critical tests did not skip.
- Test report and manifests are retained.
- Build cannot be marked successful with missing required artifacts.

### G7 — Safe debug profile

- Dangerous services disabled by default.
- Touch-only restrictions are not forced in diagnostic/debug profile.
- Release profile remains separate.
- Every hardware feature has an explicit enable flag.

### G8 — Recovery readiness

- Exact model positively identified.
- Recovery package is available for that exact model.
- Rollback procedure reviewed by the human operator.
- Known-good Android/Lineage boot and recovery files are locally available.
- Data backup completed.
- No primary SIM or sensitive data remains on the device.

### G9 — Diagnostic boot verified

- Boot occurred using `fastboot boot`.
- Command transcript proves no partition writes.
- Kernel logs were collected.
- Display/touch/USB status recorded honestly.
- Temperatures remained within the conservative test protocol.
- Any failure is understood before persistent install.

### G10 — Laboratory install

- Only audited partitions were written.
- Slot decisions were explicit.
- Full command transcript exists.
- Device can enter bootloader/recovery after installation.
- UCROM reaches at least the expected debug target or has actionable logs.
- Rollback has been tested or demonstrated.

### G11 — Hardware beta

- Hardware matrix completed.
- No critical thermal, charging, suspend, modem, or storage corruption issues.
- Motorised camera and fingerprint were tested only after prerequisites.
- Soak test completed without unexplained resets or data corruption.

### G12 — Daily-driver candidate

- Default credentials removed.
- Encryption strategy implemented and tested.
- Update signing and rollback implemented.
- Exposed services audited.
- Recovery procedure does not depend on one fragile tool.
- Primary-SIM and personal-data warnings can be reconsidered only after this gate.

# 7. Phase P0 — Baseline, evidence model, and repository guardrails

## Goal

Make the repository honest, auditable, and difficult for an automated agent to overstate.

## Files to add

```text
docs/REAL_DEVICE_READINESS_PLAN.md
docs/SAFETY_POLICY.md
docs/BLOCKERS.md
docs/EVIDENCE_LEVELS.md
docs/RELEASE_STATES.md
config/release-state.json
```

## Implementation tasks

1. Copy this specification into `docs/REAL_DEVICE_READINESS_PLAN.md`.
2. Set `config/release-state.json` to:

```json
{
  "schema_version": 1,
  "state": "UNSAFE",
  "reason": "No real-device diagnostic boot evidence exists",
  "baseline_commit": "5b42d790b062c3a268f6b9117eaaa4d756ad718f",
  "allowed_persistent_install": false,
  "allowed_primary_sim": false,
  "allowed_personal_data": false
}
```

3. Add `docs/BLOCKERS.md` with at least:
   - Exact model of the physical test device not yet captured.
   - `fastboot boot` support on the exact unit not yet proven.
   - Halium image layout ambiguity.
   - Bridge packages not release-pinned.
   - No full hotdog release CI.
   - No real-device logs.
   - No encryption or signed update design.
4. Update README status language only to link to the release state. Do not claim improved hardware support.
5. Add a repository rule in tests: the release state cannot advance without an evidence file.
6. Add `SECURITY.md` describing how to privately report a dangerous flashing bug.

## Tests

- JSON schema or Python validation for `config/release-state.json`.
- Test that the default state is `UNSAFE`.
- Test that `allowed_persistent_install`, `allowed_primary_sim`, and `allowed_personal_data` are false.
- Test that README links to the current release state.

## Acceptance criteria

- Documentation and state files exist.
- No actual flashing behaviour has changed.
- CI still passes.
- Evidence level remains honest.

## Prohibited actions

- Do not change release state to `DIAGNOSTIC_ONLY`.
- Do not add “safe,” “stable,” “daily driver,” or “fully functional” language.

# 8. Phase P1 — Model-locked cross-platform device controller

## Goal

Replace ambiguous, destructive flashing logic with a testable controller that defaults to verification and refuses unknown devices.

## Files to add

```text
tools/ucromctl.py
tools/ucromlib/__init__.py
tools/ucromlib/adb.py
tools/ucromlib/fastboot.py
tools/ucromlib/bundle.py
tools/ucromlib/device.py
tools/ucromlib/transcript.py
config/device-allowlist.json
schemas/device-preflight.schema.json
schemas/bundle-manifest.schema.json
tests/test_ucromctl_safety.py
tests/test_ucromctl_bundle.py
tests/fixtures/fastboot/
tests/fixtures/adb/
```

## Files to change

```text
scripts/flash.sh
docs/FLASHING.md
Makefile
.github/workflows/build-test.yml
```

## Device allowlist design

Start narrowly:

```json
{
  "schema_version": 1,
  "profiles": {
    "oneplus-hotdog": {
      "android_codenames": ["hotdog"],
      "allowed_model_codes": ["HD1910", "HD1911", "HD1913"],
      "explicitly_forbidden_model_codes": ["HD1925"],
      "possible_fastboot_products": ["msmnile", "hotdog"],
      "diagnostic_write_partitions": [],
      "lab_install_write_partitions": ["boot", "dtbo", "userdata"],
      "persistent_install_default": false
    }
  }
}
```

Do not add HD1917 merely because another project lists it. Add it only after its identity, partition layout, boot stack, and compatibility are audited.

## Required commands

### `capture-device`

Runs while Android or LineageOS is booted. It must:

- Require an explicit ADB serial.
- Capture multiple identity properties rather than trusting one:
  - `ro.product.model`
  - `ro.product.device`
  - `ro.product.vendor.device`
  - `ro.boot.product.hardware.sku`
  - `ro.boot.project_name`
  - `ro.build.fingerprint`
  - `ro.boot.slot_suffix`
- Capture battery level and temperature for preflight context.
- Capture current platform-tools versions.
- Produce `device-preflight.json`.
- Redact secrets from console output.
- Refuse to infer a model code when none of the properties expose it.
- Require a human-entered physical model code when the software properties are inconclusive.
- Mark the human-entered field as `operator_asserted`, not automatically verified.

Example:

```text
python tools/ucromctl.py capture-device \
  --adb-serial <serial> \
  --expected-profile oneplus-hotdog \
  --out device-preflight.json
```

### `verify-bundle`

Must perform no device communication. It must:

- Validate JSON schemas.
- Verify SHA-256 for every file.
- Verify manifest signature when release signing is enabled.
- Verify release state.
- Verify allowed model list.
- Verify image sizes recorded in the manifest.
- Verify no required image is absent.
- Verify all dependency lock metadata is present.
- Print a clear summary.

### `diagnostic-boot`

Must:

- Require explicit fastboot serial.
- Require a verified bundle.
- Require a matching `device-preflight.json`.
- Confirm exactly one matching device.
- Query and record:
  - product
  - unlocked state
  - current slot
  - `is-userspace`
  - `has-slot:boot`
  - `has-slot:dtbo`
  - partition sizes when supported
- Refuse fastbootd (`is-userspace: yes`) unless a later audited operation explicitly requires it.
- Refuse locked bootloader.
- Refuse unknown product.
- Refuse model mismatch.
- Execute exactly one device-changing command: `fastboot boot diagnostic-boot.img`.
- Execute no `flash`, `erase`, `format`, or `set_active`.
- Save a transcript.

### `plan-install`

Must not write anything. It must:

- Calculate the exact proposed commands.
- Determine current and inactive slots without changing them.
- Show partition names and image hashes.
- Show all blockers.
- Print `INSTALL PLAN ONLY`.
- Save the plan as JSON for human review.

### `install`

Must remain disabled until the release state and evidence gates permit it.

When later enabled, it must:

- Require an exact device serial.
- Require exact model confirmation.
- Require bundle status `LAB_INSTALL` or higher.
- Require a recovery-readiness record.
- Require an interactive confirmation containing serial, model, and bundle hash.
- Default to no automatic reboot.
- Enforce a hard partition allowlist.
- Refuse any image not named in the signed manifest.
- Record every command and response.
- Never support wildcard partition flashing.
- Never execute commands built from unvalidated user-provided partition strings.

## Fastboot parsing requirements

Fastboot commonly prints variables to stderr. The controller must combine stdout and stderr safely, preserve the raw transcript, and parse normalized lines.

Handle:

- CRLF on Windows.
- `(bootloader)` prefixes.
- `getvar` returning non-zero for unsupported variables.
- Multiple connected devices.
- No connected device.
- Device changing serial representation between ADB and fastboot.
- Unknown current slot.
- A non-slotted partition.
- A malicious or corrupted manifest.
- `fastboot boot` failure without falling back to flash.

## Compatibility wrapper

Replace the body of `scripts/flash.sh` with a wrapper similar in behaviour to:

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "scripts/flash.sh is deprecated."
echo "The old --try mode erased userdata and is disabled."
exec python3 "$(dirname "$0")/../tools/ucromctl.py" "$@"
```

The old positional interface must not remain accepted.

## Test design

Use fake executables placed first in `PATH`. Each fixture should record calls to a temporary file.

Required tests:

```text
test_diagnostic_boot_never_calls_flash
test_diagnostic_boot_never_calls_erase
test_diagnostic_boot_never_calls_format
test_diagnostic_boot_never_calls_set_active
test_diagnostic_boot_executes_only_expected_serial
test_rejects_multiple_devices
test_rejects_missing_serial
test_rejects_locked_bootloader
test_rejects_fastbootd
test_rejects_unknown_product
test_rejects_hd1925
test_rejects_model_mismatch
test_rejects_checksum_mismatch
test_rejects_unsigned_manifest_when_signature_required
test_rejects_missing_diagnostic_image
test_fastboot_boot_failure_has_no_fallback
test_plan_install_is_zero_write
test_install_is_disabled_below_lab_install_state
test_windows_crlf_and_stderr_parsing
```

Add a static test that fails if the diagnostic code path contains a subprocess argument equal to `flash`, `erase`, `format`, or `set_active`.

## Acceptance criteria

- All safety tests pass on Ubuntu and Windows CI.
- Old `--try` is rejected with an explanation.
- Diagnostic command transcript contains no partition write.
- Unknown identity always stops.
- No persistent install can occur while release state is below `LAB_INSTALL`.

# 9. Phase P2 — True zero-write diagnostic boot image

## Goal

Create a minimal RAM-resident boot image for first hardware contact. It must not require or modify userdata.

## Design requirements

The image must:

- Use the hotdog vendor kernel and appropriate DTB data.
- Contain its complete diagnostic userspace inside the initramfs.
- Mount only `proc`, `sysfs`, `devtmpfs`, `devpts`, and `tmpfs`.
- Never mount userdata, super, vendor, odm, persist, modem, or other storage read-write.
- Not run systemd, Phosh, LXC, Halium bridges, modem services, camera services, fingerprint services, charging-control scripts, or the pop-up camera helper.
- Keep HID/keyboard support available in the diagnostic kernel unless it conflicts with boot.
- Disable automatic suspend.
- Expose kernel logs over an audited USB path when technically possible.
- Show an obvious diagnostic status screen when display works.
- Record no secrets.

## Suggested files

```text
diagnostic/README.md
diagnostic/init
diagnostic/bin/ucrom-diag
diagnostic/etc/diagnostic.json
diagnostic/ui/
scripts/build-diagnostic-image.sh
socs/common/diagnostic.config
tests/test_diagnostic_image.py
```

## Diagnostic kernel configuration

Inspect the actual kernel config. Do not assume options exist.

Prefer to enable, where supported:

```text
CONFIG_DEVTMPFS
CONFIG_DEVTMPFS_MOUNT
CONFIG_TMPFS
CONFIG_PROC_FS
CONFIG_SYSFS
CONFIG_USB_GADGET
CONFIG_USB_CONFIGFS
CONFIG_USB_CONFIGFS_ACM
CONFIG_USB_F_ACM
CONFIG_USB_LIBCOMPOSITE
CONFIG_U_SERIAL
CONFIG_PSTORE
CONFIG_PSTORE_RAM
CONFIG_PSTORE_CONSOLE
CONFIG_PSTORE_PMSG
```

Do not weaken the eventual release configuration globally. Apply these through a diagnostic-only fragment.

## Diagnostic init sequence

The init script should:

1. Mount basic pseudo-filesystems.
2. Set a conservative PATH.
3. Start continuous `dmesg` capture into tmpfs.
4. Attempt the reviewed USB ACM/serial setup.
5. Detect display and touch input nodes without writing vendor controls.
6. Launch a simple status tool.
7. Print:
   - kernel release
   - device tree model
   - detected framebuffer/DRM nodes
   - detected touchscreen nodes
   - battery read-only values
   - thermal-zone read-only values
8. Wait indefinitely.
9. Provide a power-button-safe reboot path if available.
10. Never call `resize2fs`, `fsck -y`, `mkfs`, `dd` to a block device, `mount` on userdata, or any fastboot command.

## Display strategy

Do not make the diagnostic gate depend exclusively on GPU acceleration.

Use progressive display tests:

1. Existing bootloader framebuffer/simpledrm if available.
2. DRM/KMS dumb buffer if the kernel exposes it.
3. A minimal static status pattern.
4. Phosh or hwcomposer only in a later diagnostic tier.

If display does not work, the USB log path remains the primary evidence channel.

## Touch strategy

Read events without calibrating or writing configuration:

- Identify touchscreen candidate by device properties.
- Log touch coordinates and pressure.
- Draw touch points only if the display path works.
- Do not inhibit keyboards or mice in this build.

## Image assembly

Add a dedicated make target:

```text
make diagnostic DEVICE=oneplus-hotdog
```

Output:

```text
out/devices/oneplus-hotdog/diagnostic/diagnostic-boot.img
out/devices/oneplus-hotdog/diagnostic/BUILD_INFO
out/devices/oneplus-hotdog/diagnostic/SHA256SUMS
out/devices/oneplus-hotdog/diagnostic/VALIDATION.json
```

## Required validation

Unpack the image and verify:

- Correct boot image header.
- Kernel present.
- DTB present when required.
- Initramfs present.
- `/init` exists and is executable.
- No `rootfs.img`, `system.img`, or userdata image is embedded.
- No forbidden write command exists.
- No hardware-control service exists.
- Size is within the configured boot partition limit.
- Manifest marks state `DIAGNOSTIC_ONLY`, not `LAB_INSTALL`.

## Required tests

```text
test_diagnostic_initramfs_is_self_contained
test_diagnostic_initramfs_has_no_userdata_mount
test_diagnostic_initramfs_has_no_storage_formatter
test_diagnostic_initramfs_has_no_halium_container
test_diagnostic_initramfs_has_no_modem_services
test_diagnostic_initramfs_has_no_camera_motor_service
test_diagnostic_initramfs_has_no_fingerprint_service
test_diagnostic_image_size_within_limit
test_diagnostic_kernel_debug_interfaces_present
test_diagnostic_manifest_declares_zero_write_partitions
```

## Acceptance criteria

- `ucromctl diagnostic-boot` needs only `diagnostic-boot.img`.
- The release bundle contains no command requiring userdata for diagnostic use.
- Static validation proves no persistent partition write is intended.
- Release state may advance to `DIAGNOSTIC_ONLY`, but not beyond it.

# 10. Phase P3 — Halium image identity and layout correctness

## Goal

Ensure the Android driver-host image is identified, verified, named, and mounted according to its real layout.

## Problem to solve

`android-rootfs.img` and `system.img` are not interchangeable:

- `android-rootfs.img` is an Android root filesystem.
- `system.img` is an Android system partition image.

Renaming one to the other can make the initramfs mount it incorrectly.

## Files to add

```text
scripts/inspect-halium-image.py
schemas/halium-image.schema.json
tests/test_halium_image_identity.py
tests/fixtures/halium-images/
```

## Files to change

```text
scripts/fetch-halium-system.sh
scripts/build-halium-system.sh
scripts/build-device.sh
docs/BUILDING.md
docs/ARCHITECTURE.md
```

## Metadata format

Produce `out/halium-system/halium-image.json`:

```json
{
  "schema_version": 1,
  "image_kind": "android-rootfs",
  "canonical_filename": "android-rootfs.img",
  "source_server": "https://system-image.ubports.com",
  "channel": "<explicit channel>",
  "device": "halium_13_arm64",
  "version": "<source version>",
  "original_archive_path": "<path>",
  "sha256": "<sha256>",
  "signature_verified": true,
  "inspected_markers": ["/init", "/system"],
  "compatible_android_version": 13
}
```

For a system-only image, use:

```json
{
  "image_kind": "system",
  "canonical_filename": "system.img"
}
```

## Detection rules

The inspector must use multiple signals:

- Original archive path.
- Filesystem type and sparse/raw status.
- Presence of `/init`.
- Presence of `/system/build.prop`.
- Presence of root-level Android directories.
- Presence of system partition markers.

If signals conflict, return `AMBIGUOUS` and fail.

Do not choose a type based only on the filename after extraction.

## Fetching rules

- Preserve the source filename and path in metadata.
- Verify the upstream signature before extraction.
- Record the exact image version.
- Pin the selected channel/device/version in a lock file for release builds.
- Do not automatically pick “latest” during a release build.
- A maintenance command may update the lock through a reviewed commit.

## Build-device rules

When building userdata:

- If `image_kind` is `android-rootfs`, store it under the filename expected for rootfs mode.
- If `image_kind` is `system`, store it under the filename expected for system mode.
- Do not unconditionally rename either type.
- If metadata is missing, fail.
- If `signature_verified` is false, fail.
- If Android version does not match the locked Halium/vendor design, fail.
- If the image is absent, fail the hotdog release build.
- Do not claim “full hardware” when the Android driver host is absent.

## Required tests

```text
test_android_rootfs_preserves_rootfs_mode
test_system_image_preserves_system_mode
test_filename_alone_is_not_trusted
test_conflicting_markers_are_rejected
test_missing_metadata_is_fatal
test_unverified_signature_is_fatal
test_missing_halium_image_is_fatal_for_hotdog_release
test_build_places_image_under_correct_name
test_validation_records_image_kind_and_hash
```

## Acceptance criteria

- The build manifest contains an unambiguous image kind.
- The initramfs search path and packaged filename agree.
- No release candidate is produced with `halium_system=missing`.

# 11. Phase P4 — Pinned and fail-closed bridge build

## Goal

Make hardware bridge availability deterministic and mandatory.

## Files to add

```text
packages/bridges.lock.json
schemas/bridges-lock.schema.json
scripts/verify-bridges.py
tests/test_bridge_release_gate.py
```

## Lock format

Replace branch-only release inputs with entries such as:

```json
{
  "schema_version": 1,
  "bridges": [
    {
      "name": "libgbinder",
      "repository": "https://github.com/droidian/libgbinder",
      "commit": "<full immutable commit sha>",
      "required": true,
      "expected_debian_packages": ["libgbinder1", "libgbinder-dev"],
      "expected_runtime_files": ["/usr/lib/aarch64-linux-gnu/libgbinder.so.1"]
    }
  ]
}
```

The existing human-readable list can be generated from the lock file, but the lock file is authoritative for release builds.

## Build behaviour

Modify `scripts/build-bridges.sh` so that:

- It checks out the exact commit, not a moving branch.
- It records the resolved commit and source tree state.
- It applies only repository-tracked patches.
- It fails immediately or returns non-zero when a required bridge fails.
- Optional components, if any, are explicitly marked optional.
- It writes structured JSON status, not only TSV.
- It verifies produced package names.
- It verifies package architecture is arm64.
- It verifies expected binaries and libraries after installation.
- It rejects uncommitted source modifications in fetched trees.
- It never reports overall success when `fails > 0`.

End behaviour must be equivalent to:

```bash
if (( fails > 0 )); then
    die "$fails required bridge package(s) failed"
fi
```

## Root filesystem gate

The Halium rootfs build must:

- Read required package names from the lock.
- Install all required packages.
- Run `dpkg -s` for each expected package.
- Run `ldd` on required executables.
- Fail on any `not found`.
- Record service unit presence.
- Record versions.

## Build isolation

Bridge packages execute third-party build scripts. Build them inside a disposable VM or container/chroot with:

- No mounted home directory.
- No SSH agent.
- No cloud credentials.
- No host Docker socket.
- Network access only where needed.
- A clean output directory.

## Required tests

```text
test_required_bridge_failure_returns_nonzero
test_optional_bridge_failure_is_explicit
test_every_bridge_has_full_commit_sha
test_branch_only_lock_is_rejected
test_expected_packages_are_produced
test_wrong_architecture_is_rejected
test_rootfs_contains_all_required_packages
test_required_executables_link_without_missing_libraries
test_status_json_matches_lock
```

## Acceptance criteria

- Every required bridge is pinned and built.
- Missing telephony, display, audio, camera, Bluetooth, fingerprint, or container bridges block release.
- Build status cannot be green when any required bridge is red.

# 12. Phase P5 — Reproducible device build and signed manifest

## Goal

Create a verifiable relationship between source inputs, tests, and flashable outputs.

## Files to add

```text
config/source-lock.json
scripts/generate-build-manifest.py
scripts/verify-build-manifest.py
schemas/build-manifest.schema.json
docs/REPRODUCIBLE_BUILDS.md
tests/test_build_manifest.py
```

## Source lock requirements

Record:

- UCROM repository commit.
- Kernel repository and exact commit.
- Halium Android image hash and version.
- Every bridge repository and commit.
- Initramfs-tools-halium commit.
- Toolchain versions.
- Ubuntu suite and package snapshot strategy.
- Node package version and hash.
- Patches and their hashes.
- Build profile.

Avoid mutable `latest` selection during release builds.

## Build manifest example

```json
{
  "schema_version": 1,
  "project": "ucrom",
  "release_state": "BUILD_VERIFIED",
  "device_profile": "oneplus-hotdog",
  "allowed_models": ["HD1910", "HD1911", "HD1913"],
  "forbidden_models": ["HD1925"],
  "repo_commit": "5b42d790b062c3a268f6b9117eaaa4d756ad718f",
  "build_profile": "lab",
  "images": {
    "diagnostic_boot": {
      "path": "images/diagnostic-boot.img",
      "sha256": "<hash>",
      "size": 0,
      "write_partitions": []
    },
    "boot": {
      "path": "images/boot.img",
      "sha256": "<hash>",
      "size": 0,
      "intended_partition": "boot"
    },
    "dtbo": {
      "path": "images/dtbo.img",
      "sha256": "<hash>",
      "size": 0,
      "intended_partition": "dtbo"
    },
    "userdata": {
      "path": "images/userdata.img",
      "sha256": "<hash>",
      "size": 0,
      "intended_partition": "userdata",
      "destructive": true
    }
  },
  "tests": {
    "critical_skips": 0,
    "failures": 0
  },
  "real_device_evidence": false
}
```

## Build-time validation

Fail if:

- Any expected image exceeds the configured partition limit.
- DTB or DTBO is empty.
- Boot image cannot be unpacked.
- Initramfs is missing required files.
- Userdata filesystem fails read-only fsck.
- Halium image metadata is absent.
- Required bridges are absent.
- Kernel fragments have unresolved required mismatches.
- Build contains a tracked fixed PIN.
- Manifest hash does not match outputs.
- Release state is higher than available evidence.
- The build date or random data makes the manifest internally inconsistent.

## Reproducibility target

Bit-for-bit reproducibility may require further timestamp normalization. At minimum:

- Set and record `SOURCE_DATE_EPOCH`.
- Avoid embedding current wall-clock time where unnecessary.
- Sort file lists deterministically.
- Normalize ownership and permissions.
- Record package versions.
- Make repeated builds explain any hash difference.

Create a `reproducibility-report.json` comparing two clean builds.

## Signing

Use one reviewed signing mechanism. Acceptable initial approach:

- Offline signing key controlled by the maintainer.
- Sign `manifest.json`, not individual ad hoc files.
- Installer verifies signature before any install command.

Do not put private signing keys in GitHub Actions secrets for early development unless the threat model and rotation procedure are documented.

## Acceptance criteria

- Bundle verification is independent of the build environment.
- Every image is tied to source and test metadata.
- Release state is no higher than `BUILD_VERIFIED`.
- Any file modification after packaging is detected.

# 13. Phase P6 — Release CI with no critical skips

## Goal

Make CI prove that a complete hotdog candidate was built and tested, not merely that lightweight checks passed.

## Workflow structure

Create separate workflows:

```text
.github/workflows/quick.yml
.github/workflows/qemu-integration.yml
.github/workflows/hotdog-release-candidate.yml
```

## Quick workflow

Runs:

- ShellCheck.
- Python compile.
- Unit tests using fake tools.
- JSON schema validation.
- Device profile validation.
- No large build.

## QEMU integration workflow

Runs:

- Mainline rootfs build.
- QEMU image.
- Touch UI tests.
- Application tests.
- Report generation.

It must remain clearly labelled emulator evidence.

## Hotdog release-candidate workflow

Runs manually or on a reviewed release tag. It must:

1. Check out exact source.
2. Load locked dependencies.
3. Build every required bridge.
4. Build Halium rootfs.
5. Build hotdog kernel.
6. Build diagnostic image.
7. Build boot, DTBO, and userdata images with the locked Halium image.
8. Run all hotdog artifact tests.
9. Run bridge installation/linker tests.
10. Generate test JUnit output.
11. Fail on critical skips.
12. Generate source lock and manifest.
13. Package the release bundle.
14. Upload logs, metadata, and test reports.
15. Keep release state at `BUILD_VERIFIED` until physical evidence exists.

If GitHub-hosted capacity is insufficient, use an isolated self-hosted runner. Do not silently remove tests to fit hosted limits.

## Critical skip policy

Mark safety and device-release tests:

```python
@pytest.mark.release_critical
```

Add a plugin or post-processing step that fails if any `release_critical` test is skipped.

Examples:

- hotdog kernel config
- boot image structure
- DTBO structure
- Halium image included
- all required bridges built
- all required bridge binaries linked
- manifest complete
- diagnostic zero-write validation

## Required artifacts

```text
test-report/
junit.xml
bridge-status.json
source-lock.json
build-manifest.json
reproducibility-report.json
release-bundle.tar.zst
```

## Acceptance criteria

- A green release-candidate workflow means all required device artifacts were actually built.
- The workflow cannot be green with missing bridge status or absent Halium image.
- Critical skipped count is zero.
- The bundle passes `ucromctl verify-bundle` on a separate job.

# 14. Phase P7 — Debug/release profiles and hardware feature gates

## Goal

Prevent the first physical boot from automatically exercising dangerous or unverified hardware.

## Profiles

Create explicit profiles:

```text
diagnostic
debug
lab
release
```

### Diagnostic

- RAM only.
- No storage writes.
- No Halium container.
- No modem.
- No camera.
- No fingerprint.
- No pop-up motor.
- Debug input allowed.
- USB logging enabled.

### Debug

- Persistent rootfs permitted only after G9.
- Halium may run.
- Dangerous hardware features disabled.
- USB logging enabled.
- SSH over Wi-Fi disabled.
- Optional USB-only debug shell with documented authentication.

### Lab

- Hardware enabled selectively through flags.
- Full logging.
- Not for personal data.
- Not for primary SIM.

### Release

- Debug access removed or tightly controlled.
- Touch-only policy may be enabled.
- Security and update requirements enforced.

## Feature flags

Add a file such as:

```text
config/features/oneplus-hotdog.json
```

Initial state:

```json
{
  "display": false,
  "touch": false,
  "storage": false,
  "thermal_monitoring": true,
  "charging_basic": false,
  "charging_fast": false,
  "wifi": false,
  "audio": false,
  "suspend": false,
  "sensors": false,
  "camera_rear": false,
  "camera_front": false,
  "popup_camera_motor": false,
  "fingerprint": false,
  "bluetooth": false,
  "nfc": false,
  "modem": false,
  "calls": false,
  "sms": false,
  "mobile_data": false,
  "volte": false
}
```

A feature may become true only after evidence is attached.

## Files to change

```text
rootfs/hooks/1-60-ucrom-daemons.chroot
rootfs/hooks/1-70-session.chroot
rootfs/hooks/1-30-touch-only.chroot
ucrom/systemd/system/*
ucrom/systemd/user/*
config/ucrom.conf
scripts/build-rootfs.sh
```

## Service gating

Do not globally enable:

- `ucrom-popup-camera.service`
- `ucrom-fod.service`
- modem/telephony services
- camera services
- refresh-rate write service
- any fast-charging control
- automatic suspend

Instead, generate enablement from the selected profile and feature file.

## Pop-up camera safety redesign

Before enabling the motor:

- Verify actual sysfs semantics on the exact kernel.
- Read position before every action.
- Refuse movement when position is unknown.
- Add movement timeout.
- Add rate limiting.
- Add maximum movement count per minute.
- Log every write.
- Always attempt safe retract on controlled shutdown.
- Do not enable free-fall automation until accelerometer units and sampling are validated.
- Replace the world-writable file signal with a permissioned D-Bus interface or protected runtime socket.
- Provide a manual lab command requiring explicit confirmation.

Example interface:

```text
ucrom-hwctl popup-camera status
ucrom-hwctl popup-camera move-up --lab-confirm
ucrom-hwctl popup-camera retract --lab-confirm
```

No camera application should directly write motor sysfs.

## Fingerprint safety

- Keep disabled until display brightness/dim-layer behaviour is observed.
- Do not assume D-Bus API compatibility.
- Add timeouts for all calls.
- Ensure the bright sensor overlay cannot remain stuck.
- Restore the dim-layer state on crash and service stop.
- Do not describe fingerprint as secure authentication until failure and spoof behaviour are assessed.

## Touch-only policy

The touch-only policy must not apply to diagnostic or debug profiles.

Revise documentation to state:

- Debug builds intentionally preserve rescue input.
- Touch-only is a product policy, not an early-port safety feature.
- Relocking the bootloader is not part of touch-only implementation.

## Acceptance criteria

- First persistent debug boot starts no dangerous helper.
- Feature flags are visible in the build manifest.
- Tests prove disabled features do not start.
- Diagnostic/debug builds retain recovery input paths.

# 15. Phase P8 — Exact-device recovery readiness

## Goal

Ensure the human operator has a verified way back before the first physical boot.

## Required device identity

The operator must establish the exact model printed in hardware/settings/packaging. “McLaren Edition” is insufficient.

Initial profile policy:

- HD1910: audit required but included in current profile.
- HD1911: audit required but included in current profile.
- HD1913: audit required but included in current profile.
- HD1925: stop; this is hotdogg, not hotdog.
- Any other model: stop.

## Recovery kit

The operator must locally possess:

- Exact-model stock recovery/EDL package from a trusted source.
- Qualcomm/OnePlus drivers required by the recovery method.
- A Windows machine capable of running the exact recovery tool.
- Pinned Android Platform Tools.
- Known-good LineageOS/Android install package.
- Known-good recovery image.
- Known-good boot and DTBO files for the current baseline.
- USB cable known to support data.
- Full backup of personal data.
- Printed or offline recovery steps.

Do not redistribute proprietary recovery packages in the UCROM repository.

## Recovery validation

Before UCROM diagnostic boot:

- Confirm the device enters bootloader mode.
- Confirm the flashing host sees the exact serial.
- Confirm a known-good recovery image is available.
- Record active slot.
- Record bootloader unlocked state.
- Record the current Android build fingerprint.
- Confirm the recovery package exactly matches the device model.
- Confirm no critical account depends exclusively on the phone.
- Remove SIM and sensitive data.

The safest recovery test does not intentionally brick the device. It verifies tools, files, drivers, identity, and access paths without writing unnecessary partitions.

## Partition protection policy

The UCROM controller must permanently reject writes to at least:

```text
xbl
xbl_config
abl
aop
devcfg
hyp
tz
keymaster
cmnlib
cmnlib64
modem
bluetooth
persist
modemst1
modemst2
fsg
fsc
frp
devinfo
super
vendor
odm
```

This list is conservative and not necessarily exhaustive. The controller should allow only the positive allowlist, never rely only on a denylist.

Initially permitted only after G9:

```text
boot
dtbo
userdata
```

`vbmeta` is not permitted unless a separate AVB design is reviewed.

## Recovery readiness record

Create:

```text
recovery-readiness.json
```

It must include:

- exact model
- redacted serial hash
- current slot
- stock recovery package hash
- Lineage package hash
- recovery image hash
- platform-tools version
- backup confirmation
- SIM removed
- sensitive data removed
- operator acknowledgement
- timestamp

## Acceptance criteria

- G8 record validates.
- Model is exact.
- No wrong-model fallback exists.
- Recovery kit is offline and accessible.

# 16. Phase P9 — First real-device diagnostic boot

## Goal

Boot the RAM-only diagnostic image without modifying any persistent partition.

## Human-only prerequisite

This phase requires a human physically present with the device and recovery host. An AI must not claim to have completed it without human-supplied evidence.

## Environmental setup

- Test device only.
- SIM removed.
- No personal accounts or sensitive files.
- Battery charged before entering bootloader.
- Do not begin with fast charging.
- Device placed on a non-insulating surface.
- Recovery host connected to reliable power.
- Command transcript recording enabled.
- Only one fastboot device connected.

## Procedure

1. Run `ucromctl verify-bundle`.
2. Run `ucromctl capture-device` while Android is booted.
3. Reboot manually or through the controller into bootloader.
4. Run `ucromctl diagnostic-boot`.
5. Confirm the transcript includes no write command.
6. Observe:
   - screen
   - touch
   - buttons
   - USB diagnostic channel
   - boot stability
   - battery and thermal readings
7. Collect logs.
8. Reboot back to the previous operating system.
9. Confirm previous system still starts and userdata remains intact.

## Conservative stop conditions

Stop immediately if:

- Any command attempts a partition write.
- Device identity differs from the preflight file.
- The product is unknown.
- Fastboot reports userspace fastbootd unexpectedly.
- Battery or thermal readings rise rapidly or exceed the conservative laboratory threshold chosen by the human operator.
- The pop-up camera moves.
- The phone repeatedly resets.
- USB connection becomes unstable during command execution.
- The previous operating system does not return after reboot.

Do not continue to persistent installation merely because the screen displayed something.

## Required evidence

- Full command transcript.
- Hash of diagnostic image.
- Device preflight.
- Photo or operator note of display result.
- Touch event log.
- Dmesg.
- Thermal readings over time.
- Confirmation that old OS and data returned.
- Explicit note of every non-working component.

## Acceptance criteria

At minimum:

- Zero partition writes.
- Kernel reached diagnostic init.
- At least one reliable log extraction path.
- No unexpected hardware action.
- Previous OS returned.
- Failures are understood or documented.

Only then may release state become `DIAGNOSTIC_BOOT_VERIFIED`.

# 17. Phase P10 — Controlled laboratory installation

## Goal

Perform the first persistent UCROM installation with a reversible, auditable process.

## Preconditions

- G9 passed on the exact device.
- Full release candidate built from locked inputs.
- Recovery readiness still valid.
- Dangerous services disabled.
- Installer state is `LAB_INSTALL`.
- Operator has reviewed the exact install plan.

## Slot-aware design

The controller must query:

- current slot
- whether boot is slotted
- whether DTBO is slotted
- slot success state when supported
- partition sizes

Do not assume A/B behaviour solely from a device profile.

Preferred strategy, only if verified compatible:

1. Preserve the currently bootable slot.
2. Write boot/DTBO to the inactive slot.
3. Do not switch slots yet.
4. Write userdata only after boot images were accepted.
5. Switch slot only as a final explicit action.
6. Default to remaining in bootloader after writes.
7. Require explicit `--reboot` to reboot.

If vendor/odm/firmware compatibility on the inactive slot is not proven, stop and resolve that issue rather than guessing.

## Write order reasoning

The AI must document the selected write order and its failure modes. It must not copy the old script blindly.

Consider:

- Writing inactive boot/DTBO first avoids damaging the active boot path.
- Writing userdata is destructive regardless of slot.
- Switching the slot should happen only after required writes succeed.
- A failed userdata write should not leave the device automatically booting a new kernel.
- A failed boot/DTBO write must not trigger userdata destruction.

## Confirmation

Require a phrase that includes:

```text
INSTALL UCROM <bundle-short-hash> ON <serial> MODEL <model> AND WIPE USERDATA
```

Do not accept only `ERASE`.

## Post-write behaviour

- Do not automatically reboot by default.
- Print written partitions and hashes.
- Print the selected slot.
- Print rollback instructions.
- Save transcript.
- Require a separate explicit reboot command.

## First persistent boot

Start in debug profile:

- USB logging on.
- Touch-only policy off.
- Motor off.
- Fingerprint off.
- Modem off.
- Fast charging off.
- Suspend off.
- Display refresh fixed conservatively.
- No primary SIM.

## Acceptance criteria

- Only positive-allowlist partitions were written.
- Transcript and manifest agree.
- Device can still enter bootloader and recovery.
- UCROM reaches debug target or produces actionable logs.
- Rollback procedure remains available.
- No uncontrolled hardware action occurs.

# 18. Phase P11 — Subsystem-by-subsystem hardware bring-up

## Goal

Enable and validate hardware in an order that minimizes ambiguity and physical risk.

## General rule

Only one major subsystem may move from disabled to enabled in a test iteration. Every iteration must have:

- source commit
- bundle hash
- feature flag diff
- test protocol
- logs
- result
- rollback
- updated hardware matrix

## Stage H1 — Boot, display, touch, buttons

Validate:

- repeated boots
- screen resolution and orientation
- touchscreen coordinate mapping
- power/volume buttons
- no ghost touches
- refresh rate initially fixed at 60 Hz
- USB logging
- storage read/write only within the UCROM filesystem

Do not enable 90 Hz until display stability is proven.

## Stage H2 — Thermal and basic charging

Validate read-only telemetry first:

- battery percentage
- battery temperature
- current and voltage reporting
- relevant thermal zones
- charger connect/disconnect
- low-current USB charging

Rules:

- Do not write undocumented charging sysfs nodes.
- Do not enable fast charging initially.
- Do not leave the phone charging unattended.
- Compare readings with the stock/Lineage baseline.
- Abort on abnormal temperature rise, current reporting, or repeated power resets.

## Stage H3 — Wi-Fi

Validate:

- scanning
- connection
- DHCP
- DNS
- reconnect
- sleep/wake behaviour
- MAC handling
- no credential leakage in logs

## Stage H4 — Audio

Validate separately:

- speaker
- earpiece
- microphones
- wired headset if supported
- volume controls
- no dangerously loud initial gain
- no audio service crash loops

Start at low volume.

## Stage H5 — Suspend and resume

Validate:

- screen off/on
- USB reconnect
- Wi-Fi reconnect
- no wake lock loops
- no rapid battery drain
- no touch loss
- no storage corruption

Do not enable aggressive suspend until logs remain accessible.

## Stage H6 — Sensors and vibration

Validate units and orientation for:

- accelerometer
- gyroscope
- compass
- proximity
- light
- vibration

The pop-up camera free-fall feature must remain off until accelerometer magnitude and units are proven.

## Stage H7 — Rear camera

Validate the rear camera before the front motor:

- service discovery
- preview
- capture
- orientation
- camera release
- repeated open/close
- no driver crashes

## Stage H8 — Front camera without automatic motor

Use manual, supervised motor control only after the rear camera path works.

Validate:

- motor sysfs presence
- position semantics
- direction semantics
- timeout
- manual up
- camera preview
- manual retract
- recovery after app crash

Do not enable automatic motor movement yet.

## Stage H9 — Pop-up motor automation

Enable only after:

- manual motor tests pass
- accelerometer units pass
- service crash cleanup is proven
- rate limit is proven
- emergency retract works
- front camera activity detection is reliable

Run a limited number of cycles. Record count.

## Stage H10 — Fingerprint

Validate:

- service availability
- enrollment
- scan timeouts
- overlay positioning
- dim-layer cleanup
- lock-screen integration
- failure behaviour
- reboot behaviour

Do not treat fingerprint as the sole unlock method.

## Stage H11 — Bluetooth and NFC

Bluetooth:

- controller power
- scanning
- audio
- reconnect
- no HID policy side effects in debug

NFC:

- controller detection
- safe read test
- service stability

## Stage H12 — Modem without SIM

Validate:

- modem service startup
- baseband visibility
- no crash loop
- IMEI is never printed into public logs
- radio partitions are untouched

## Stage H13 — Secondary test SIM

Use a non-primary test SIM.

Validate:

- SIM detection
- network registration
- SMS
- mobile data
- incoming/outgoing call
- microphone/earpiece during call
- airplane mode
- reboot recovery
- carrier-specific behaviour

Do not place test calls to emergency services. Follow local approved procedures if emergency-call testing is ever required.

## Stage H14 — VoLTE and carrier-specific functions

Treat VoLTE as a separate feature. Record:

- carrier
- region
- IMS registration
- call fallback
- data during call
- reboot persistence

Do not claim universal VoLTE support from one carrier result.

## Hardware matrix schema

```json
{
  "schema_version": 1,
  "device_model": "HD1911",
  "bundle_hash": "<hash>",
  "features": {
    "display": {
      "status": "PASS",
      "evidence": ["dmesg.txt", "operator-observations.md"],
      "tested_on_real_device": true
    },
    "popup_camera_motor": {
      "status": "NOT_TESTED",
      "tested_on_real_device": false
    }
  }
}
```

Allowed statuses:

```text
NOT_TESTED
BLOCKED
PARTIAL
PASS
FAIL
REGRESSION
```

## Soak testing

Before `HARDWARE_BETA`:

- repeated cold boots
- repeated warm reboots
- suspend/resume cycles
- Wi-Fi reconnect cycles
- charging/discharging observation
- storage integrity checks
- camera cycles
- call/SMS/data cycles with test SIM
- no unexplained kernel panic
- no unexplained reboot
- no filesystem corruption

Record duration and counts instead of saying “tested extensively.”

# 19. Phase P12 — Security, updates, encryption, and daily-driver qualification

## Goal

Address risks that are acceptable on a sacrificial lab device but unacceptable on a primary phone.

## 19.1 Credentials

Remove the tracked PIN from `config/ucrom.conf`.

Requirements:

- No public default PIN.
- No password stored in the repository.
- Debug builds may accept a test credential only through an untracked build secret and must mark the bundle insecure.
- Release builds require a first-boot local credential setup.
- Root password remains locked.
- Normal phone user should not be in `sudo` by default.
- Administrative operations should use a designed privilege mechanism rather than making the phone PIN a sudo password.

Add tests that scan tracked source and built images for known default credentials.

## 19.2 Encryption

A daily-driver candidate requires an encrypted-data design.

Possible architectures to evaluate:

1. LUKS2-encrypted root/data image unlocked during early boot.
2. Minimal unencrypted system plus encrypted user data/home.
3. Hardware-backed or secure-element-assisted key storage if practically supported.

The implementing AI must not choose an architecture without documenting:

- boot flow
- PIN/key derivation
- recovery-key handling
- lost-key behaviour
- update compatibility
- crash recovery
- performance
- what remains unencrypted
- threat model with unlocked bootloader

Do not claim complete physical security while the bootloader is unlocked.

## 19.3 Network exposure

Audit:

- listening sockets
- USB debug interfaces
- SSH
- mDNS
- development servers
- AI agent tools
- App Hub installers
- browser and Flatpak permissions

Release profile should default to no remotely reachable administrative service.

## 19.4 Application installation security

App Hub installers must:

- download from explicit official sources
- pin versions or verify signatures/checksums
- avoid `curl | sh`
- display permissions and source
- use non-root installation where possible
- log installed version
- support uninstall
- never embed API keys

## 19.5 Mandatory access controls

Evaluate and implement:

- AppArmor profiles
- systemd sandboxing
- `NoNewPrivileges`
- `ProtectSystem`
- `ProtectHome`
- `PrivateTmp`
- device allowlists
- restricted capabilities
- seccomp where practical

Hardware helpers should have only the devices and sysfs paths they need.

## 19.6 Signed updates

Design an update system with:

- signed metadata
- image hashes
- rollback to previous known-good version
- interrupted-update recovery
- channel separation
- version monotonicity
- release notes
- minimum compatible firmware/vendor baseline

Do not implement automatic update until rollback is proven.

## 19.7 Bootloader and verified boot

Keep the bootloader unlocked during development.

A future relock design requires:

- custom AVB key strategy
- every verified partition mapped
- rollback indexes
- recovery key storage
- exact-device testing
- proven unlock/recovery behaviour

This is a separate project gate. Never tell the user to relock based only on a generated key and a signed boot image.

## 19.8 Primary SIM and personal data gate

Do not recommend primary SIM or personal data until:

- hardware matrix passes
- modem is stable
- suspend is stable
- charging is stable
- encryption is implemented
- update signing exists
- recovery is proven
- no default credentials remain
- no uncontrolled debug service is exposed
- multi-day soak results are recorded

# 20. Phase P13 — Release documentation and maintenance

## Goal

Make future builds and tests repeatable by someone other than the original author.

## Required documents

```text
docs/INSTALL.md
docs/RECOVERY.md
docs/BUILD.md
docs/DEVICE_IDENTITY.md
docs/DIAGNOSTIC_BOOT.md
docs/LAB_TEST_PROTOCOL.md
docs/HARDWARE_MATRIX.md
docs/SECURITY_MODEL.md
docs/UPDATE_MODEL.md
docs/KNOWN_LIMITATIONS.md
docs/RELEASE_CHECKLIST.md
```

## Documentation rules

- Every destructive step must be labelled.
- Diagnostic boot and persistent install must never be mixed.
- Use exact model codes.
- Clearly distinguish hotdog from hotdogg.
- State the tested carrier and region for telephony claims.
- State the exact bundle hash for test reports.
- Do not use “all hardware works” when the matrix contains `PARTIAL` or `NOT_TESTED`.
- Keep rollback instructions offline-capable.
- Include screenshots only as supporting evidence, not proof of unseen subsystems.

# 21. Suggested pull-request sequence

Do not implement everything in one PR.

## PR 1 — Documentation and release state

- P0 only.
- No behaviour changes.

## PR 2 — `ucromctl` verification and diagnostic command

- P1.
- Old `--try` disabled.
- Fake tools and safety tests.

## PR 3 — RAM diagnostic image

- P2.
- No persistent install.

## PR 4 — Halium image semantics

- P3.
- Fixtures and metadata.

## PR 5 — Bridge locks and fail-closed build

- P4.

## PR 6 — Build manifest and source locks

- P5.

## PR 7 — Release CI

- P6.

## PR 8 — Profiles and hardware gates

- P7.

## PR 9 — Recovery documentation and readiness schema

- P8.

## PR 10 — Changes based on first diagnostic evidence

- P9 results only.
- No claims beyond evidence.

## PR 11 onward — One subsystem per PR

- P10/P11.
- Each PR contains test evidence.

## Final security PRs

- P12/P13.
- Credentials, encryption, update system, sandboxing, documentation.

# 22. Required test inventory

The final repository should include at least these categories:

```text
tests/unit/test_fastboot_parser.py
tests/unit/test_adb_parser.py
tests/unit/test_device_identity.py
tests/unit/test_bundle_manifest.py
tests/unit/test_partition_policy.py
tests/unit/test_halium_image_identity.py
tests/unit/test_bridge_lock.py
tests/unit/test_release_state.py
tests/integration/test_ucromctl_fake_device.py
tests/integration/test_diagnostic_image.py
tests/integration/test_hotdog_bundle.py
tests/release/test_no_default_credentials.py
tests/release/test_no_critical_skips.py
tests/release/test_required_bridges.py
tests/release/test_partition_allowlist.py
tests/release/test_manifest_matches_artifacts.py
```

# 23. Mandatory negative tests

Safety systems are incomplete without proving refusal behaviour.

The following failures must be tested:

- Wrong model.
- HD1925 connected to hotdog bundle.
- Unknown model.
- Multiple devices.
- No device.
- Locked bootloader.
- Fastbootd rather than bootloader.
- Missing current slot.
- Unsupported `fastboot boot`.
- Corrupt diagnostic image.
- Corrupt manifest.
- Wrong image hash.
- Missing signature.
- Expired or revoked signing key when revocation is implemented.
- Oversized boot image.
- Oversized DTBO.
- Missing Halium image.
- Ambiguous Halium image.
- Required bridge failed.
- Required test skipped.
- Recovery record missing.
- User cancels confirmation.
- Transcript cannot be written.
- Bundle is on a read-only or partially copied path.
- Unexpected partition name.
- Attempt to pass a raw partition name from the CLI.
- Attempt to use old `--try`.
- Attempt to install while state is `UNSAFE`, `BUILD_VERIFIED`, or `DIAGNOSTIC_ONLY`.

# 24. Safe coding patterns

## 24.1 Subprocess execution

Use argument arrays, never shell-concatenated commands.

Good:

```python
subprocess.run(
    [fastboot_path, "-s", serial, "getvar", "product"],
    text=True,
    capture_output=True,
    check=False,
)
```

Bad:

```python
os.system(f"fastboot -s {serial} flash {partition} {image}")
```

## 24.2 Partition allowlist

Good:

```python
allowed = manifest["partition_policy"]["lab_install"]
if requested_partition not in allowed:
    raise SafetyError("Partition is not in the signed allowlist")
```

Do not let the user expand the allowlist with a command-line flag.

## 24.3 Image verification

Verify immediately before use, not only at bundle extraction.

```python
actual = sha256_file(image_path)
expected = manifest["images"]["boot"]["sha256"]
if actual != expected:
    raise IntegrityError("boot.img checksum mismatch")
```

## 24.4 No fallback

```python
result = run_fastboot(["boot", diagnostic_image])
if result.returncode != 0:
    raise DiagnosticBootError(
        "fastboot boot failed; no partition was written and no fallback will be attempted"
    )
```

Never follow it with `flash boot`.

# 25. Human decision points that AI cannot replace

The AI may prepare code and checklists, but a human must decide:

- The exact physical model code.
- Whether the recovery package matches the device.
- Whether the phone is sacrificial/test-only.
- Whether data backup is complete.
- Whether observed heat is abnormal.
- Whether a motor sound or movement is unsafe.
- Whether to proceed after any unexplained failure.
- Whether a carrier/SIM test is legally and practically appropriate.
- Whether security limitations are acceptable for personal use.

# 26. Final go/no-go checklists

## 26.1 Before first diagnostic boot

```text
[ ] Exact model captured
[ ] HD1925/hotdogg excluded
[ ] Diagnostic image built
[ ] Diagnostic image verified
[ ] No-write tests pass
[ ] ucromctl tests pass on the flashing host OS
[ ] Recovery kit ready
[ ] Personal data backed up
[ ] SIM removed
[ ] Only one fastboot device connected
[ ] Bundle hash recorded
[ ] Command transcript enabled
```

## 26.2 Before first persistent install

```text
[ ] Diagnostic boot succeeded on this exact device
[ ] Previous OS returned after diagnostic boot
[ ] Full hotdog release CI is green
[ ] Zero critical skips
[ ] Halium image type verified
[ ] Every required bridge built
[ ] Build manifest verified
[ ] Dangerous hardware services disabled
[ ] Recovery readiness record valid
[ ] Exact install plan reviewed
[ ] Only boot/dtbo/userdata are allowed
[ ] Slot plan reviewed
[ ] Userdata destruction explicitly accepted
[ ] No primary SIM or sensitive data
```

## 26.3 Before calling it a daily-driver candidate

```text
[ ] Full hardware matrix completed
[ ] Thermal behaviour stable
[ ] Basic and fast charging validated
[ ] Suspend/resume stable
[ ] Storage integrity stable
[ ] Modem stable with test SIM
[ ] Calls/SMS/data tested
[ ] Carrier and VoLTE limitations documented
[ ] Camera motor safety passed
[ ] Fingerprint failure handling passed
[ ] No default credentials
[ ] Normal user not unrestricted sudo
[ ] Encryption implemented and tested
[ ] Signed updates implemented
[ ] Rollback tested
[ ] Network exposure audited
[ ] Soak test evidence recorded
[ ] Recovery tested after a failed candidate
```

# 27. Completion rule

This plan is complete only when the repository can answer all of these questions with machine-verifiable evidence:

1. What exact device models may use this bundle?
2. What exact source commits produced it?
3. What exact images will be used?
4. What partitions, if any, will be written?
5. Can diagnostic boot occur without writing a partition?
6. What happens when identity or integrity checks fail?
7. Are all required Halium bridges present?
8. Is the Android driver-host image mounted according to its true layout?
9. Did the full hotdog candidate build in CI?
10. Were any release-critical tests skipped?
11. What has actually been tested on a real device?
12. How can the operator recover the exact model?
13. Which dangerous hardware features remain disabled?
14. What security limitations remain?
15. What evidence permits the current release state?

Until the answers are complete, the correct status is not “ready to flash.” The correct status is the highest evidence-backed release state defined in this document.
