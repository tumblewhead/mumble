# Joint probability codebooks: preserve tails as well as centroids

**Yes: probability mass can be represented geometrically and quantized into a
codebook.** This step implements a small joint monotone-aging/temperature model,
tests chronological elimination against unmerged paths, and compares probability
geometries. **2,064 finite checks pass** across three separately recorded stages.
The useful reference is now logarithmic relative-amplitude encoding; the first
apparently excellent mean-preserving codebook was insufficient for uncertainty.

The [main derivation](derivation.md), [tail/composition proof](tail_derivation.md),
[summary](summary.json), [main result](attempt001/result.json),
[tail audit](tails001/result.json), [16-bit result](log16_001/result.json) and
[integrity receipt](verification.json) contain the details. Earlier results are
preserved, including the preliminary rounding failure and its source.

## Geometry that is useful for compression

Square roots of the **joint probabilities** lie on a unit sphere. Distances
there bound total variation, which bounds errors in bounded queries. This keeps
all health/temperature/SOC/nuisance correlations; it does not multiply separate
marginal distributions.

However, linear amplitude quantization can misrepresent very small probabilities
while barely affecting a mean. Quantizing **logarithmic relative amplitudes**
also controls relative tail weights. The resulting log-density-ratio error is
unchanged by a common likelihood update and cannot increase under a common
stochastic transition. Each lossy encoding adds an explicit bounded error.
This gives us a composition rule with a mathematical error ledger.

A separate Gaussian-boundary example compresses two standardized thresholds and
a correlation into3B at8bits, or5B at12bits. Those are coordinates for one
conditional mass query. They do not encode a whole history or the dependence of
those coordinates on every retained parameter.

## What was implemented

The small standalone model retains monotone Q loss and R0 growth, uncertain
reversible temperature dependence, carried SOC, and three uncertain joint
three-RC/hysteresis candidates. Measured T(t) and the parameter laws g(T) are
separate. Its aging kernel is normalized, allows only forward damage, includes
a shared Q/R channel, and has explicit envelope boundaries. No nuisance value
is fixed to a synthetic truth. All observations are public fabricated inputs.

The aging rates and envelope behavior are **experimental assumptions**, not
calibration. Slow and accelerated stress cases are labeled separately. The
event model applies health transport at a boundary and freezes health during
each electrical interval; this is an explicit splitting approximation. The
eight-event fixtures cover250seconds of held-current intervals, not a complete
35Hz stream or a physical aging/convergence study.

The uncompressed finite-state filter agrees with explicit unmerged two-event
path sums to below8e-17TV and1.7e-16log evidence in the controls. Its stationary
response submodel matches the original C model to4.45e-16V at nominal-rate
intervals. These checks qualify elimination/response algebra under the stated
model, not the continuous posterior or physical aging law.

## Comparison and storage

The model has4,131 joint probability cells. The table reports maxima across six
short held-out fixture/rate combinations. Errors are against the **same-grid
uncompressed reference**, not against physical truth.

| Encoding | Probability payload | Maximum TV | Maximum Q mean distortion | Maximum SOC mean distortion |
| --- | ---: | ---: | ---: | ---: |
| Linear relative amplitude,8bit |4,131B|0.00541|0.0300%|0.00273pp|
| Linear relative amplitude,12bit |6,197B|0.000268|0.00155%|0.000117pp|
| Five joint shape templates |518B +864B dictionary|0.419|2.172%|2.164pp|
| Log relative amplitude,12bit |6,197B|0.0607|0.716%|0.0340pp|
| **Log relative amplitude,16bit** |**8,262B**|**0.00384**|**0.0296%**|**0.001743pp**|

TV is the maximum discrepancy in the probability of any event on this finite
joint grid. The template packet includes its exact support bitmap and index;
the dictionary retains full joint precision matrices and is frozen before
held-out evaluation. It is substantially too restrictive in these controls.
The implicit amplitude codebooks need no stored table of all codewords.

The16bit payload leaves1,978B below10KiB, **before** descriptors, source/error
ledgers and update workspace. It is not a complete SRAM fit and cannot simply
be added to the existing rolling estimator's footprint. The Python prototype
uses decoded probability arrays and cached dictionary/features well above the
target. This small6-coordinate discrete distribution also does not represent
the full40-coordinate continuous boundary model.

## Why the uncertainty audit changed the choice

In a sharply concentrated weak-excitation grid fixture, the linear12bit code
inflated SOC standard deviation by **118.37times**, despite its very small mean
error. The reference concentration is a finite-grid artifact, not calibrated
physical precision; the discrepancy still shows that mean error alone cannot
qualify an uncertainty representation.

An independent two-state counterexample is more decisive. A true rare mass
of1e-12 becomes about5.96e-8 under linear12bit encoding. After a future
likelihood favors that state, its correct posterior probability is0.009901,
but the encoded result is0.998326. Log16 gives0.0099183 instead.

Across the battery-grid controls, log16 preserved SOC standard deviation within
approximately **-0.193% to+0.255%** of the reference, while retaining the joint
covariance and event-probability checks. This supports using it as the next
diagnostic reference; it does not establish validated coverage.

![Joint mass and uncertainty comparisons](figures001/joint_mass_geometry.png)

[Exportable PDF](figures001/joint_mass_geometry.pdf).

## What remains unresolved

The largest current model issue is **SOC-grid transport**, not the selected
codebook. Refining SOC from17 to65nodes shifts the final temperature-reversal
result by about **2.30SOC percentage points and2.16% Q**. Barycentric deposition
preserves the instantaneous SOC mean but adds numerical diffusion, altering
future nonlinear likelihoods. Health, temperature and nuisance supports remain
discrete even at the finest SOC grid. No continuous-posterior convergence has
been established.

The log16 observed eight-event TV stays below0.003844; its conservative
accumulated bound stays below0.02157. An additive error ledger can still grow
over years. Idempotent encoding prevents drift from unchanged storage, but
repeated small physical changes can be lost if every update is immediately
quantized. Keeping accumulated physical transport separately is a candidate
repair only when its operators can legitimately compose; intervening
informative likelihoods generally prevent arbitrary reordering.

The next focused work is to replace or control the coarse SOC transport while
retaining its dependence on the capacity path and temperature, using the
tail-preserving log encoding as a diagnostic reference. Then reduce the number
of stored shape coordinates with a bounded residual, rather than discarding
cross terms or small probabilities. Rate calibration, full rolling integration,
complete memory/timing and ten-year accuracy remain open. Production C and
earlier artifacts are unchanged.

## Evidence and reproduction

The primary study has1,234checks, the separate tail audit589, and the16bit
follow-up241. Their measured CPU times were approximately0.445,0.465 and0.234s
on this host; these are qualification times, not estimator throughput. The
primary attempt preserves185earlier artifacts. Its original source snapshots,
dictionary and results remain unchanged by the follow-ups.

The initial rounding failure is recorded in
[development001/receipt.json](development001/receipt.json). Re-encoding its
normalized output100times changed TV by0.00141without new information. The
repaired relative-amplitude encodings pass idempotence checks. Later studies
were designed after earlier findings and are explicitly separate; no outcome
is retroactively described as preregistered.

With NumPy installed, run from the repository root using fresh output paths:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.joint_mass_codebook_001.qualify /tmp/mumble-mass-main
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.joint_mass_codebook_001.tail_checks /tmp/mumble-mass-tails
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.joint_mass_codebook_001.log16_checks /tmp/mumble-mass-log16
```

All refuse existing output directories. Supplemental checks bind the canonical
earlier attempts and frozen dictionary; they do not retrain it or rewrite them.
The modules are algebra/comparison interfaces, not a complete production source-
ownership API. Inputs, chronology, source hashes, assumptions and model limits
are recorded with the evidence.
