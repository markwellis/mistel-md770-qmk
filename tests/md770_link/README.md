# Split-link checks

Run `nix-shell --run 'bash tests/md770_link/run.sh'` from the repository root.
The stock comparison requires the recorded left US 4.01 and right US 7.02 binaries.

The native harness compiles the actual QMK link and framing source for both halves
with address, undefined-behaviour and bounds sanitisers. It checks periodic
snapshots, coalesced ticks, queue backpressure, retained matrix/RGB state, PB8
mode transitions, RGB power requests and UART retiming/sleep restoration.
Hardware services are supplied; the tests do not establish electrical wake or
physical UART timing.

The stock comparison executes left routines `0x53bc` and `0x5468` against the
same observation histories as the native QMK implementation. It compares mode,
filter counter, periodic counter, enqueue attempts and USB mode changes after
every observation. USB transport and UART enqueue are explicit boundaries.
The initial low-input counter wrap is included; stable modes saturate at 0/16.
Right routine `0x66ac` is compared for periodic-counter and enqueue behaviour,
including coalesced elapsed-tick batches that wrap its byte counter.
Results and source hashes are saved in
`docs/mistel-md770-link-stock-conformance.json`.
