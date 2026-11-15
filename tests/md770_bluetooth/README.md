# MD770 Bluetooth and power checks

`run.sh` compiles the actual QMK keyboard drivers and ChibiOS resume function
against supplied registers, a FIFO model, GPIO, time and host services. It
uses address, undefined-behaviour and bounds sanitizers. C++ register proxies
provide FIFO read/write effects without changing the production C source.
The firmware itself is compiled as C in both-half QMK builds.

Run from the repository root:

```fish
nix-shell --run 'bash tests/md770_bluetooth/run.sh'
```

`QMK_HOME` defaults to the sibling `qmk_firmware` checkout. The Nix shell sets
that path. Cases cover queued reports and macro backpressure, media mappings,
transport recovery, incoming status/reconnect races, pairing, shutdown,
supply/LVD/LED states, USB suspend and both RGB drivers. The RGB checks verify
the unchanged shifted waveform for all 256 byte values and that wake priming
does not run under the global lock. Leak detection is disabled because the
execution environment uses ptrace; address and bounds checks remain enabled.

`stock_probe.py` and `stock_trace.py` execute original firmware instructions
under Unicorn. See the [stock research](../../docs/mistel-md770-stock-bluetooth-power.md)
for extraction, hashes, reproduction and the supplied-input scope.

The older `radio_probe.c` and reader remain historical diagnostics. Neither
the native tests nor Unicorn establishes electrical timing, physical charging
or Bluetooth delivery through the real module.

The new `emulator*.py` and `emulator_abi.c` files are an unfinished ARM
emulator prototype, separate from the passing native suite. See the
[resume checkpoint](../../docs/mistel-md770-emulator-checkpoint.md).
