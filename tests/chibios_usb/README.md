# USB regressions

`run.sh` checks the unchanged native QMK endpoint queue: suspend discards
queued input, and fresh input works after resume. The optional first Raw HID
packet after wake remains an upstream limitation accepted for this port.

`run-stop.sh` retains the independent investigation of the HT32 stop guard:

```fish
nix-shell --run 'bash tests/chibios_usb/run-stop.sh'
```

It extracts the actual generic API and pinned low-level function, then
compares the original with a one-line condition change in the test build.
The original fails hardware shutdown from SELECTED, ACTIVE and SUSPENDED;
the proposed condition passes all five permitted states. Endpoint cleanup
and repeated-stop behaviour are also checked with sanitisers.

This correction is not applied to the keyboard's dependency and its patch
file has been removed. The keyboard keeps the native USB driver running,
so it does not need these stop paths. The test establishes software dispatch,
not observed crashes, electrical behaviour or battery savings.
