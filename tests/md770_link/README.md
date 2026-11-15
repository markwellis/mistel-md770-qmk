# Historical MD770 split-link probes

These original GPL-2.0-or-later source snapshots were used on 2026-11-13:

- `uart_probe.c` records UART, GPIO and frame counters before the PB11 correction.
- `pb11_probe.c` adds the right-half PB11 high output used in the successful paired test.

Each file replaces `link.c` in its historical QMK keyboard source and
requires the QMK console. They are archival probes, not additions to the
current production build. See the [recorded observations](../../docs/mistel-md770-qmk-split-diagnostics.json)
and [GPL text](../../keyboards/mistel/md770rgb_bt/keymaps/markwellis/LICENSE).

The console includes recent matrix traffic. Keep captures private; the
published record contains counters and register observations only.
