# Physical RC scale repair and registered adaptations

**The proposed scale law is implemented and tested, but is not a general
repair.** Forcing physical-v scaling improves the8record slow response and
worsens32record results. A derived combination of physical and response
information gives a substantial partial repair at8records. The32record
variance discrepancy and some shorter-horizon regressions remain, so no
candidate replaces the rolling estimator or receives deployment qualification.

All **66 controls** pass in the final suite. All **28 unique conditional fits**
meet their registered numerical gradient tolerance; the maximum residual is
9.17e-8 against1e-7. The three comparisons pass1,580case checks. A separate
[density audit](fit_density_audit.json) reconstructs all28conditional objectives
from serialized parameters, physical support and normalizers. This does not
establish a global mixture optimum, physical identification or coverage.

The original attempt, adaptations, code and source hashes are preserved in
the [verification receipt](verification.json). A pre-battery control initially
used a2e-17absolute QR reconstruction tolerance; its2.08e-17difference failed.
The [development receipt](development_controls/receipt.json) preserves the
original test and documents replacement by a scale-aware machine-epsilon
check. No estimator change or battery evaluation informed that correction.

The [first plan](plan.json) and [derivation](derivation.md) fit the selected
carried RC density using `F=a(tau)*v` and scale `a(tau)*s`. The intercept column
is divided by a with every other feature; no extra intercept or target
recentering changes the mean family. Support and Jacobian factors remain
normalized. The slow-only and all-carried arms share the same slow fits.
Results are preserved in [attempt001](attempt001/result.json).

| Prefix | Model | Reversal SD | Excess variance vs construction |
|---|---|---:|---:|
| 8 | Saved baseline | 37.383 mV | +288.154 mV² |
| 8 | Physical scale, slow only | 33.985 mV | +45.593 mV² |
| 8 | Physical scale, all three | 36.965 mV | +257.032 mV² |
| 8 | Combined information | 33.537 mV | +15.391 mV² |
| 8 | Added mean compensation | 33.160 mV | −9.796 mV² |
| 32 | Saved baseline | 24.679 mV | +73.677 mV² |
| 32 | Physical scale, slow only | 26.051 mV | +143.257 mV² |
| 32 | Physical scale, all three | 27.449 mV | +218.081 mV² |
| 32 | Combined information | 24.523 mV | +65.986 mV² |
| 32 | Added mean compensation | 24.655 mV | +72.459 mV² |

Construction/reference reversal SDs are33.307/34.018mV at8records and
23.138/23.117mV at32records. Each model has four batches of16,384draws; all
thirteen probes and the full covariance decomposition are recorded in the
[summary](summary.json). Batch ranges are descriptive, not confidence bounds.

## Learning from the failed endpoint

The full physical scale assumes one information geometry. A Gaussian quadratic
in physical v and another in F contribute precision as

```
precision_F(tau) = J_F + J_v/a(tau)²,   J_F,J_v >= 0.
```

This gives a normalized family containing both tested endpoints. The
[registered adaptation](combined_plan.json) learns their balance from
construction samples, with the [derivation](combined_derivation.md) explicitly
distinguishing this posterior representation from adding another prior.
It introduces no arbitrary aging rate or forgetting exponent.

The learned physical-information fractions at the public reference scale are:

| Prefix/component | Fast RC | Middle RC | Slow RC |
|---|---:|---:|---:|
| 8/0 | 0 | 0 | 0.782 |
| 8/1 | 0 | 0 | 0.750 |
| 32/0 | 0.333 | 0 | 0.037 |
| 32/1 | 0.222 | 0 | 0 |

The [combined result](combined001/result.json) reduces the absolute reversal
variance discrepancy against construction by **94.66% at8records** and
**10.44% at32records**. Its amplitude–gain covariance error falls from279.970
to2.884mV² at8records, supporting the mechanism identified by the symbolic
study. At32records that term remains55.414mV² versus60.923mV² before.

There are regressions. At8records, one-second load SD increases from16.611
to17.181mV against a16.728mV heldout reference. The0.1second load SD increases
from5.195to5.320mV against5.013mV. At32records, one-second load remains close
(3.085mV versus3.070mV reference), while reversal SD remains about6.08%high.
At32records heldout NLD improves0.002624 in one population and worsens0.000501
in the other. A favorable long probe does not qualify the full message.

## Remaining conditioning error and a final controlled test

A [construction-only diagnostic](conditioning001/result.json) integrates the
slow conditional analytically. At32records after the information repair,
carried-sum variance discrepancy separates into18.83mV² from conditional fit,
40.10mV² from generated conditioning-variable distribution, and−0.13mV² from
draw variation. This uses fixed construction component memberships and model
latent labels, and concerns carried response rather than complete voltage.

Physical voltage compensation suggests two additional slow-mean features:
`F1*(a3/a1-1)` and `F2*(a3/a2-1)`. Their zero-coefficient limit recovers the
combined model. The [separate derivation](compensation_derivation.md),
[frozen plan](compensation_plan.json) and
[result](compensation001/result.json) preserve this final test. It improves
joint density scores overall but does not consistently improve predicted
variance. At32records its reversal variance nearly returns to baseline.
The extra mean terms are therefore **not recommended for promotion**.

The combined-information family is the smaller partial research candidate.
The next target is generated-prefix distribution and its carried-state
coupling, with all response horizons and fresh independent source populations
required before promotion. Later candidates here were designed after earlier
heldout results; these reused populations provide exploratory comparisons,
not fresh confirmation. Source disagreement is never corrected using truth or
by shifting fits toward heldout means.

## Storage and scope

| Layout | Retained numeric bytes |
|---|---:|
| Original / forced physical scale | 2,496 |
| Combined information | **2,544** |
| Combined information + mean compensation | 2,576 |

The combined family adds one scalar per carried conditional: six binary64
scalars total, **48bytes**. Mean compensation adds another32bytes. Metadata,
source ownership, fitting/query workspace, queues and stack remain additional;
complete10KiB SRAM is not qualified. Maximum measured desktop process RSS is
97,599,488bytes. The combined comparison takes1.35CPU seconds, including0.208
seconds for its12fits on this host, excluding controls and closeout. It is an
offline measurement, not Cortex-M23 or rolling-stream timing.

Source histories remain0.229/0.914seconds. No new particle inference, causal
history update, physical aging, long-duration stability or coverage study was
performed. The rolling solver and all earlier evidence are unchanged.

Reproduce any comparison into a fresh directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python3 -B -m experiments.physical_rc_scale_001.compare_combined \
  --output experiments/physical_rc_scale_001/reproduction001
```

Use `compare` for the original endpoint comparison or `compare_compensation`
for the final mean-feature experiment. Existing output paths are exclusive.
