# Qualified mainline integration

Previous main: `311218af167acad715e3738015c34568a62c3f98`.
Reviewed experiment tip: `fdc605e`.
Integration branch: `integration/qualified-mainline-001`.

This integrates the source and recorded evidence accumulated since the field
promotion. An isolated clean worktree tests the combinations before a fast-forward
of main. Experiment history remains available, including rejected ideas; inclusion
in Git history is not numerical promotion. No existing result is rewritten.

## Selected outcomes

- Current campaign infrastructure: compact recording/replay, source-bound builds,
  default overlays, clearer parameter-error comparisons, independent workload/noise
  seeds, parallel cases and configurable actual sample intervals.
- Original-origin native tangent, fused updates and H7 comparison paths, with H7
  transaction containment and explicit failure/publication states. These remain
  opt-in; uncertainty misses in historical controls are not declared repaired.
- Distinct-bank, reduced-bank float64 and native rowwise comparison paths. Bank
  modes require stationary 25 C; rowwise requires rank3, float64 and no centering.
  Paired 72-hour evidence establishes equivalence to the reduced reference, not
  improved physical accuracy or coverage.
- Reviewed full-core C build optimizations: shared calculations/QR/triangular solves,
  reduced immutable metadata and response pointers, exact byte index tables and
  shared physical-coordinate helpers. The selected combined-scalar native build
  reproduces 24400 B static. It is a separate generated ABI, not silently substituted
  into the desktop SRAM adapter.
- Four explicit numerical capability builds. Qualified subtraction sharing and
  scratch reuse remain available in the experimental integer collector; its Q12
  accumulation failure still prevents promotion as a reliable estimator.

The default remains joint-field/C/float64/bounded hysteresis at35Hz. Field refresh
remains60s, bank rank4/float64/uncentered, rowwise implementation baseline and SRAM
history64. No low-precision default, implicit test truth, forgetting, threshold
change, duplicate evidence or automatic checkpoint migration is introduced here.

## Not promoted

Float32/naive Q12 accumulated history, paired Gram with invalid information,
unsuccessful constant codecs, lazy free-state reconstruction, or any claimed
complete10KiB/lifetime/aging/coverage qualification. Historical conditional proofs
remain conditional; this integration does not convert them into deployment proofs.
Sub-10KiB collector resource results omit unimplemented application responsibilities
and cannot override their known numerical failures.

## Fresh qualification

- Tangent/H7/default/transaction tests: **101 passed**.
- Bank/reduced-bank/native rowwise tests: **47 passed**.
- Runner, recording, workload, plotting, replay and SRAM-adapter tests: **65 passed**.
- Five native generator combinations rebuilt. UBSan parity, numeric and159 invalid
  bindings per variant pass with identical transcripts. The selected combined
  helpers reproduce their earlier hashes and static footprint.
- All four default capability builds compile in a clean checkout and reproduce
  static bytes:24400 full,13528 collector,13864 SOC,17720 predictor.

No long sweeps were rerun. Existing owner-run receipts are retained with their
original revisions and hashes. The receipt lists test commands, output hashes and
native controls. Matplotlib's fallback cache warning and all-SRAM RWX linker
warnings did not cause failures; neither is a new qualification claim.

## Source and artifact policy

The branch ancestry is linear from the previous main, so fast-forward preserves
all source identities and proof/review history. There are1066 changed paths at the
experiment tip, approximately14.26MB of final file contents. New-history blobs total
approximately41.96MB uncompressed; the largest is a1.54MB scientific receipt.
There are no new trajectory CSVs, ELF/shared-library binaries or massive raw-run
exports in this range. Generated tests/builds from this integration remain ignored
and local. This is not a request to upload owner campaign data.

Two stale guide statements are corrected: compare-tangent means field+tangent,
and rowwise's older9816B figure excludes executable code/constants. The top-level
README now separates current mainline use from historical experiment notes.

## Hardware direction retained for future work

The M23 is16MHz and its roughly10KiB local allocation includes code/constants/data
and stack. The system provides IPC. A larger processor has an FPU but can lose its
SRAM during sleep; the M23 cannot access or wake it then. Separate always-on SRAM
can retain handoff information. Its available size and relationship to the10KiB
allocation, maximum sleep duration, and FPU precision remain unspecified. No
unmeasured two-processor protocol or lifecycle implementation is promoted.
