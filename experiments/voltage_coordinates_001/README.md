# Physical voltage coordinates repair the boundary distribution

The proposed coordinate change substantially improves all three tested
representations at the same retained numeric size. At the 32-record boundary,
predicted rest-voltage standard deviation changes from **13.6–13.8 mV to
1.970–2.004 mV**, compared with **1.968 mV** in the saved reference. The one-second
load prediction also improves: its excess variance relative to the reference
falls by **88.2–89.2%**. It still remains too broad to treat this representation
as a qualified history replacement.

All twelve matched cases completed. Twenty numerical control tests passed,
including ten inherited controls and ten for the new coordinate, Jacobian,
conditional normalization, sampler and inverse. Original artifacts remain
unchanged. No particle inference, rolling estimation or physical aging update
was rerun. The reference prefixes still span only **0.229 and 0.914 seconds**.

The [derivation](derivation.md), [frozen plan](plan.json),
[primary results](attempt001/result.json), [controls](attempt001/controls.txt),
and [physical-response audit](audit001/result.json) provide the detailed evidence.
The [prior study](../region_compression_001/README.md) remains the comparator.

## What changed

Replace the SOC logit with the physical predicted instantaneous rest voltage

```
w = OCV(SOC) - v1 - v2 - v3 - H*h.
```

Keep the other fifteen physical quantities uncertain. Given them, SOC is
recoverable uniquely because the existing OCV curve has positive derivative
everywhere on its support. The inverse is solved with bounded bisection.

The allowed voltage interval depends on RC voltage and hysteresis. Each region
therefore models the other quantities first and voltage conditionally, with a
Gaussian conditional normalized over that exact dependent interval. The
physical density includes the OCV derivative and coordinate Jacobians.
Simply imposing a fixed voltage box or omitting the conditional normalizer
would define a different, incorrectly normalized density.

Construction projects untruncated moments/regressions and then applies this
conditional support normalization. It is not a maximum-likelihood fit of the
truncated family. No support correction was resolved in binary64 for the
finite construction, held-out and generated samples in these cases. This does
not mean Gaussian mass outside support is mathematically zero. Numerical
controls separately exercise substantial truncation, narrow intervals and
extreme tails; no sample clipping is used.

All other comparison choices are unchanged: the three arms, two/four regions,
capacity placement, source populations, construction/evaluation split,
16,384 draws per case, and stationary rest/load/reversal probes. The original
held-out populations are reused for this predefined hypothesis; this is not
a new independent validation campaign. Source populations passed finite
moment checks, not full density or coverage validation.

Each message owns its original prior and source intervals once. The new voltage
coordinate is a prediction, not a measurement or additional evidence. These
remain posterior snapshots, not likelihood factors that can be substituted
into the rolling caller without an ownership/update contract change.

## Matched results

The following numbers are standard deviations of noiseless predictions at the
32-record boundary and after the same one-second +0.05 A probe. They are not
point-estimation errors against battery truth.

| Arm | Regions | Numeric payload | New boundary SD | Old load SD | New load SD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Saved reference | — | Reference samples | **1.968 mV** | **3.070 mV** | **3.070 mV** |
| Statistical mixture | 2 | 2,472 B | 1.970 mV | 14.617 mV | 5.746 mV |
| Statistical mixture | 4 | 4,936 B | 1.976 mV | 14.546 mV | 5.725 mV |
| Fixed probability atlas | 2 | 2,488 B | 1.994 mV | 14.630 mV | 5.607 mV |
| Fixed probability atlas | 4 | 4,968 B | 1.982 mV | 14.766 mV | 5.710 mV |
| Self-organizing atlas | 2 | 2,488 B | 2.004 mV | 14.559 mV | 5.770 mV |
| Self-organizing atlas | 4 | 4,968 B | 1.988 mV | 14.595 mV | 5.679 mV |

At eight records, boundary voltage SD improves from 16.78–16.98 mV to
**0.788–0.804 mV**, against the reference's **0.797 mV**. The load probe improves
from 25.91–26.33 mV to **19.10–19.30 mV**, against **16.73 mV**.

Every candidate improves its held-out joint log-density score in both
populations: about **2.82–2.83 nats per current-state sample** at eight records
and **3.02–3.22 nats** at 32 records. These are relative scores of the same
physical-coordinate density, not observation NLL residuals, absolute KL bounds,
or a new acceptance threshold.

At 32 records, candidate SOC SD is 0.02427–0.02474 versus 0.02400 in the
reference. Capacity SD is 0.01779–0.01922 Ah versus 0.01786 Ah. The R0 marginal
remains too broad, as expected: its representation has not changed. All sixteen
means, covariances and marginal quantiles are retained in the primary receipt.
No predictive draw lost physical support in the brief probes.

More capacity regions and adaptive scalar placement still show no consistent
benefit. The large common improvement comes from the physical coordinate and
its conditional density, rather than additional region memory.

## Where the remaining discrepancy comes from

A separate post-comparison audit decomposes the exact one-second voltage into
boundary voltage, OCV change from charge, free RC release, forced RC response,
ohmic drop and hysteresis change. For each RC mode,

```
release_i = (1 - exp(-dt/tau_i)) * v_i
forced_i  = -I * (1 - exp(-dt/tau_i)) * R_i.
```

The full covariance of these terms, including every signed cross term,
reconstructs predictive voltage variance. The audit checks that this additive
expression matches the inherited physical predictor; it makes no correction
to the candidate distribution.

At 32 records, reference load variance is **9.426 mV²**, while the new variants
give **31.43–33.29 mV²**. In the declared symmetric covariance allocation, free
RC release contributes about **11.1–12.1 mV²** of the excess and forced RC
response **10.4–11.7 mV²**. Ohmic drop contributes only **0.75–0.98 mV²** in
that allocation; the boundary contribution is slightly negative. Contributions
depend on the stated partition and can be signed; this is not unique causal
attribution or permission to freeze nuisance parameters.

The rest-only probe isolates this further. Its reference variance is
**7.872 mV²**, while candidates give **19.51–20.52 mV²**, with nearly all the
excess assigned to free RC release. The two independent reference populations
give 7.682 and 8.031 mV². This gap is much larger than their observed difference.

The boundary relationship is now represented well, but the remaining Gaussian
coordinates still spread probability away from nonlinear relationships between
RC time constants, carried voltages and resistances. Matching boundary voltage
alone therefore does not qualify future predictions.

## Resources and next step

The matched run took about **0.731 host CPU seconds**, excluding its controls
and the later audit. It scored 98,304 held-out densities, generated 196,608
samples, used 10,223,616 sample-wise OCV bisection iterations, and evaluated
786,432 predictive sample-steps. Another 384 density queries checked serialized
message parity; these are control work outside the scored-point counter.
This is offline compression cost, not per-record streaming performance.

Retained numeric payload is identical to the previous variants. Complete
firmware memory remains unqualified: the implemented builder already retains
over 2 MiB of construction/unit-coordinate arrays, and process peak RSS was
**93,224,960 B**, including controls and libraries. Source ownership metadata,
query/fit workspace, solver, queue and stack cannot be inferred from the small
factor payload.

The next matched experiment should retain this voltage coordinate and test
**physical RC response coordinates**, with the time constants still uncertain.
For a declared response interval, the release and forced-response expressions
above are invertible in `v_i` and `R_i` conditional on `tau_i`. Their support
depends on `tau_i`, so the same normalization care is required. Multiple probe
timescales should test whether the improvement transfers beyond the one-second
probe; a single prediction coordinate is insufficient evidence for long-term
retention. This next change is proposed, not implemented here.

After those representation checks, causal posterior transport/aging and a
complete bounded-memory update remain prerequisites for the four-hour rolling
comparison. The current result is a successful boundary-coordinate repair,
with a localized and still substantial future-response discrepancy.

Reproduce without overwriting saved evidence:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -B -m experiments.voltage_coordinates_001.compare \
  --output experiments/voltage_coordinates_001/reproduction001
```
