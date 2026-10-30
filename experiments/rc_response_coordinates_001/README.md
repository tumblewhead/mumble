# RC response coordinates: improvement across timescales, with a bounded-fit issue

The RC response comparison completed **36 cases and 29 numerical control
tests**. A further support-fitting audit passed **168 derivative checks**.
Response coordinates improve the one-second prediction substantially, but a
single common response interval does not transfer well to longer reversal
probes. Using each mode's public characteristic timescale gives a better overall
result, while still leaving short-time and mean/quantile discrepancies.

**Basic retained storage estimate: 2,496–2,512 bytes with two regions, or
4,960–4,992 bytes with four.** These include the three response-frame values.
They are numeric payload estimates, not complete subsystem memory: metadata,
solver state, query scratch, queue, stack and update workspace remain additional.
The current offline builder already needs over 2 MiB of arrays; no complete
10,240-B Cortex-M23 implementation is demonstrated.

See the [derivation](derivation.md), [frozen plan](plan.json),
[primary results](attempt001/result.json), [controls](attempt001/controls.txt),
and [support audit](support_audit001/result.json). The
[voltage-coordinate experiment](../voltage_coordinates_001/README.md) is the
preserved comparator. No original result was overwritten, no truth was read,
and no particle inference or physical-aging update was run.

## What the comparison changes

For each uncertain RC mode, use `a_i = 1-exp(-D_i/tau_i)` and retain
`F_i = a_i*v_i`, `G_i = a_i*R_i`: its free-voltage release and forced-response
coefficient. Retain the uncertain time constant, so the inverse is exact.
Keep the previously repaired boundary-voltage coordinate and all sixteen
quantities uncertain.

The dependent support is `-.25*a_i < F_i < .25*a_i` and `0 < G_i < a_i`.
A sequence of scalar Gaussian conditionals, each depending on **all previous
coordinates**, is normalized over these exact bounds. The Jacobian includes
`product(a_i²)` as well as the existing OCV/logit factors. No clipping, covariance
shrinkage, lost cross terms in the linear conditional model, or duplicate prior
is introduced. Nonlinear distributional fidelity is still an empirical question.

Three constructions distinguish the effects:

- **Physical-amplitude control:** `a_i=1`, with the same conditional density.
  This isolates replacing RC logits with bounded physical amplitudes.
- **Common one-second response:** `D_i=1 s` for every mode.
- **Public mode-scale response:** `D_i` is the geometric midpoint of that mode's
  public time-constant bounds: about 0.0474, 0.4743 and 6.7082 seconds.
  These intervals use neither truth nor fitted values.

Each construction is tested with the statistical mixture, fixed probability
atlas and restricted self-organizing capacity atlas, at two/four regions and
both saved prefixes. Capacity placement, source ownership and construction/
held-out populations remain unchanged. Old voltage-only messages were drawn
again with their original seeds to extend the comparator to the new probes;
they were not refitted.

The stored histories still span only 0.229 and 0.914 seconds. Future probes
are stationary predictions over one sample interval, 0.1, 1 and 10 seconds;
a reversal contains two segments of the stated duration. Longer segments are
split into actual intervals no greater than one second, carrying physical state.
These probes do not establish parameter learning over minutes or hours.

## What improved, and what did not

At the 32-record boundary, these are noiseless voltage standard deviations in
mV. Ranges cover all three region organizations and both region counts.

| Probe | Saved reference | Voltage-only baseline | Amplitude control | Common 1-s response | Public mode-scale response |
| --- | ---: | ---: | ---: | ---: | ---: |
| Boundary rest voltage | 1.968 | 1.970–2.004 | 1.966–1.985 | 1.968–1.984 | 1.960–1.983 |
| Load, 1/35 s | 0.600 | 1.030–1.045 | 0.979–0.992 | 0.981–1.002 | 1.022–1.033 |
| Load, 0.1 s | 0.680 | 1.455–1.479 | 1.256–1.276 | 1.130–1.157 | 1.270–1.295 |
| Rest, 1 s | 2.806 | 4.417–4.530 | 4.454–4.604 | 2.760–2.825 | 3.179–3.254 |
| Load, 1 s | 3.070 | 5.607–5.770 | 4.461–4.654 | **2.949–2.988** | **3.229–3.268** |
| Load, 10 s | 16.373 | 18.877–19.069 | 17.800–18.229 | 18.996–19.390 | **16.090–16.306** |
| Load/reversal, 10+10 s | 23.117 | 24.806–25.069 | 23.986–24.153 | **29.702–30.393** | 24.384–24.836 |

The common one-second frame brings the one-second spread close to the reference,
but worsens longer reversal behavior. The public mode-scale frame transfers
better, yet does not repair the very short load predictions. The amplitude
control itself improves some quantities, so the entire gain cannot be attributed
to response coordinates alone. More capacity regions and learned capacity
placement still show no consistent gain worth doubling the retained payload.

The eight-record results show the same horizon tradeoff. Common one-second
coordinates give 16.12–16.28 mV at the one-second load probe against 16.73 mV,
but 48.35–49.63 mV at the 10+10-second reversal against 34.02 mV. Public mode
scales give 16.27–16.43 mV and 37.44–37.90 mV respectively.

Agreement of standard deviations is insufficient. For public mode scales at
32 records, mean voltage differs from the saved reference by about
−0.39 to −0.42 mV at the one-second load, −0.71 to −0.95 mV at the ten-second
load, and +2.29 to +2.86 mV after the long reversal. The largest difference
among the retained 5/50/95% quantiles is about 3.05–3.94 mV after that reversal.
These are compression comparisons, not point errors against battery truth.
All sixteen marginal moments/quantiles and independent-population probe
summaries remain in the receipt. No finite predictive draw left physical support.

Held-out joint-density scores improve in every construction relative to the
voltage-only baseline. Mean improvement across the two held-out populations:

| Construction | Eight records | 32 records |
| --- | ---: | ---: |
| Physical amplitudes | 0.375–0.379 nats | 0.424–0.524 nats |
| Common 1-s response | 0.136–0.141 nats | 1.196–1.296 nats |
| Public mode scales | **1.072–1.082 nats** | **1.472–1.589 nats** |

Higher improvement is better here. These are differences of the same physical-
coordinate log density, not absolute KL divergence, observation NLL error or
a new physical acceptance threshold. The same finite reference populations are
being reused; this is not independent coverage validation.

## A principled next repair: fit the density we actually normalize

Construction currently fits an unbounded regression, then normalizes each
conditional on its physical support. That was declared in the plan and was
negligible in the voltage-only experiment, but is material for RC amplitudes.
For the slow forced-response conditional, mean removed Gaussian mass over
generated states is roughly 12–13% in public mode-scale cases and can reach
about 19–22% with the common one-second frame. Some rare states require much
larger corrections. The normalized distribution is well defined, but its
conditional means no longer match the unbounded projection.

The separate construction-only audit makes this precise. For normalized scalar
Gaussian negative log density, let `a=(lower-mu)/sigma`, `b=(upper-mu)/sigma`,
`Z=Phi(b)-Phi(a)`. The derivative for an intercept shift by one `sigma` is

```
mean((mu - observed_coordinate)/sigma + phi(a)/Z - phi(b)/Z).
```

The unbounded fit makes the first term average to zero. The normalizer term
does not vanish. In the 32-record public mode-scale construction, the mean
scaled intercept gradients across charts are about **0.088 and 0.194** for the
second and third forced-response coordinates. Log-scale gradients are also
nonzero. All 168 independent finite-difference checks agree with the analytic
derivatives; the maximum absolute discrepancy is about 6.85e-9.

This establishes a mismatch between the fitted objective and the density being
evaluated, not merely a need for more nodes. The next experiment should **fit
the bounded conditional likelihood including its support normalizer**, keeping
the same coordinates, region counts and storage. Compare against these frozen
projections and preserve multiple horizons. This would not automatically repair
all geometry, particularly the short-time ohmic/fast-RC relationship; it is a
specific defect to resolve before expanding the representation.

## Storage and work

| Retained numeric payload | Two regions | Four regions |
| --- | ---: | ---: |
| Conditional mixture | **2,496 B** | **4,960 B** |
| Fixed or adaptive atlas | **2,512 B** | **4,992 B** |

These counts include packed factors, conditional coefficients/log scales,
weights, atlas normalizers/edges and the 24-B response frame. With a 10,240-B
total target, they leave roughly **7.7 kB or 5.3 kB** for everything else.
That arithmetic is a planning estimate, not evidence the complete subsystem
fits. Conditional-bound fitting should need no additional retained coefficients,
although its construction/update workspace must be measured separately.

The implemented offline constructor needs at least **2,097,152 B** for its
construction and transformed-input arrays before other allocations. The whole
process peaked at **93,077,504 B RSS**, including controls and libraries.
The 36-case comparison took **8.53 host CPU seconds**, excluding controls and
the later support audit. It scored 294,912 held-out densities plus 1,152
serialization checks and evaluated 42,598,400 sample-wise predictive steps,
including baseline/reference extensions. Candidate inverse transforms used
30,670,848 sample-wise bisection iterations; baseline regeneration adds
10,223,616, disclosed separately. None of these is a new battery observation
or a measured Cortex-M23 cost.

No replacement is integrated into the rolling solver. Causal posterior updates,
physical aging, complete SRAM, long-duration accuracy and coverage remain open.

Reproduce into a new output directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -B -m experiments.rc_response_coordinates_001.compare \
  --output experiments/rc_response_coordinates_001/reproduction001
```
