# Structured joint history: boundary storage and constrained elimination

The physical dependency review and joint elimination prototype are complete;
**174 finite checks pass**. The result is a more precise storage contract:
keep a joint boundary factor, including its nonquadratic support/normalization
term. Physical partitioning helps evaluate response functions, but does not
justify independent parameter posteriors. No production estimator was changed.

See the [derivation](derivation.md), [support/error addendum](support_addendum.md),
[registered plan](plan.json), [main checks](attempt001/result.json),
[support checks](support001/result.json), [summary](summary.json) and
[integrity receipt](verification.json).

## SpanishCastleMagic findings

The [linked handoff](https://github.com/tumblewhead/naia/blob/9cb846ef5e9838100f9c7d5156bb2fb01b90d957/experiments/scm_eh1_capacity_information_tail_correction_v1/OWNER_RUN.md)
is an unexecuted tail-correction candidate at the reviewed revision. Its frozen
V3 dependency retains shared12-coordinate constraints across OCV, temperature,
capacity, RC and hysteresis quantities. It also checks that one common
candidate contains a known synthetic witness; separate marginal containment
does not suffice. These are useful design lessons for our joint history.

Its [saved A informative arm](https://github.com/tumblewhead/naia/blob/9cb846ef5e9838100f9c7d5156bb2fb01b90d957/experiments/scm_eh1_capacity_information_v1/owner_evidence/owner_capacity_info_20261027T030343Z/full/cell_A_informative/SUMMARY.json)
reports Q support shrinking from48–84mAh to50.0572–71.2327mAh: **41.18% width
reduction** over1,170simulated seconds. This is support contraction, not capacity
point accuracy or posterior coverage. The original matrix stopped during the A
zero-current arm at a subnormal RC reference-point miss; B arms were not reached.
The proposed correction has no completed result at this revision.

SCM's exact-rational LP certificates apply to the represented necessary
constraints. The rows are not an exact nonlinear feasible set, a likelihood
posterior or an indefinitely sufficient history. Resource limits and discarded
additional rows are explicit. We reviewed sources and saved summaries, verified
all **nine applicable selected lock identities**, and retained12 retrieved files
with [pinned provenance](sources.json). We did not rerun or independently
reproduce SCM trajectories, audit all156 evidence files, or execute OWNER_RUN.

## What the new controls establish

- The actual fixed-eta battery amplitude likelihood is jointly coupled: its
  nine-coordinate Gram matrix is dense in the excited control.
- Block square-root partitioning retains likelihood, cross covariance, residual
  energy and Gaussian integration determinants. It saves no generic storage
  unless variables are actually retired. Rank failures remain explicit.
- Chronological elimination can retain a fixed-dimensional boundary under a
  specified Markov model. A fixed-dimensional domain does not guarantee a
  fixed-size density representation.
- Monotone retirement contributes a Gaussian probability over the retired
  support. A scalar implementation matches independent numerical integration;
  the multivariate case needs joint probabilities. The omitted scalar term can
  have unbounded log error near a support boundary.
- A normalized monotone transition has a state-dependent normalizer. Removing
  it changes distribution shape even after global renormalization. Repeated
  elimination must also carry the earlier nonquadratic shape.

One simple shared-observation control is informative: deleting covariance
cross terms changes the variance of an observable sum by a factor101, while
spuriously narrowing the unexcited difference. Deleting precision cross terms
instead makes individual variances about50.75times too small. These synthetic
controls explain why memory savings based on independence would be misleading.

## Storage estimate

A proposed boundary carries8health variables,24thermal-response coefficients,
5fast physical states and3static H/gamma nuisance parameters:40coordinates.
It is conditional on a specified Markov aging model and fixed H/gamma thermal
laws. A local active aging segment adds8endpoint/slope coordinates; an uncertain
local temperature curve adds4. A global cubic trajectory cannot be retired this
way without a justified change of representation and prior.

| Proposed layout | Packed root | Root +12-bit centers +one scratch row |
| --- | ---: | ---: |
| Full64-coordinate trajectory example |17,160 B|17,776 B|
| 40-coordinate boundary |**6,888 B**|**7,276 B**|
| Boundary +4 uncertain T controls |8,280 B|8,706 B|
| Boundary +8 active age endpoint controls |9,800 B|10,264 B|
| Active age and uncertain T controls |11,448 B|11,950 B|

These are partial packed-payload estimates. The support factor, prior/model
descriptors, nonlinear/remainder representations, metadata and remaining stack/
workspace are additional. No packed firmware updater or complete SRAM fit is
claimed; the reference uses dense NumPy arrays. The48-coordinate version already
exceeds10KiB with only one scratch row. The40-coordinate version leaves2,964B,
but its support-factor complexity and full runtime requirements are unresolved.

The main checks took about0.024CPU seconds on this host. This is algebra-test
time, not battery-estimator throughput. All137 earlier artifacts bound by the
main reservation remain unchanged, and the supplemental attempt preserves the
main result and source snapshots.

## Next gate

The next useful implementation is a small **support-aware chronological
message**, starting with two monotone health coordinates and their thermal
coupling, with carried SOC and explicitly handled nuisance uncertainty. First
specify a normalized aging transition; then compare constrained retirement with
a batch integration oracle. Measure normalization, SOC/Q query errors, retained
shape complexity and actual memory. A quadratic core plus an unresolved support
factor is not yet an aging-capable compressor.

The previous fixed-center nonlinear field remains unrepaired. No calibrated
aging law, full battery integration, probability coverage, M23 timing or ten-year
qualification is supplied by this step.

## Reproduction

From the repository root, with NumPy installed, use fresh output directories:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.structured_joint_001.qualify /tmp/mumble-structured-joint-check
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.structured_joint_001.support_checks /tmp/mumble-joint-support-check
```

Both refuse an existing output directory. The supplemental check preserves the
canonical main attempt; it does not rerun it. Source identities and assumptions
are captured with every attempt. [joint.py](joint.py) is a local algebra primitive
whose caller must supply correctly owned factors once; it is not a streaming
source-ownership API or a complete multivariate constrained solver.
