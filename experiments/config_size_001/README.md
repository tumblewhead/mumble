# Configuration-backed finite-check reduction

The selected `chart_finite` candidate removes the raw `w[j]` finite check from
`supported()` while keeping the transformed-coordinate finite check. All bind,
sample, range and response-state checks remain. It saves56B static in the new
observable-input lane:24768 ->24712B. Cached exponential evaluation produced no
additional saving, and the combined candidate is the same size as chart_finite.

## Ownership and conditional argument

`bind()` checks finite means and positive finite scales, then stores pointers.
Configuration and its pointed-to arrays must remain valid and immutable during
use; this is a caller contract, not enforced protection against later mutation.
Response arrays are mutable and do not receive this optimization.

For each coordinate, `chart = mean + scale*w`. With finite mean and strictly
positive finite scale, IEEE nontrapping arithmetic has:

- NaN w -> NaN chart;
- infinite w -> infinite chart;
- consequently finite chart -> finite w.

Therefore `finite(w) && finite(chart)` and `finite(chart)` classify the same
inputs under the validated configuration contract. Finite-w overflow remains
rejected by the retained chart check. No thresholds, statistical approximations
or changed battery parameter support are introduced.

The new path may evaluate previously short-circuited arithmetic on NaNs. Floating
exception flags/traps and NaN payloads are outside this equivalence claim. The
embedded target uses software double arithmetic; compilation retains
-fno-fast-math and -ffp-contract=off. This is a local conditional argument, not a
proof of memory-corruption tolerance or indefinite estimator accuracy.

## Evidence

| Measurement | Baseline | Candidate |
|---|---:|---:|
| Observable-input static SRAM |24768B|24712B|
| Separate execution-fixture stack watermark |664B|664B|
| Static plus provisional1024B reserve |25792B|25736B|

Both execution witnesses returned status0. Their M23 code runs on an M33 QEMU
model. This does not establish timing or the full observable-input harness's
worst-case stack. The observable harness includes synthetic interface slots;
mainline and campaign defaults are unchanged.

Corrected direct controls compare20400 classifications, including6190 accepted
states, positive subnormal/maximal scales, nonfinite/zero/negative configurations,
NaN/infinite/maximal inputs and signed zeros. Invalid configurations remain
rejected. Independent review reran these tests and checked the argument.

`check001` is INVALID evidence: the host shared object's internal call to `bind`
resolved to libc's socket function, so every test rejected. `check002` binds
internal symbols locally with -Wl,-Bsymbolic and requires at least one accepted
case. The estimator implementation did not change during this fixture repair.
The target executables are not affected by that shared-library interposition.

## Reproduce

Use fresh output directories:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.config_size_001.target --variant chart_finite --out experiments/config_size_001/new_target
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.config_size_001.execution --variant chart_finite --execute --out experiments/config_size_001/new_execution
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.config_size_001.check --out experiments/config_size_001/new_checks
```

No long-stream rerun was used to justify this control-predicate change. Acceptance
is scoped to the preserved validation contract and measured footprint. Next:
inspect retained model pointers/metadata and lifetime-specific configuration
ownership, keeping validation at externally supplied boundaries.
