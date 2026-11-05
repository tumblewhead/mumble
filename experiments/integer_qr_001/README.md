# Integer QR: digit-by-digit versus CORDIC

Base d4d12a9, branch experiment/integer-qr-001. Both prototypes are implemented,
compared and retained for research. No campaign/default profile is changed.

## Results

| Metric | Digit-by-digit | CORDIC |
|---|---:|---:|
| Standalone kernel-image text (includes harness) | 1250 B | 978 B |
| Integrated collector static SRAM | 9588 B | 9324 B |
| Observed integrated stack | 456 B | 408 B |
| Static + observed stack | **10044 B** | **9732 B** |
| Static + provisional 1024 B stack | 10612 B | 10348 B |
| 4096-sample integrated relative Gram error | 3.858e-6 | 3.864e-6 |
| Q16 unit-row information error after20M updates | -0.0556% | -0.2833% |

Integrated figures include float response calculation/configuration, feature
conversion, integer history, row scratch, vectors and alignment. History is2380B
(595 int32 values); observed bank allocation3080B. They exclude IPC, recovery,
platform drivers/ISRs and host fitting. The execution witness runs512 samples of
M23 code on M33 QEMU. Observed stack is not a worst-case bound. Both exceed10KiB
with the provisional1KiB stack reserve. There is no firmware admission claim.

**The integrated collectors use Q12, not Q16.** Q16 was too narrow for the raw
whitened feature stream and its original512-sample witness rejected. Q12 provides
16 times the range at16 times coarser resolution. Its20M repeated-row tests lose
16.1% (digit) and16.7% (CORDIC) of information. At their20M endpoints
an additional identical row leaves each scalar factor unchanged: both have
stalled permanently for that input. Therefore neither fixed-scale collector is suitable
for sustained use as implemented, despite small short-stream aggregate errors.
The tighter Q16 kernel controls must not be used to qualify the Q12 collector.

## Shared numeric contract

The kernel consumes int32 upper-triangle square-root coefficients and one int32
row, at a common caller-defined power-of-two scale. n is1..34; all stored/input
magnitudes must be <=2^29; diagonal pivots must be nonnegative. Outputs outside
that range reject. There is no saturation, automatic rescaling or hidden forgetting.
A rejection after work starts may partially mutate arrays; the enclosing collector
latches failure. Buffers must be nonaliasing. The standalone kernel itself has no
validity state. Zero incoming pivot skips rotation exactly, preserving zero-row
identity even on a populated factor.

Digit-by-digit: compute the norm with16 fractional guard bits using an implicit
96-bit radicand and64-bit root/remainder; generate Q30 rotation coefficients using
fractional binary long division. Round only the stored norm to the integer grid.
Trailing entries use64-bit multiply/add and round back to int32.

CORDIC: vectoring generates30 rotation direction bits from the pivot pair, with16
internal fractional guard bits. The same schedule rotates each trailing pair.
One Q30 inverse-gain constant corrects the magnitude. A split multiply avoids
128-bit arithmetic. No angle table is needed because QR uses directions directly.
The gain approximation and finite iterations introduce error as well as storage
rounding. A tiny pivot can produce substantial absolute error on a much larger
trailing entry; retaining positive semidefinite R^T R does not certify accuracy.

The float-to-integer adapter uses explicit nearest rounding with ties away from
zero, via truncation and fractional correction. Every conversion is range checked.
Q12 decoding is R_integer/4096; Q16 decoding is R_integer/65536. Thus scale changes
units, not evidence weight. The host must decode with the matching scale. The
short integrated test compares R^T R against retained float-generated features;
it does not fit parameters, compare against the exact battery model or validate
uncertainty coverage.

## Review-driven corrections

- attempt001 used the rounded stored norm to form digit coefficients. For valid
  R=[1,1000000,0], x=[1,-1000000], this doubled trailing information. Guarded norm
  coefficients fix the control to approximately2.21e-6 relative error.
- A nonempty CORDIC history changed on an all-zero row. Skipping every b=0 rotation
  makes that operation exactly identity. attempt003 includes the regression.
- The first adapter template replaced part of CORDIC_KIND as well as its value;
  preliminary collector/stack artifacts are superseded by reviewed_* outputs.
- Float conversion using v+0.5 could perturb large integral values and values just
  below a half. Truncation plus fractional correction fixes both. Independent
  UBSan/float-cast-overflow testing covers61086 signed float inputs.

Original artifacts remain local. Final receipts preserve only compact evidence.
Independent review additionally checks100000 integer sqrt/ratio reference cases,
random widths, boundary inputs, range rejection and zero-row identity.

## Execution cost

Host timings in result.json are diagnostic, not M23 cycle predictions; short-stream
measurements include Python/ctypes overhead. A full34-column CORDIC insertion can
perform595*30=17850 micro-rotations, plus gain correction, conversions and response
calculations. At35Hz/16MHz the entire sample budget is about457143 cycles. Target
cycle qualification remains necessary; small code alone does not establish that
we meet it. QEMU provides execution/stack witnesses, not a cycle certificate.

## Decision and next step

CORDIC is the smaller kernel and collector; digit-by-digit is more accurate in the
Q16 repeated-unit control. Neither passes the sustained Q12 requirement. Keep both
as building blocks and leave binary64/history48 as the default.

Next: physically justified column scaling and retained rounding remainders, with
explicit bounds on information distortion across rescaling. Merely increasing
iteration count cannot recover bits discarded at storage. Test weak directions,
small pivots with large trailing values, range exhaustion, and repeated evidence
before promoting either collector or starting a long battery campaign.

The CORDIC vector/rotation/gain helpers are separate in kernel.h. Later trig work
can reuse these operations, but needs an angle-driven rotation interface, quadrant
handling and angle constants with their own error tests. No trig functions or
angle LUT bytes have been added to the estimator in this experiment.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.integer_qr_001.run \
  --fraction-bits 16 --out experiments/integer_qr_001/my_q16
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.integer_qr_001.run \
  --fraction-bits 12 --out experiments/integer_qr_001/my_q12
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.integer_qr_001.integrate \
  --kind cordic --fraction-bits 12 --out experiments/integer_qr_001/my_collector
```

Use --kind digit for the other collector; --execute creates a separate stack
witness. Use fresh output directories. These commands build research probes, not
campaign-ready estimator backends.
