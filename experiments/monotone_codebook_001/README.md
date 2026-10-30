# Monotone trajectory codebooks and recenterable square-root history

The next representation is implemented and **1,118 finite checks pass**:
1,082 main checks plus36 contiguous-packing controls. It supports exact
real-arithmetic square-root re-centering, monotone curve constraints, packed
8/12/16-bit coefficient codebooks, and separate temperature-history and
temperature-response curves. It has not been integrated as a full aging solver.

The key result is that **quantizing a chart center need not approximate the
likelihood**: translate the residual factor to compensate for the decoded
center. When codewords instead approximate the physical curve, the implementation
supplies a quantization bound. These are deliberately separate operations.

[Derivation](derivation.md), [registered plan](plan.json),
[main checks](attempt001/result.json), [packing checks](packing001/result.json)
and [summary](summary.json) record the assumptions and evidence.

## Adopted direction and temperature separation

Following the user's instruction, the new trajectory model assumes monotone
reference-condition aging: R0 and R_i are nondecreasing; Q and C_i are
nonincreasing. This is an adopted model assumption. Rates, curvature and actual
physical validity remain uncalibrated. tau_i=R_i*C_i is not assumed monotone.

The user selected both temperature representations:

1. A curve for measured temperature history T(t), over a declared interval.
2. A separate reversible parameter-response curve g(T), anchored to zero at
   25 C in these controls.

The illustrative decomposition is h(t,T)=a(t)+g(T). Temperature can reverse
the apparent parameter trend even while a(t) is monotone. Additive separability
is a prototype assumption; age-dependent thermal response, temperature-driven
aging rate changes and sensor uncertainty remain separate modeling obligations.
Four temperature coefficients are not claimed to encode years of thermal cycles.
Consumed temperature segments must eventually be absorbed into the owned history
operator, rather than accumulated as an unbounded archive.

The old two-sided health-diffusion implementation does not enforce monotonicity
and remains preserved as historical reference. The new code enforces monotone
trajectory coefficient support; a normalized monotone health-transition model
and support-aware posterior integration remain to be specified and qualified.

## Implemented representation

[factor.py](factor.py) stores the augmented upper-triangular factor R, center c,
observation-noise normalization, source interval, chronology and residual-defect
ledger. It evaluates `||R*[theta-c;1]||²/2` plus the noise constant.

Changing c to c_new updates only the final column of R. The likelihood,
gradient, residual energy and cross terms are preserved in real arithmetic.
The original prior/support are still evaluated in physical coordinates.
Chronologically adjacent factors merge after aligning centers; overlaps and
incompatible source/basis contracts reject. Appends and failed re-centering
are atomic, and queries are read-only. Quantized-center packets retain the
factor adjustment and spent error ledger. No posterior is appended as evidence.

[splines.py](splines.py) supplies two explicit curve families:

- A degree-one spline through four sites.
- A single cubic Bernstein segment with four control coefficients. These are
  control coefficients, not four interpolation knots.

Both have nonnegative bases summing to one. Ordered coefficients guarantee
monotonicity. A shared ordered quantization grid preserves that order, including
ties. Invalid order, unsupported values and extrapolation reject; no clipping
or sorting repairs them. The codebook is an implicit uniform product codebook,
so it does not need a table containing thousands of prototype curves. A learned
vector codebook is not implemented.

## Quantization bounds and bytes

For spacing Delta, the decoded age curve differs by at most Delta/2 from the
unquantized curve in the chosen family. The anchored thermal response has bound
Delta_g. If g has Lipschitz bound L_g, the combined encoding bound is

```
epsilon_age + epsilon_thermal_response + L_g*epsilon_temperature_path.
```

For the frozen engineering ranges—relative health0.5–1.5, temperature−20–60 C,
thermal coefficients−0.3–0.3—the12-bit bounds are:

| Encoding component | Bound |
| --- | ---: |
| Age curve | 0.0001221 of reference, or **0.01221%** |
| Temperature path | **0.009768 C** |
| Anchored thermal response | 0.0001465 of reference |
| Combined illustrative model with L_g=0.003/C | 0.0002979 of reference, or **0.02979%** |

These cover quantization only. They exclude curve-model remainder, calibration,
sensor errors, posterior uncertainty and the propagation through battery voltage/
SOC equations. They are not achieved capacity/SOC accuracy or a lifetime NLL
bound. Quantizing a physical curve can still introduce accumulated likelihood
error; compensated chart translation avoids that particular representation change.

Actual contiguous encoding of32 age coefficients (eight health quantities),
four temperature-path coefficients and24 thermal-response coefficients uses:

| Bits per coefficient | Packed60-coefficient payload |
| --- | ---: |
| 8 | 60 B |
| 12 | **90 B**, versus480 B as doubles |
| 16 | 120 B |

At12 bits, the parts are48 B age,6 B temperature history and36 B thermal
response. Packing each three-coefficient thermal curve separately pads it to
five bytes, producing94 B total; the separate packing control verifies the90 B
contiguous layout. Knot sites, ranges, version descriptors and uncertainty are
additional. The codebook envelopes are declared test domains, not empirical
physical support.

For the scalar eight-coordinate demonstration, a packed augmented square root
uses360 B;12-bit center codes use12 B, giving **372 B**, compared with424 B
using a floating center. The current Python factor stores a dense matrix and
JSON metadata, so372 B is a proposed packed factor-plus-center layout, not the
actual host object footprint. Only the center-code bit packing is implemented.

The main remaining storage problem is joint uncertainty. Expanding all eight
health quantities to independent age/thermal/residual coefficients gives64
coordinates: a dense augmented factor alone would use **17,160 B**. Codebook
compression of centers does not make that fit the complete10,240-B target.
A justified structured joint representation is needed; deleting cross terms
or assuming independent health quantities would change the evidence.

## Verification and remaining work

Two256-observation synthetic linear controls compare streaming QR with independent
batch residuals, gradients and an explicitly unbounded Gaussian algebra oracle.
They exercise64 re-centerings and all three code precisions. Maximum differences
include2.36e-11 NLL for merged factors and5.46e-12 NLL after12-bit center
encoding. The unbounded Gaussian comparison does not qualify a posterior under
monotone support.

The original C physical recurrence also agrees with a re-centered, quantized-
center conditional amplitude factor on32 queries over128 fabricated records;
maximum discrepancy is1.21e-8 NLL. This checks the existing stationary battery
primitive without changing its25 C model or treating unknown nonlinear rates
as identified.

The temperature anchor is exactly unexcited at reference temperature. A separate
control constructs age-temperature confounding when temperature tracks time;
anchoring removes a constant offset ambiguity but cannot invent excitation.
Joint age/thermal/residual cross terms remain present throughout.

The main checks took about0.60CPU seconds with108.4MB peak host RSS including
plotting, excluding compilation. No battery fits, particles or long trajectories
were run. Floating-point error remains unresolved beyond these finite checks.
Earlier artifacts remain hash-identical.

![Monotone aging, reversible temperature and codebook error](attempt001/monotone_temperature_codebook.png)

Next, derive a **structured joint square-root layout** from the physical
dependency graph before expanding to all aging/temperature coefficients.
Preserve center/residual and age/thermal coupling, original support and the
nonlinear-response error ledger. Then connect the smallest supported monotone/
thermal model to the battery operator. The prior zero-order nonlinear field's
large errors remain unresolved by this exact re-centering step; full nonlinear
closure, curve remainder, RC aging state transfer and complete SRAM/work still
require proof and qualification.

To rerun into a new main destination:

```sh
MPLCONFIGDIR=/tmp/mumble-codebook-mpl OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.monotone_codebook_001.qualify /tmp/mumble-codebook-new
```

The contiguous-packing control was run with
`python3 -B -m experiments.monotone_codebook_001.packing_check`; its exclusively
named `packing001` evidence is preserved.
