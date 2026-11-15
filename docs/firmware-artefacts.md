# Firmware artefacts

The local `firmware_v1.07.02` directory combines official updaters with
stock firmware, device backups and local recovery packages. No vendor
redistribution permission was identified. Keep the archive outside Git;
`/firmware_v1.07.02/` is also ignored if copied into the checkout again.

Obtain official firmware from [Mistel support](https://mistelkeyboard.com/support).
The updater files used for this research have these fingerprints:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `MD770R_FW_0419_7.02_20230421.exe` | 2,195,976 | `fb38e891d4e138bb768249a68660ada353c706d23aeea5b202f125ee376cd64c` |
| `MD770L_FW_041A_4.01_20230424.exe` | 2,121,516 | `a4557983f712f5baf2b9c17c895bf15582509e7a31745ef19312e80424995a0c` |

## Reproduce locally

The existing tools provide the reproducible parts of the archive:

- [`md770-extract.py`](../scripts/md770-extract.py) extracts a user-supplied updater without executing it.
- [`md770-ghidra/`](../scripts/md770-ghidra/) prepares Ghidra analysis and exports decompiled functions.
- [`md770_prepare_recovery.py`](../scripts/md770_prepare_recovery.py) assembles recovery packages from locally supplied inputs.
- [`md770_flash.py`](../scripts/md770_flash.py), [`md770_updater_check.py`](../scripts/md770_updater_check.py) and [`ht32-dfu-tool`](../tools/ht32-dfu-tool/) retain the host tooling.

The archived Python flashers match the maintained scripts byte for byte.
The final archived Holtek source matches the maintained tool source.
Older tool snapshots and QMK build snapshots remain in the private archive.
The QMK port lives in the [QMK fork](https://github.com/markwellis/qmk_firmware/tree/mistel-md770-support).

Follow the [extraction and decompilation instructions](mistel-md770-firmware.md#reproducing-the-extraction-and-decompilation).
Generated firmware images and complete vendor disassembly or decompiler
exports stay local. The [recovery procedures](left-recovery-package.md)
require the owner's verified device backups; the repository does not supply them.

## Retained research

The following original source and measurement records were copied from
the recovery packages. Source copyright and licence notices are preserved.
These are historical results from 2026-11-13, not new hardware tests or
claims about the current firmware build.

| Repository file | Archive package | Contents |
| --- | --- | --- |
| [`identify_probe.c`](../tests/md770_storage/identify_probe.c) | `qmk-right-flash-identify-20261113` | Read-only JEDEC/SFDP probe |
| [`uart_probe.c`](../tests/md770_link/uart_probe.c) | `qmk-right-link-diagnostic-20261113` | UART and GPIO diagnostic source |
| [`pb11_probe.c`](../tests/md770_link/pb11_probe.c) | `qmk-right-pb11-diagnostic-20261113` | Successful PB11 diagnostic source |
| [Flash identification](mistel-md770-flash-identification.json) | `qmk-right-flash-identify-20261113` | JEDEC/SFDP data and erase geometry |
| [Backup verification](mistel-md770-external-backup-check.json) | `qmk-right-flash-identify-20261113` | Read count, size and hash; no backup bytes |
| [Storage readback](mistel-md770-native-storage-readback.json) | `qmk-right-flash-identify-20261113` | Before/after hashes and erase guard result |
| [Updater round trip](mistel-md770-qmk-updater-roundtrip.json) | `qmk-right-storage-indicators-20261113` | Checksum and normal-return verification |
| [Clean firmware checks](mistel-md770-qmk-clean-hardware-checks.json) | `qmk-upstream-native-clean-20261113` | Both-half installation and paired typing results |

Vendor executables, stock bootloaders, reconstructed stock images, raw
storage dumps, the vendor instruction JPEG, compiled builds, runtime
archives, full console captures and the Git history bundle are excluded.
