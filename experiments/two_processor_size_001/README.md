# Two-processor size measurements

Base `c2c8b27`; branch `experiment/two-processor-size-001`. These are linked Cortex-M23
numerical partitions, not a deployed two-processor protocol. The existing full
estimator remains the production-of-experiment baseline; no campaign changes.
All code, constants and static storage in the size image count as SRAM.

## Measured budgets

| Always-on responsibilities | Text | Rodata | BSS | Static total | Observed stack | Static + observed | With 1024 stack |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full existing estimator | 16480 | 948 | 6936 | 24400 | 680 | 25080 | 25424 |
| History collector only | 8276 | 368 | 4856 | 13528 | 424 | 13952 | 14552 |
| Collector + SOC point readout | 8576 | 368 | 4888 | 13864 | 440 | 14304 | 14888 |
| Collector + all16 point readouts | 11688 | 624 | 5376 | 17720 | 464 | 18184 | 18744 |

Every image includes28 vector bytes; alignment is8/0/4/4 bytes respectively.
The full image was rebuilt and reproduces24400B. Its680B stack witness is the
prior independently reviewed coordinate-sharing fixture; split variants have
new execution witnesses. Stack observations are not worst-case bounds or interrupt
stack budgets. Split witnesses use M23 code on M33 QEMU; no hardware timing claim.

The collector reduces static footprint by10872B and the paired static-plus-observed
figure by11128B. It still exceeds10240B by3712B including observed stack. A fixed
1024B stack reservation gives4312B over budget. None fits10KiB as measured.

## What each partition includes

All split variants preserve the original sample-to-feature recurrence, the same
93-double carried response state, the same34-wide48-bit square-root history and
history insertion arithmetic. They remove incremental local inference-factor
updates, nonlinear fitting, line search and uncertainty reconstruction. The
collector validity flag concerns stream/history operations, not inference support.
Therefore it is not equivalent to the full estimator's complete failure gating.

The SOC variant consumes two host-supplied physical parameters: origin SOC z0 and
inverse capacity1/Q. It reports z0-(1/Q)*accumulated charge when finite/in range.
The pair must refer to the SAME origin as the carried charge/history. No current
uncertainty or autonomous parameter learning is provided.

The full-point variant consumes16 host-supplied whitened coordinates, keeps the
original supported()/transported() formulas and emits16 endpoint chart values.
It does not fit or calculate covariance. Its output and derivative scratch are
not optimized for overlap in this measurement. Failed prediction can leave a
partially written result; application callers must gate results by status.

The current stream implementation is stationary25C with affine OCV. Temperature
variation, aging extensions and their memory are not added by this partition.
The larger processor must own current-prior refitting, uncertainty, validity
assessment and recovery. A host-only service image has not been measured; the
rebuilt full image is a reference, not a proposed final host service footprint.

## Resident data and why the collector is still large

Collector bank allocation is4808B: history3570B, response744B, row scratch272B,
model/valid fields and alignment, copied input40B, and the inherited160B reserved
identity area. Synthetic volatile sample/status slots add48B, reaching4856B BSS.
The160B reservation is counted but does not implement sequence/transaction logic.
No raw sample queue or duplicate history snapshot is stored.

Collector code remains8276B. The software-double add/multiply/divide routines
alone occupy3844B; comparisons, copies, math, row formation and QR/history update
remain as well. Removing fitting does not remove those shared arithmetic needs.
The current linked reset() also contains the inlined sample loop; its size is
not a reset-only allocation that could all be offloaded.

## Costs not yet defined

These totals include small startup/zeroing code, current math/configuration, input
slots and the numerical path. They exclude a real IPC driver, mailbox framing,
snapshot consistency protocol, parameter commit/version checks, wake controller,
interrupt/device drivers and recovery protocol. No artificial byte estimate is
presented as measured implementation. A full duplicate history snapshot would
cost another3570B before alignment; streaming transfer must solve coherence.

The measurement harness continually reads synthetic volatile parameter slots
and may publish a value on error to keep access code observable. This is NOT an
atomic installation protocol or a trustworthy application readout flow. Real
updates must be serialized and tied to a sample prefix, origin and model version.
The host must not overwrite newer carried state or count a history snapshot and
its derived posterior as independent evidence. A delayed response needs an
explicit validity/transport contract while collection continues.

All owned arrays/configuration must remain live, immutable where specified, and
nonaliasing. One serialized sample owner is assumed. Invalid stream/history
operations latch failure; no rollback/transaction copy is provided. Starting
collector history at zero is a new-origin bootstrap, not recovery of old evidence.

If sleeping-processor SRAM is retained AND accessible to the always-on processor,
external placement of history could change the local budget substantially. That
hardware property is not assumed here; no shared-SRAM placement image is measured.
The private-SRAM measurements remain valid regardless of that future option.

## Validation and reproduction

The host UBSan control feeds512 ordered samples through all variants and the full
reference. History and response checkpoints every32 samples match byte-for-byte
(71080-byte status/checkpoint transcripts). Full-point predictions match the
original full transport helpers over16 coordinates; SOC is checked against its
explicit origin/charge formula. A negative-dt sample rejects and poisons subsequent
collection without further history/response changes. This does not establish
full-solver invalid-state equivalence or asynchronous handoff correctness.

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.coordinate_sharing_001.target --variant combined_scalar --out experiments/two_processor_size_001/full
python3 -B -m experiments.two_processor_size_001.measure --variant collector --out experiments/two_processor_size_001/collector
python3 -B -m experiments.two_processor_size_001.measure --variant soc --out experiments/two_processor_size_001/soc
python3 -B -m experiments.two_processor_size_001.measure --variant predictor --out experiments/two_processor_size_001/predictor
python3 -B -m experiments.two_processor_size_001.measure --variant collector --execute --out experiments/two_processor_size_001/stack_collector
python3 -B -m experiments.two_processor_size_001.measure --variant soc --execute --out experiments/two_processor_size_001/stack_soc
python3 -B -m experiments.two_processor_size_001.measure --variant predictor --execute --out experiments/two_processor_size_001/stack_predictor
python3 -B -m experiments.two_processor_size_001.check --out experiments/two_processor_size_001/check002
```

Use fresh directories on rerun. The first check001 verified only predictor success;
check002 adds explicit prediction-value parity. The execute runner now requires
both successful QEMU exit and printed status=0 (semihost exit alone is insufficient).
Earlier artifacts are retained. Independent review rebuilds all splits, repeats
stack/host controls and checks that extracted numerical helpers are unchanged.
