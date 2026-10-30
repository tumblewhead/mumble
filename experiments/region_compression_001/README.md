# Three ways to compress the current joint posterior

All twelve offline comparisons completed: a statistical mixture, a fixed
probability atlas, and an atlas with self-organizing placement, each with two
and four regions at two saved boundaries. Ten numerical control tests passed.
**None of these variants is ready to carry the rolling estimator's history.**
They retain fairly similar SOC/capacity marginals but substantially broaden
voltage predictions. Preserving a full covariance matrix did not preserve the
nonlinear relationships that make those predictions precise.

This is the first representation test authorized by “try all three.” The
geometric arm adapts the proposed **likelihood atlas into a probability atlas**
so that every arm compresses the same existing posterior. It does not implement
the earlier likelihood-atlas transport contract. The self-organizing arm tests
a restricted chain along capacity, not a general sixteen-dimensional network.
Neither simplification excludes the broader approach if this variant fails.

The [frozen plan](plan.json), [primary results](attempt001/result.json),
[numerical controls](attempt001/controls.txt), and
[separate diagnostic](audit001/result.json) record the evidence. Existing
posterior files and their original receipts remain unchanged; their identities
and the executed source are bound in the [reservation](attempt001/reservation.json).

## What was compared

The reference uses saved full-joint posterior populations from the 8-record
and 32-record studies. Both passed their original finite moment checks; neither
has validated coverage or an exact marginal density. These are only **0.229 s
and 0.914 s of simulated history**, not a capacity-learning or lifetime test.
The 32-record source is the user's 96-move rerun. No particle inference was
rerun, and no truth data were read.

For each boundary, the first two independently seeded 4,096-member populations
construct the message. The last two evaluate it. Members within a population
are dependent; population-to-population differences are reported rather than
treating all members as independent confidence samples. Construction receives
only the current sixteen quantities, not latent health paths or future data.

| Arm | Representation | Region placement |
| --- | --- | --- |
| Statistical mixture | Weighted full16 Gaussians in bounded-logit coordinates | Fixed equal-width log-capacity bins assign construction samples; fitted components have overlapping support |
| Geometric probability atlas | Disjoint log-capacity charts; normalized bounded quadratic capacity density and a full15 conditional Gaussian for everything else | Fixed equal-width log-capacity intervals |
| Self-organizing atlas | Exactly the same conditional density as the geometric arm | Sixteen fixed Lloyd passes move an ordered chain along log-capacity using construction samples only |

Every physical coordinate remains uncertain. Public support is enforced by
bijective transforms and explicit chart domains, with density Jacobians.
Chart/component masses sum to one. There is no covariance repair, clipped
sample, forgetting factor, learned aging rate, nuisance freezing or truth-based
centering. Duplicating the construction samples leaves uncertainty unchanged.
Unsupported/singular cases report unavailable and would not stop the census;
none occurred in the twelve tested cases.

All three messages already own the initial prior and the source's observation
and physical-transition intervals. Their regions describe alternative mass of
**one posterior**. Multiplying the regions, reapplying that prior, or replaying
the owned observations would be incorrect. Refitting these messages from saved
samples is an offline operation; no causal update or merge algebra is supplied.

## Results

At the 32-record boundary, the following uncertainties are standard deviations
of predicted noiseless voltage, before adding measurement noise. The load probe
applies +0.05 A for one second using the existing physical equations. A rest
probe and a load/reversal probe are also retained in the receipt. Health is held
constant for these short predictive probes to isolate compression effects.

| Representation | Regions | Retained numeric payload | Boundary rest-voltage SD | Load-probe voltage SD |
| --- | ---: | ---: | ---: | ---: |
| Saved held-out posterior | — | Reference samples | **1.968 mV** | **3.070 mV** |
| Statistical mixture | 2 | 2,472 B | 13.578 mV | 14.617 mV |
| Statistical mixture | 4 | 4,936 B | 13.612 mV | 14.546 mV |
| Fixed probability atlas | 2 | 2,488 B | 13.675 mV | 14.630 mV |
| Fixed probability atlas | 4 | 4,968 B | 13.804 mV | 14.766 mV |
| Self-organizing atlas | 2 | 2,488 B | 13.623 mV | 14.559 mV |
| Self-organizing atlas | 4 | 4,968 B | 13.632 mV | 14.595 mV |

All six load predictions are **4.74–4.81 times broader** than the saved
reference in standard deviation. At eight records, the boundary voltage SD
broadens from 0.797 mV to 16.78–16.98 mV. No predictive draw left the declared
physical support in these brief probes; this finite check does not establish
support preservation for future arbitrary trajectories.

Meanwhile, at 32 records the saved SOC SD is 0.0240 and capacity SD is
0.01786 Ah. Candidate SOC SDs are 0.02341–0.02386 and capacity SDs are
0.01789–0.01919 Ah. These comparatively similar marginal uncertainties would
hide the voltage failure if we judged compression only by SOC/capacity plots.
R0 variance is also inflated: about 2.20–2.28 times the reference at 32 records.

Held-out joint density gives a more mixed ranking. These are mean negative log
densities in the same sixteen physical coordinates, averaged over the two
held-out populations; lower is better. Their absolute values depend on units
and are **not** a KL divergence, an observation NLL error or a physical gate.

| Arm | Regions | 8-record score | 32-record score |
| --- | ---: | ---: | ---: |
| Statistical mixture | 2 | −12.1739 | −20.1550 |
| Statistical mixture | 4 | −12.1361 | −20.1539 |
| Fixed probability atlas | 2 | −12.2594 | −20.1273 |
| Fixed probability atlas | 4 | −12.2233 | −20.0397 |
| Self-organizing atlas | 2 | −12.2533 | −20.1288 |
| Self-organizing atlas | 4 | −12.2198 | −20.0565 |

There is no consistent winner across the boundaries, and no demonstrated
benefit from spending twice the region memory here. This is a finite comparison
of the specified constructions, not an optimized search over each family.
There is no new 0.1-NLL acceptance threshold.

## Why full covariance was insufficient

The separate audit verifies analytically from the stored factors that all
three methods preserve the construction mean and covariance of the fifteen
non-capacity logits, up to numerical error. The mixture preserves all sixteen;
the atlas additionally preserves the capacity chart coordinate's first two
moments and cross-covariance. The largest standardized covariance discrepancy
in this audit is about 1.1e-12. The voltage failure therefore cannot be repaired
merely by restoring cross terms already present in those matrices.

At zero applied current, the physical relation is

\[
V = \operatorname{OCV}(z) - (v_1+v_2+v_3) - Hh.
\]

Write this exactly as a local linear prediction in transformed coordinates
plus its nonlinear remainder: `V = V_linear + remainder`. Then

\[
\operatorname{Var}(V) = \operatorname{Var}(V_{linear})
 + \operatorname{Var}(remainder)
 + 2\operatorname{Cov}(V_{linear},remainder).
\]

In the eight-record construction posterior, the linear part has SD
11.984 mV and the nonlinear remainder 11.956 mV. Their correlation is
**−0.9978**, so together the voltage SD is only **0.792 mV**. The corresponding
candidate correlations are only about **−0.05 to −0.07**. The marginal sizes
remain comparable but their cancellation is lost. The held-out populations
show the same effect. At 32 records the construction correlation is −0.9776,
versus approximately −0.07 to −0.09 in these candidates.

Thus these distributions occupy a narrow curved region in the chosen
coordinates. Matching its mean and covariance spreads probability away from
that region. Partitioning along capacity does little to resolve this curvature.
This diagnostic is evidence for changing the coordinate/density construction,
not proof that small mixtures, geometric methods or self-organizing networks
are fundamentally unsuitable.

## Work and memory

The twelve cases took about **0.421 host CPU seconds**, including source loading
and reporting but excluding numerical controls. The run evaluated 98,304
held-out joint densities, drew 16,384 samples per candidate and performed
851,968 sample-wise predictive steps. There were no fresh posterior-inference
steps. This measures offline compression work, not a streaming estimator's
per-record cost or Cortex-M23 execution.

The numeric payload figures include packed triangular factors, means or
conditional slopes, weights, atlas normalizers and interval edges. The stored
JSON also carries support and ownership metadata. The numeric figures omit
that metadata, Python object overhead, the rolling solver, queues, stack and
update workspace; they are not complete SRAM layouts.

The implemented builder needs an 8,192×16 construction matrix and a unit-space
matrix simultaneously: already **2,097,152 B**, before its other arrays and
retained payload. The whole process, including controls and library overhead,
peaked at **92,073,984 B RSS**. A future bounded builder must be designed and
accounted for separately. No complete 10,240-B implementation is demonstrated.

## Next experiment

Test a **physics-conditioned coordinate system** at the same small region
counts before adding nodes or extending the trajectory. For example, replace
SOC as a coordinate with the predicted boundary rest voltage while retaining
the other fifteen variables. Given those variables, SOC is recoverable uniquely:
`dOCV/dSOC = 1.15 + 0.64 sech²(8(SOC−0.5)) > 0`. This could represent the narrow
voltage direction directly instead of asking affine Gaussian covariance to
encode its curvature.

That proposal requires the exact inverse, Jacobian, and **state-dependent
voltage support normalization**. It must preserve capacity/RC/hysteresis
alternatives and be checked against future probes; matching boundary voltage
alone is insufficient. Adaptive placement should then be tested against the
remaining physical predictive error, rather than assuming capacity distance
is the useful organizing metric. These are proposed tests, not repairs already
applied to this experiment.

After a representation passes those checks, implement its causal ownership and
physical-health update with complete working-memory accounting, then run the
four-hour rolling comparison. Starting that trajectory with the current
representations would obscure a compression defect already visible here.

To reproduce in a new directory from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -B -m experiments.region_compression_001.compare \
  --output experiments/region_compression_001/reproduction001
```

Existing output directories are never overwritten. The separately recorded
post-comparison audit was run with `python3 -B -m
experiments.region_compression_001.audit` under the same single-thread settings.
