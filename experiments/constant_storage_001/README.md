# Exact index storage and provisional float32 coefficients

Base `36856cc`; numerical baseline is the contiguous-response implementation
`bbe8a8f`. The selected exact change is `byte_indices`. The `f32_coefficients`
variant is retained for qualification, not selected as an equivalent estimator.
Mainline/campaign defaults and existing adapters remain unchanged.

| Variant | Text | Rodata | BSS | Static total | Observed stack |
|---|---:|---:|---:|---:|---:|
| Baseline | 16660 | 984 | 6936 | 24608 | 672 |
| Byte indices | 16652 | 948 | 6936 | 24568 | 664 |
| Byte indices + float32 P/V | 16816 | 640 | 6936 | 24424 | 664 |

All include28 bytes of vectors. Baseline has no inter-section gap; both candidates
have4 bytes of inter-section alignment. The byte
variant saves40 static and8 observed stack bytes:48 bytes in the paired comparison.
Its provisional total with1024 bytes of stack is25592 bytes. The float variant
saves another144 static bytes (192 combined vs baseline including observed stack),
with a provisional1024-stack total25448 bytes. Stack is a separate M23-code/M33-QEMU
fixture witness, not a worst-case bound or hardware timing measurement. Numerical
core scope excludes platform services. The10KiB target remains unmet.

## Exact index change

`ip[6]` and `jp[6]` select hysteresis polynomial exponents and contain only0,1,2.
Changing their shared declaration from unsigned to unsigned char preserves each
value exactly. Their indices are constrained to0..5 by the existing loop/modulo.
C integer promotion at the consumer preserves the same values. No arithmetic,
control flow, ABI, state, likelihood ownership or uncertainty calculation changes.
The nominal36-byte table reduction also saves8 text bytes; the linked image includes
4 bytes of additional inter-section alignment, so the actual static saving is40 bytes.

The compiled exact control matches all3,458,582 transcript bytes:256 support
probes,94 feature rows,256 samples,8 refits,4096 scalar queries, final history,
response and joint factor.159 invalid bindings reject while preserving the core.
UBSan is clean. Independent review repeats parity, invalid checks and target build.

## Float32 coefficient storage

Only the39 P coefficients and39 V coefficients are rounded once to binary32.
Their loads explicitly promote to double; all recurrence, fit, history and scalar
arithmetic stays binary64. History remains the already-selected48-bit storage
format with its existing limitations. Config projected_map and stream V pointer
types become float pointers: callers must rebuild; old ctypes ABIs are not valid.
Both arrays remain immutable with the same39-element extent and lifetime rules.
Mean, scales, centres and OCV remain double.

The tables shrink by312 bytes. Linked rodata falls308 bytes after internal
alignment; conversion/access code adds164 bytes, leaving144 bytes saved. No full
expanded copy of the coefficients is allocated.

`numeric_check.py` compares a257-point projected map/derivative sweep,64 supported
points of34 projected feature rows, and4096 synthetic samples at50Hz (81.92s).
All32 refit/status sequences agree; only3 refits meet acceptance criteria in each
arm.464 of512 scalar queries succeed in both arms; other statuses agree as well.
This synthetic fixed-voltage control is not a realistic plant or a coverage test.
It must not be described as32 successful refits or512 valid numerical estimates.

Measured maxima: map value delta3.632e-8, map derivative delta2.681e-8,
feature value delta3.567e-9, feature derivative delta3.497e-8, and scalar coordinate
delta3.058e-8 across successful queries. Returned coordinates have different units;
these numbers are not a common relative battery error. Carried response states
match exactly. Variance deltas and all per-coordinate measurements are in the
receipt. These are observations, not predeclared accuracy acceptance thresholds.

## Fixed-coefficient perturbation model

Let dP and dV be the coefficient-rounding differences. On |u|<=1,
|T_j(u)|<=1 and |T'_j(u)|<=j^2 give map bounds sum|dP_j| and sum j^2|dP_j|.
For a state vector x, |x^T dV| <= ||x||inf times column sums of |dV|.

The composed projected likelihood response uses V P T(u). Its coefficient change
is dV P + V dP + dV dP. Therefore an entrywise envelope is
B=|dV||P|+|V||dP|+|dV||dP|. With gamma=sum(B) and
 gamma_u=sum_j j^2 sum_i B_ij, the additional represented RC-component error is
at most (|b|+R I_peak)*gamma per branch, assuming free filter states bounded by1
and forced filter states bounded by I_peak. Its u derivative uses gamma_u.
This concerns the represented likelihood response; endpoint transport retains
its original full-bank formula. It does not assert physical correctness of the
underlying cardinal/rank3 representation.

These expressions bound coefficient perturbations in exact arithmetic. The
reported floating evaluations are not outward-rounded certificates and exclude
runtime roundoff, fitting nonlinearities and previous history48 error. Fixed
quantization does not repeatedly quantize coefficients, but its likelihood error
still repeats with observations: standardized score effects can grow as evidence
accumulates. Small short-run differences do not establish honest long-run coverage.

Before adopting float storage: carry its approximation into the representation
error budget; run paired realistic long trajectories with quiet/repetitive and
exciting stimuli, temperature and aging as supported; compare Q/SOC/RC predictions,
uncertainty and failure rates. Do not silently substitute this ABI in the campaign.

## Reproduce

Use fresh output directories on rerun:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_storage_001.target --variant baseline --out experiments/constant_storage_001/baseline
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_storage_001.target --variant byte_indices --out experiments/constant_storage_001/byte_indices
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_storage_001.target --variant f32_coefficients --out experiments/constant_storage_001/f32_coefficients
python3 -B -m experiments.constant_storage_001.exact_check --out experiments/constant_storage_001/exact001
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_storage_001.numeric_check --out experiments/constant_storage_001/numeric003
python3 -B -m experiments.constant_storage_001.execution --variant byte_indices --out experiments/constant_storage_001/stack_byte_indices
python3 -B -m experiments.constant_storage_001.execution --variant f32_coefficients --out experiments/constant_storage_001/stack_f32_coefficients
```

An initial numeric001 harness failed compilation because its output helper reused
the core's `emit` identifier. The renamed helper is isolated to the test; failed
artifacts are preserved separately. numeric002 measured the same controls before
the composed V/P error expression was added; numeric003 is the final report.
