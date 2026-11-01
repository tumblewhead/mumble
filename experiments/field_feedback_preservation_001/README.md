# Preserve joint history between field refreshes

The fixed-origin square-root prototype repairs the weak-case narrowing in the
tested controls. Five short replays and an hour of weak use complete without
query or refresh failures. Production estimation and campaign defaults are
unchanged. This is a stationary-cell desktop prototype, not M23 firmware.

[Qualification receipt](qualification.json), [hour-long comparison plot](report001/weak_feedback.png),
and [separate postfit scoring](report001/scores.json) accompany the source.
The parent evidence is [the uncertainty study](../uncertainty_weak_stimulus_001/README.md),
preserved at commit `18878d1`. Work branch: `experiment/field-feedback-preservation-001`.

## What caused the narrowing?

The previous short-suffix fits stalled near stationarity. An independent
observed-Newton continuation of their analytic gradients now resolves them.
Three starts reach two distinct local stationary modes, both with positive
observed Hessians. Their costs differ by about0.0248; neither is a global
posterior certificate. Finite-difference Hessians at two step sizes agree to
about1.2e-6 relative norm.

| Same38.4-second suffix | Q local GN width, percent |
|---|---:|
| Field message before suffix | 4.278 |
| One joint fit with that Gaussian boundary, lower-cost local mode | 1.393 |
| Other local mode | 1.715 |
| Existing repeated rolling updates | 1.115 |
| Full-history field at endpoint | 4.303 |

Observed-Hessian widths at the two stationary modes are about1.522% and1.905%,
respectively. Thus switching from GN to observed curvature does not reproduce
the full field's local width here. Multiple modes remain relevant; these
numbers are local precision, not exact marginal posterior uncertainty.
The loss occurs even without repeated16-record posterior replacements, with
additional narrowing in the rolling arm. It is not solely an iteration-cap
failure or a missed refresh.

There is a geometric reason to suspect the Gaussian boundary representation.
After the initial RC states have decayed, the saved endpoint covariance root
has numerical rank13 in the16-coordinate chart: three singular values are
approximately1e-17. The remaining dynamic states lie on nonlinear functions
of the original parameters. A first-order Gaussian represents the tangent
plane to that curved set.

For a state map `y=T(x)` and an uncertain displacement `d`,

```
T(x+d) = T(x) + DT(x)d + 1/2 D²T(x)[d,d] + ...
```

The transported Gaussian retains `DT(x)d` but discards curvature normal to
its range. In the weak case, displacements along the fitted Q direction show
normal residuals scaling nearly quadratically: about2.18e-9,8.73e-9,3.49e-8
in the mixed endpoint-chart norm at0.25,0.5,1 local SD. These greatly exceed
the near-null numerical directions. Tiny absolute state curvature can therefore
matter when the Gaussian has essentially zero width normal to its tangent.
This is a local diagnostic of a representation defect, not a ten-year proof
or a quantified decomposition of global posterior error.

## Repair and evidence ownership

Keep inference in the field's original parameter coordinates between scheduled
refreshes. Use the endpoint Gaussian only for reporting. It never becomes the
prior for the next history update.

Let `w` be original-prior-whitened coordinates and `w0` the latest field fit.
At that anchor, linearize the original prior and all accumulated field residuals.
Retain a joint augmented square-root factor in16 coordinates plus residual.
For each new response-row block `E`, compute

```
r = E phi(w0)
B = E Dphi(w0)
factor <- QR([factor; B r])
delta  <- solve(factor[:16,:16], -factor[:16,16])
w      <- w0 + delta
```

The initial factor includes the original prior once. New rows own only the new
suffix; no posterior is multiplied by replayed evidence. The field continues
to retain all observations in its nonlinear likelihood representation. At the
existing scheduled refresh, rebuild the tangent from that field and the same
original prior, using the candidate's own fit as initialization. The oracle
does not initialize the candidate. A nonlinear state-map query produces the
current endpoint and full joint covariance for readout.

The frozen tangent approximates the likelihood within one refresh interval;
its Gaussian readout is not recursively re-ingested as history. It adds no
variance floor, forgetting, health decay, diagonalization or truth correction.
Source/count guards prevent duplicate or skipped row ownership and mismatched
readout boundaries. Domain or solve failures remain explicit and unresolved.
Production fallback behavior is not yet integrated.

## Tests and comparisons

Six targeted tests pass: independent batch linearized least squares with full
covariance; evidence partition invariance; duplicate/skipped input rejection;
source/readout boundary binding; rest-from-origin Q null information; and
observed-Newton stationarity against a known nonquadratic optimum.

The five short tests reuse the registered35/50Hz, two-cell, two-load,
2/4/20mV witnesses. Four cover one field interval; the weak case covers the
same38.4seconds as before. All three arms start from a fresh causal fit of
the same prefix. They compare original rolling updates, full-field queries
after every16 records (oracle), and the candidate. Owner-run short endpoints
are measured before their scheduled refresh; refreshing would replace them
with the full-field result. No later observations initialize an earlier fit.

Across these controls, maximum candidate/oracle difference is **0.00602% Q**
and **0.000153 SOC percentage points**. Local Q width ratios range from
**0.9806 to1.0091**. In the weak case at four hours:

| Method | Q error vs truth | Q local width |
|---|---:|---:|
| Rolling between field refreshes | −1.8938% | 1.1152% |
| Fixed-origin candidate | +0.2775% | 4.2775% |
| Frequent-field-query oracle | +0.2760% | 4.3033% |

The longer weak replay starts at the scheduled boundary just before3.5hours
and ends just before4.5hours: **3,648.46seconds,7,981windows,60refreshes**.
Maximum candidate/oracle differences are **0.03583% Q** and **0.000468 SOC pp**;
Q width ratios stay **0.9409–1.0793**. There are no query or refresh failures.
The original rolling comparator is restarted with the same causal field
message at each scheduled boundary, isolating between-refresh behavior.
All boundary and intermediate readouts are shown, including before replacements.

Truth is opened only by the separate reporting process after fits are frozen.
The candidate's point accuracy does not make weakly identified Q certain.
The oracle is the existing approximate field, not exact retained data or a
calibrated posterior. Hysteresis field bias, aging and long-duration coverage
remain open. This does not replace the planned24/72-hour gradient-growth study.

## Cost and storage

On the final isolated short weak replay, candidate query/update time is about
**0.60ms per16-record block**, versus **3.67ms** for nonlinear field refitting
and readout, and **0.064ms** for the existing C rolling core. Shared field
accumulation adds about0.326ms per block in this diagnostic. Thus the query
path is about6.1times faster than frequent full refits, but about9.3times slower
than C rolling before accumulation. The hour-long measurement has similar
ratios. These are Python/C host measurements, not target timings or a promised
campaign speedup.

Current prototypes use full82-coordinate field QR updates each block for the
shared oracle. The production adapter batches those updates. That cost and
Python overhead must be separated in a native implementation; this experiment
does not establish a faster complete campaign runner.

Additional packed numeric payload in the literal candidate is **12,504B**:

| Item | Bytes |
|---|---:|
| Joint17-column triangular tangent factor | 1,224 |
| Anchor coordinates | 128 |
| Feature values | 656 |
| Dense82-by16 feature derivative cache | 10,496 |

Together with the existing28,864B field payload/live state, that is **41,368B**
before prior, metadata and workspace. Regenerating or structurally encoding the
derivative cache would leave **2,008B** of additional persistent payload, but
that is an implementation option, not a measured complete SRAM result. Native
workspace/lifetime design and field compression remain necessary for M23.

## Reproduction and next step

Use this worktree with the parent study's local observation caches present:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest \
  experiments.field_feedback_preservation_001.test_numerics -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m \
  experiments.field_feedback_preservation_001.diagnose_boundary \
  --out experiments/field_feedback_preservation_001/gaussian_reproduction
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m \
  experiments.field_feedback_preservation_001.run \
  --out experiments/field_feedback_preservation_001/short_reproduction
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m \
  experiments.field_feedback_preservation_001.run --extended --labels weak_B_cycle \
  --out experiments/field_feedback_preservation_001/extended_reproduction
```

The initial normal-equation prototype (`short001`), square-root runs (`short002`,
`extended001`) and final source-binding guard replay (`guard003`) are preserved
with source identities. The guard replay reproduces the square-root weak result
exactly. Earlier unresolved Gaussian fits are also preserved; `gaussian002`
adds the stationary solutions without rewriting them.

Next: port the small update/readout kernel with explicit workspace and a
structured derivative cache, then add an opt-in campaign backend with checkpoint
parity. Longer mixed/weak-load tests should precede default promotion. Keep the
hysteresis approximation-growth investigation separate from this feedback repair.
