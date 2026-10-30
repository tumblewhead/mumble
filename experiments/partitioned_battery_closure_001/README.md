# Partitioned battery operator: derivation and finite checks

The battery closure derivation is complete for this step, and **844 finite
checks pass**. It identifies an exact conditional operator and the functions
that still require bounded approximation. It does not establish a closed
full-battery compressor or change the existing estimator.

The main result is a useful reduction: conditional on the seven SOC/capacity/
rate coordinates, voltage is affine in nine amplitude coordinates. Its entire
likelihood uses a **55-entry quadratic square root**, preserving every cross
term. But those entries vary with the uncertain conditioning coordinates:
they are functions, not 55 constants that summarize arbitrary battery history.

See the [derivation and ten claims](../../proofs/partitioned_battery_001/derivation.md),
[dependency map](../../proofs/partitioned_battery_001/dependencies.json),
[scope contract](../../proofs/partitioned_battery_001/contract.json) and
[machine summary](summary.json).

## What can remain exact

- RC free/forced and directional hysteresis transport are affine conditional
  on their rates. The amplitude chart retains R0, three R values, H, three
  entering RC voltages and B=H*h. It never requires division by H for original-
  chart likelihood queries, including H=0.
- Adjacent conditional blocks compose through the correct entering-state
  transform and shifted SOC. QR of the transformed factors preserves the
  joint likelihood and normalization. This is a prior-free evidence operator.
- Stationary all-prefix SOC support is retained using signed-charge extrema;
  final SOC alone is insufficient.
- The tanh component of OCV has an **exact Möbius transport map**. This answers
  the earlier coordinate question, but does not make accumulated squared
  residuals a finite closed likelihood family.

These conditional amplitude equations already exist in the C model. The new
work establishes their block composition, function dependencies, support and
measure obligations, nonclosure arguments and error-budget connection.

## Where the representation still needs approximation

Different OCV shifts introduce different rational poles; different RC sample
times give linearly independent functions of the uncertain rate. The written
proofs therefore rule out a fixed finite **additive likelihood basis** that is
exact for arbitrary such histories. They do not rule out useful bounded-error
compression or every other representation.

The underlying Gram coefficients have much smaller overlapping dependencies
than a generic seven-dimensional field:

| Nonlinear coordinates needed by a coefficient | Number of coefficients |
| --- | ---: |
| 0 | 1 |
| 1 | 15 |
| 2 | 19 |
| 3 | 18 |
| 4 | 2 |

The two four-coordinate functions couple OCV with hysteresis. RC/OCV and
RC/hysteresis cross terms need three coordinates. This structure supports
specialized approximations that retain the joint likelihood. It does not
support multiplying independent partition posteriors. QR factorization can
mix these dependencies; a stable structured storage scheme remains necessary.
Marginalizing amplitudes can also couple all seven nonlinear coordinates
through normalization. The four-coordinate limit applies to the underlying
likelihood coefficients, not to the full posterior.

The Möbius result uses the current illustrative tanh OCV law. A measured
piecewise-linear OCV table would have a different piecewise closure problem;
switching OCV laws to simplify compression would change the physical model.

## Aging and uncertainty

Two capacity paths with the same final Q can produce different SOC because
the current increments are divided by the capacity at their respective times.
Old states cannot be reconstructed from final health and total charge alone.

For RC aging, preserving voltage and preserving branch charge C*v give
different boundary maps. Both have conditional affine forms, but neither is
selected or calibrated here. The user-confirmed C=tau/R relation and proposed
relative envelope do not decide which convention describes the cell.

The existing bounded health kernels also retain state-dependent normalizers.
Two such transitions generally do not equal one truncated Gaussian transition
with doubled variance. The unbounded Gaussian prototype therefore remains a
reference building block, not the full aging model. Original prior support,
the B=H*h chart Jacobian and marginalization are retained as explicit
obligations; a conditional quadratic is not automatically a Gaussian posterior.

## An explicit error model

On a common exact supported domain, if predicted-voltage error is bounded by
epsilon_k and the supported residual by M_k, then

```
B_N = sum_k (M_k*epsilon_k + epsilon_k^2/2) / sigma_k^2
|approximate NLL - exact NLL| <= B_N
posterior mean error for query g <= range(g) * tanh(B_N/2)
```

The posterior result requires the same prior, transitions, support and exact
state/query maps. Approximate physical transport and support need separate
bounds. This supplies a route from an explicit compression allocation to an
allowable likelihood error; it does not equate the product's SOC/Q point-error
targets with a compression budget. No new numerical NLL threshold is selected.

It also makes the lifetime issue explicit: a fixed per-record response error
can consume increasing likelihood budget despite bounded storage and stable
RC endpoint errors. Physical RC relaxation does not remove already accumulated
likelihood errors. The next prototype must track that budget as it compacts.

## Executed finite controls

The [registered plan](plan.json) uses 12 conditioning points and eight amplitude
queries each on 48-record fabricated streams, including rest, current reversal,
irregular intervals, zero duration and H=0. The resulting durations are
17.58–21.32 seconds, solely algebra controls. No numerical estimator or
parameter-convergence claim follows.

[attempt001/result.json](attempt001/result.json) records all 844 passing checks:

| Control | Maximum observed difference |
| --- | ---: |
| Conditional voltage versus existing C physical recurrence | 1.78e-15 V |
| Endpoint SOC/RC/H*h quantities | 4.44e-16 in their respective units |
| Conditional NLL versus direct C-voltage residual sum | 7.45e-9 NLL |
| Merged-block NLL versus direct sum | 3.73e-9 NLL |
| Other chronological parenthesization versus direct sum | 5.59e-9 NLL |
| Möbius identities | 3.61e-16 |
| Bounded-kernel quadrature, 64 versus 128 nodes | 4.09e-14 density units |

Additional checks cover exact rational independence witnesses, unsupported
intermediate SOC, conditioning-argument/overlap rejection, the chart Jacobian,
equal-final-Q path differences, both proposed RC state maps, and the likelihood/
posterior-query inequalities on a finite common support. The finite kernel
fixture differs from its coarse replacement by 0.637 density units; it is a
dimensionless counterexample, not a calibrated battery aging rate.

The checks took about **0.21 CPU seconds** with **49.5 MB peak host RSS**,
excluding compilation. There were no fits, particles or canonical trajectories.
An initial import failed before reservation because SciPy was unavailable;
the moderate-tail scalar witness now uses standard-library erfc, with unchanged
formulas/tolerances. That launch failure and its source are preserved in
[development_import001/receipt.json](development_import001/receipt.json).
The C build, source snapshots and all earlier proof/reference hashes are retained.

## Storage and next implementation

One packed conditional square root is **440 B**. Including seven conditioning
coordinates and eight transport coefficients gives **560 B per node**, plus
**40 shared bytes** for charge/extrema/time/count: **600 B for one node** or
**9,000 B for sixteen**, before metadata, scratch, pending input and optimizer.
No node count or interpolation scheme is selected. These are conditional
likelihood objects, distinct from both the older 2,544-B posterior fit and the
4,488-B generic Gaussian operator. A complete 10 KiB fit remains open.

The [next gate](../../proofs/partitioned_battery_001/next_gate.json) is a bounded
**stationary operator-field prototype with a jointly accumulated residual-error
envelope**. It should preserve the exact amplitude structure, use the dependency
map to specialize nonlinear functions, and track outgoing-state and likelihood
defects separately. Domain exit, growing error budget and storage failure must
remain explicit. Full aging integration follows a justified state-transfer law
and a compatible uncertainty representation.

To repeat the finite controls into a new directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.partitioned_battery_closure_001.witnesses /tmp/mumble-closure-new
```
