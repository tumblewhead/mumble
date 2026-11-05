# Selectable always-on capability profiles

Branch `experiment/capability-profiles-001`, based on `3f4b733`.
One command now builds any of the four previous capability profiles. The defaults
preserve binary64 arithmetic and the existing 48-bit history storage. No mainline
campaign implementation or defaults changed. This remains a stationary 25 C,
affine-OCV research core, not complete battery firmware.

From this worktree, using a fresh output directory:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.capability_profiles_001.compile \
  --profile all --out experiments/capability_profiles_001/my_build
```

Replace `all` with `full`, `collector`, `soc`, or `predictor` to select one.
Each emits a generated C core, configuration, linker script, ELF, map, symbol
sizes and measurement JSON. `profiles.json` collects results. Single split
profiles regenerate configuration from the public fixture; they do not require
an earlier generated build directory. This build front end consolidates the
existing shared source generators rather than forking the estimator equations.

| Profile | Runs locally | Input from larger processor | Output | Local static bytes |
|---|---|---|---|---:|
| `full` | Stream, history, fit, uncertainty, all readouts | Original prior/config | Estimates and uncertainty | 24400 |
| `collector` | Stream recurrence and history QR | Immutable config | History and carried response | 13528 |
| `soc` | Collector and SOC readout | Origin SOC and inverse Q | SOC point estimate | 13864 |
| `predictor` | Collector and 16 transported readouts | 16 whitened parameter coordinates | 16 endpoint chart values | 17720 |

All totals count `.text`, constants, static arrays, vectors and alignment as
SRAM. These four static measurements reproduce the prior experiment exactly.
Prior stack witnesses remain 680/424/440/464 bytes, respectively; not worst-case
bounds. Split profiles support `--execute` for a separate QEMU stack witness;
full-profile stack qualification retains its existing harness. QEMU runs M23
instructions on an M33 model and supplies no M23 cycle guarantee.

## Contracts across the split

- Stream: ordered V/I/T, actual dt and noise SD; immutable configuration and
  nonaliasing arrays; one serialized owner. The current core rejects temperatures
  other than 25 C. No sample replay is introduced by the build profiles.
- History: the same 595 packed entries and 93 carried response values as before.
  A history snapshot and a posterior derived from it are not independent evidence.
- Host updates: parameters must refer to the same model, origin and prior chart.
  SOC parameters are physical; predictor coordinates are whitened. Prefix/version
  validation, coherent snapshots and atomic installation are still application work.
- Validity: collector failure latches refusal; it does not reproduce full inference
  validity checks. Readouts have no fresh uncertainty calculation. Callers must gate
  outputs by status; predictor failure can leave partial output.
- Initialization: setup starts a NEW history origin. It is not reset recovery.
- Allocation: generated code has fixed arrays and no heap. The 160-byte identity
  reserve remains counted but does not implement a protocol. IPC, platform ISR,
  recovery and host-only service images remain outside these measurements.

## Substantial target 1: software arithmetic

`--arithmetic float` is an explicitly experimental collector/SOC build. It changes
configuration, stream recurrence, math, QR, history storage and interfaces to
binary32. It does not merely quantize constants. The generator uses float-suffixed
literals so unused double helpers can actually disappear. The small shared math
uses binary32 range reduction, a polynomial and Newton square root. No fast-math.

| Experimental profile | Text | Constants | BSS | Vectors + gap | Static | Observed stack | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Float collector | 5486 | 192 | 3104 | 30 | 8812 | 240 | **9052** |
| Float collector + SOC | 5674 | 192 | 3120 | 30 | 9016 | 248 | **9264** |

With a provisional 1024-byte stack reservation these become 9836 and 10040 bytes.
Those are numerical-core budgets, without IPC or recovery. They are NOT accepted
long-duration alternatives, despite fitting the numerical-core memory target.

A 131072-sample varied-load/rest diagnostic (2621.44 seconds at 50 Hz) completed:
maximum normalized Gram Frobenius difference was 0.00019358; maximum carried-state
absolute difference was 3.495e-5 (mixed units); charge difference was 4.139e-9 Ah.
These are representation diagnostics, not fitted-parameter accuracy or coverage.

The decisive counterexample is repeated unit evidence in a one-column QR factor.
Its exact squared factor should equal the observation count. The float shared-math
factor stalls at update **5378752**; after 20 million observations its represented
information is about **72% too low**. Standard `hypotf` also stalls, at update
12694699, and can overstate information before stalling. Thus changing the small
math implementation alone does not remove the finite-precision accumulation
problem. Binary64 arithmetic with existing 48-bit storage does not stall in this
20-million-update control; this is not an indefinite-accuracy proof for that format.

The trial is retained as a resource experiment and counterexample. Default
binary64 profiles remain selected. Next precision work should separate bounded
response calculation from growing history accumulation; retain small contributions
using a justified accumulator/merge design before shrinking precision. A mixed
precision design may pull BOTH arithmetic runtimes into `.text`, so it must be
linked and measured rather than assumed to save memory.

## Substantial target 2: history placement

For split profiles only, `--history shared` puts the history in a separate NOLOAD
linker section at example address `0x31000000`, aligned to 8 bytes. Setup explicitly
zeros it. This address is a proposed hardware/linker contract, not detected memory.

| Binary64 split | Local static bytes | Additional shared history bytes |
|---|---:|---:|
| Collector | 9976 | 3570 |
| SOC | 10312 | 3570 |
| Predictor | 14160 | 3570 |

The external bytes are still required SRAM. Local savings are not exactly 3570
because placement changes alignment and initialization code. The collector's
264-byte local headroom is less than its prior 424-byte stack witness, even before
IPC. No shared-placement stack measurement or hardware validation is claimed;
QEMU execution of this unverified shared address is intentionally rejected.

This option requires retained SRAM accessible while the larger processor sleeps,
with serialized ownership/coherent access. That hardware property remains unknown.
It does not assume off-chip flash, remove history, or provide a snapshot protocol.
Do not use the shared image on hardware until its address/access contract is met.

## Reproduce qualification

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.capability_profiles_001.compile \
  --profile collector --arithmetic float --out experiments/capability_profiles_001/my_float
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.capability_profiles_001.qualify \
  --baseline experiments/capability_profiles_001/my_build \
  --trial experiments/capability_profiles_001/my_float \
  --out experiments/capability_profiles_001/my_check
python3 -B -m experiments.capability_profiles_001.stress \
  --core experiments/capability_profiles_001/my_float/collector/core.c \
  --reference-core experiments/capability_profiles_001/my_build/collector/core.c \
  --out experiments/capability_profiles_001/my_stress
```

Double profiles retain exact previous 512-sample transcript and prediction hashes.
UBSan controls include invalid-dt refusal and no subsequent mutation. The math
check samples 200000 inputs per function: exp/expm1/sqrt errors were at most 1/2/1
ULP against double libm rounded to float. This is not an exhaustive math certificate.
Initial check001 exposed a helper-name collision with GNU libc (`fsqrt`); functions
are now namespaced. stress002 exposed a harness scalar-type mismatch; stress004
fixes it and prints 17 significant digits. Failed and superseded artifacts remain
local; compact final evidence and the independent review are in provenance.
