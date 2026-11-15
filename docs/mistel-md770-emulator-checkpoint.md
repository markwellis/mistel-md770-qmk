# Resume checkpoint: Bluetooth and ARM emulator

Stopped at the owner's request on 2026-11-15. No firmware was flashed and
no PRs were opened. Continue from this checkpoint rather than restarting
the stock research or firmware implementation.

## Saved code

- `qmk_firmware`, branch `mistel-md770-support`: `3f9fb0f449061752370c3359d6a981d387fe5e7d` adds Bluetooth/charging; preceding `f066691b14` preserves Bluetooth reports on USB resume.
- `ChibiOS-Contrib`, branch `qmk-ht32-bftm-counter-width`: `a175f0d820dc125367073c30a1fb6029b419621d` widens HT32 BFTM's `gptcnt_t` to 32 bits. The owner will open the PR later.
- This repository contains the personal keymap, native tests, stock traces,
  implementation evidence and unfinished emulator source.

The existing QMK submodule pin is intentionally retained. Its working tree
has two local dependency fixes, both saved here as patches:
`patches/ht32f523xx-reset-register.patch` and
`patches/ht32f523xx-bftm-counter-width.patch`. They must be reapplied to a
fresh pinned dependency. The personal keymap README gives the setup.

## Verified state

The Bluetooth/power implementation received Astra maximum-effort software
review with no remaining P1/P2 findings. Both default and personal keymaps
build for both halves. The existing 29 driver/resume/RGB checks and 40
programming checks passed again at this checkpoint. Previous QMK protocol,
split, DIP, notification, USB and host-tool results are in
`docs/mistel-md770-bluetooth-implementation-checks.json`.

The new emulator found a real dependency defect: the compiled idle path
wrote BFTM0 CMP=30464 instead of 96000 because the HAL interval type was
16-bit. The counter-width fix matches the chip's 32-bit counter/compare
registers. Rebuilt right default and personal images now write CMP=96000;
ABI extraction reports four-byte `gptcnt_t`. Both halves were rebuilt.

Bluetooth delivery, LEDs, charging and revised sleep/wake still require
hardware validation. The battery is absent. Stock deep sleep and battery
runtime are not reproduced or established.

## Emulator progress

The prototype is **unfinished**, with no complete CLI or automated model
validation suite. Do not present it as a validated board emulator.

- `tests/md770_bluetooth/emulator.py`: Unicorn Cortex-M0 instruction
  execution, ELF loading, bounded SPI/GPIO/LVD/NVIC register model,
  instruction-boundary IRQ delivery, MSP/PSP exception frames, PRIMASK,
  priorities and EXC_RETURN. Unknown MMIO and unsupported operations fail.
- `emulator_abi.c` / `emulator_abi.py`: derive structure offsets using the
  actual firmware compiler flags; no hard-coded USB/PWM/GPT layouts.
- `emulator_firmware.py`: explicit post-initialisation QMK and stock fixtures.
  The actual QMK radio task and vector handler run, as does stock US7.02
  under the same model. Keyboard packet bytes match in manual checks.

Time, RTOS sleep/scheduling, persistent writes and empty UART input are
supplied boundaries. This is component execution, not MCU boot, a Bluetooth
stack, an analogue charger model or cycle-accurate hardware timing. FIFO
occupancies approaching the separate shift-register boundary are rejected;
error flags are injected inputs, not validated overflow timing.

## Next work

1. Finish model validation before using the emulator as evidence. Add
   independent CPU tests for register/flag preservation, aligned/misaligned
   stacks, PSP/MSP, nested priorities and deferred IRQs; add register contract
   tests against the manuals and negative/mutation tests.
2. Fix known draft limitations: GPIO input reads currently ignore INER and
   pull resistors; `Qmk.usb()` does not set USBDriver.state consistently.
   Model USB signalling or explicitly reject remote wake. Keep the bounded
   FIFO/shift-register scope explicit.
3. Add a repeatable CLI/test runner and differential stock/QMK scenarios:
   packets, status collisions, reconnect retries, final-byte/error races,
   real scan-IRQ pre-emption, LVD/LED timing and actual timer register values.
4. Have Astra review the completed emulator at maximum effort. Its current
   review identified corrections but did not sign off the draft.

The latest corrections already present include CONTROL.SPSEL handling on
exception entry/return, rejection of unaligned ARMv6-M accesses, stock stack
placement from its vector, GPIO SRR reset bits, the 3.30 V LVD selection and
rejection of recursive firmware calls from callbacks.

The relevant primary references are the
[Holtek manual](https://www.holtek.com/webapi/187531/HT32F52342_52_UserManual_v160.pdf)
(BFTM pp296–301, SPI pp459–470, GPIO pp124–137, LVD pp78–79) and
[Arm DUI0662B](https://documentation-service.arm.com/static/5f04abc8dbdee951c1cdc9f7)
(exception entry/return pp2-20–2-21). Unicorn's
[FAQ](https://github.com/unicorn-engine/unicorn/blob/master/docs/FAQ.md)
describes its exception-return interrupt8 convention.

## Reproduce the existing timer observation

Dependencies: Python with `unicorn`, `pyelftools`, `capstone`, plus
`gcc-arm-embedded`. Existing built ELF files are in the sibling QMK
checkout's `.build/`; binaries remain outside Git under the artefact policy.
The local ignored `md770-analysis/emulator-python` environment contains the
Python dependencies, but recreate them through Nix in another checkout.

Run this Python from this repository's root with those dependencies:

```python
from pathlib import Path
import sys
sys.path.insert(0, "tests/md770_bluetooth")
from emulator_abi import layout
from emulator_firmware import Qmk
qmk = Path("../qmk_firmware").resolve()
elf = qmk / ".build/mistel_md770rgb_bt_right_markwellis.elf"
abi = layout(qmk, elf)
machine = Qmk(elf.read_bytes(), abi)
machine.start()
machine.matrix()
machine.ms += 600001
machine.matrix()
assert abi["gpt_counter_bytes"] == 4
assert machine.hardware.registers[0x4007600C] == 96000
```

The stock fixture requires the already-extracted US7.02 image identified in
`docs/mistel-md770-stock-bluetooth-power.md`; its hash is enforced. The
existing `stock_probe.py` / `stock_trace.py` checks remain separate from
the unfinished emulator.
