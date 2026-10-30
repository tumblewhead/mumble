# Comparing a different object to compress

Recommendation: compare a small **joint-current-state posterior mixture** with
a small **geometric likelihood atlas** before further work on the 99/123-feature
storage layouts. A self-organizing graph is a candidate organizer for the regions
in either representation, not yet a replacement for probability, physical state
transport or source ownership. This is a researched design comparison, not an
implemented or qualified estimator. No new inference experiment was run.

## What the experiments establish

- The rolling architecture achieved useful point estimates at practical host
  speed, but its compressed history and uncertainty were not qualified.
- Physical partitioning and coordinates repaired large response errors. The
  latest local forced/free RC approximation approaches its exact-RC control.
- The expanded likelihood object still has 99 or 123 features. Exact mixed
  products consume most of the storage. Reducing its ambient matrix rank loses
  information or needs excessive memory/workspace; floating-point certificates
  also failed.
- The sensitivity analysis supports evaluating correlated parameter changes by
  their consequences for SOC, capacity and voltage. It does not justify fixing
  nuisance parameters, or establish a universally small intrinsic dimension.
- Repeated 64/4,096-record fixtures are useful regression tests, but cannot tell
  us how a new representation learns, retains uncertainty or handles aging on
  varied physical trajectories.

Evidence: [structured storage](../experiments/structured_likelihood_001/README.md),
[forced RC](../experiments/forced_rc_kernel_001/README.md),
[sensitivity decision](../experiments/parameter_sensitivity_001/decision.json),
[original architecture](../plans/physical_history_next_step_001.json).

## The geometric opportunity

The feature map lives in 99/123 coordinates, but physical queries are generated
by sixteen original quantities. Even this sixteen-dimensional state may have
strongly correlated directions under a particular stimulus. A curved family of
plausible predictions can require many directions in a single global linear
basis, while several local descriptions might be economical. This is a hypothesis
to test; the failed global SVD does not measure the minimum dimension of every
possible nonlinear representation.

Information-geometric model reduction studies precisely how parameter
combinations map into prediction manifolds. Transtrum and Qiu demonstrate
physically interpretable reductions, including a sum-of-exponentials example.
Their results concern selected prediction sets and specific manifold structure;
they do not authorize removing an RC mode across all battery use.
[Primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC4425275/)

For this project, closeness should include the distribution of SOC, capacity and
voltage under declared future rest/load/reversal probes. Present voltage alone
cannot distinguish batteries that later respond differently. A local Fisher or
GN metric can help locate directions, but is not itself a coverage certificate.
Keep every physical coordinate uncertain; use geometric correlation to represent
it efficiently rather than treating it as known.

Goal-oriented Bayesian reduction explicitly includes quantities of interest,
prior information and measurement noise. Spantini et al. prove optimality results
for linear-Gaussian inverse problems. That supports the comparison criterion;
our nonlinear, bounded, aging model requires its own adequacy tests.
[Primary paper](https://arxiv.org/abs/1607.01881)

## Alternatives and their distinct semantics

| Approach | Retained object | Useful difference | Critical issue here |
| --- | --- | --- | --- |
| Geometric likelihood atlas | A few local joint likelihood factors, anchors, validity regions and physical transport maps | Follows curved parameter dependence with smaller local factors | Old evidence cannot be reconstructed merely by moving an anchor or adding a new chart |
| Statistical posterior mixture | A few weighted, full-covariance distributions over the current sixteen-dimensional joint state | Directly compresses the Markov filtering message; natural place for health evolution | Gaussian projection may lose curved tails, modes or support normalization and become overconfident |
| Chronological segment coreset | Selected weighted likelihood segments plus their parameter-dependent boundary maps | Preserves nonlinear evaluability for selected evidence | Keeping a voltage/current row does not preserve the preceding input history needed to evaluate it |
| Self-organizing graph of regions | Regions from one of the first two rows, with neighborhood links and allocation rules | Can place a limited memory budget where approximation geometry is difficult | Topology or prototype accuracy alone does not preserve likelihood, probability mass or rare explanations |

**Atlas:** charts are alternative descriptions of the same owned history over
different parameter regions. They must not be multiplied as independent evidence.
Overlaps need a defined single likelihood evaluation and consistent offsets.
The original prior stays separate. Disjoint-time factors have different algebra:
they can be multiplied only with the appropriate boundary transport. Chart
creation after data are discarded must inherit a controlled approximation;
re-centering an inaccurate Taylor summary cannot recover its missing history.

**Posterior mixture:** use, schematically,
`p_t(x) approximately sum_j weight_j * density_j(x)`, with full within-component
correlation and alternative modes between components. Each density needs proper
support and normalization. This is a compact deterministic density approximation,
not a claim of exact finite sufficient statistics. Gaussian assumed-density
filtering provides an established framework for approximating nonlinear filtering
distributions by moments; its approximation limitations remain relevant.
[Author's Gaussian-filtering treatment](https://users.aalto.fi/~ssarkka/pub/bfs_book_2023_online.pdf)

The current joint state already has the right target in the
[health specification](../specifications/minimal_health_model_001/model.json):
nine uncertain static parameters, five current physical states and two current
health quantities. All sixteen stay joint. The exact filtering distribution is
sufficient for future inference under that fixed Markov model; a two/four-component
approximation has no automatic sufficiency guarantee.

A posterior message owns its absorbed initial prior. A rolling update using
that message must add only new/disjoint observations; it must not append the
original prior again or replay absorbed observations. This requires an explicit
provider/caller contract change, not renaming the current likelihood factor.
Nuisance marginalization must retain correlation and relevant normalization;
plugging in a best-fit nuisance vector is not the same operation.

**Coreset:** Hilbert coresets approximate sums of log-likelihood functions using
a small weighted subset, with approximation guarantees under their construction
and norm assumptions. This is a meaningful comparator, rather than simple sample
decimation. [Primary paper](https://www.jmlr.org/papers/v20/17-613.html)

In our stationary model, independent measurement noise permits an additive
log-likelihood conditional on parameters and the known input sequence. The
obstacle is evaluating a selected historical likelihood at a new parameter
query: its entering RC/hysteresis/SOC state depends on preceding inputs. Boundary
maps and forcing information must be included in the coreset's cost. Under
uncertain aging, conditional boundary distributions are harder still. Ordinary
weighted-row guarantees do not supply that missing transport.

## What a self-organizing network could do

Use nodes as joint belief regions or likelihood charts. Connect nearby regions
according to their physical predictions and uncertainty. A node would need an
anchor or mean, full correlated shape, a mass or relative likelihood offset,
domain/error status, and the shared source/health-epoch ownership contract.
Each newly received observation updates the appropriate evidence representation;
winner counts are not a likelihood.

Standard growing neural gas learns input topology and vector quantization. Its
algorithm includes node adaptation rates, edge-age removal, insertion schedules
and multiplicative error-counter decay. Those are algorithmic bookkeeping, not
battery-aging laws. If its nodes held evidence, deleting or decaying them would
need a separate inference-preservation argument.
[Original algorithm](https://proceedings.neurips.cc/paper/1994/file/d56b9fc4b0f1be8871f5e1c40c0067e7-Paper.pdf)

Our proposed adaptation would have a fixed node budget. Splits would conserve
parent probability mass for a mixture, or retain chart ownership for an atlas.
Merges would carry an explicit approximation assessment; matching mean/covariance
alone can lose a distinct mode. A new node cannot manufacture old information.
Rare explanations that matter under renewed excitation need protection. Network
complexity should be justified by measured prediction/density approximation,
not by visually attractive clusters or a new arbitrary distance threshold.

## Aging remains a physical prediction step

The statistical message should be propagated through the declared transition
kernel, then updated with new observations. Old capacity evidence remains
informative about past capacity and about present capacity through that kernel;
uncertainty can broaden as health evolves. The same logic applies to current
resistance and correlations with static quantities. No history discount is needed
to express this distinction.

The specified transition is support-truncated and its normalizer depends on
state. A convenient unbounded Gaussian prediction followed by clipping would
change the model. Any Gaussian/mixture approximation must account for this
normalization or report unresolved support/approximation error. No physical aging
rates have been calibrated; compression cannot supply them or inflate diffusion
to hide lost information.

## Preliminary memory arithmetic, not a deployment claim

For a stationary/current joint dimension of sixteen, one Gaussian-style region
needs sixteen means, 136 packed covariance-factor entries and one log weight:
`8*(16+136+1) = 1,224 B`. Two cores use **2,448 B**, four **4,896 B**.
This keeps all within-component cross covariances.

A seventeen-feature affine residual QR factor also has 153 packed entries,
or 1,224 B; adding its sixteen-coordinate anchor gives **1,352 B per chart**.
Two chart cores use 2,704 B, four 5,408 B. The physical meaning and missing
storage differ from the mixture despite similar core arithmetic.

Both exclude support/error descriptors, physical transport storage where needed,
normalization/mass bookkeeping, shared buffers, solver integration, update
scratch, stack and saturation recovery. A covariance bank can require multiple
simultaneously live matrices or integration nodes. No complete 10,240-B fit or
speed improvement is established. Fully inferred aging-law parameters would
increase the dimension; the current specification treats transition coefficients
as declared model inputs.

## Recommended comparison sequence

1. Specify two candidate contracts: a fixed two/four-region posterior mixture
   and a fixed two/four-chart likelihood atlas. Derive complete live memory,
   prior ownership, boundary transport, support normalization and saturation
   behavior before implementing updates. Keep the recent-window rolling solver
   as the fast proposal mechanism where compatible with the respective target.
2. Qualify toy cases with analytically known Gaussian/mixture results, and the
   existing small nonlinear controls. Test weak directions, multiple supported
   modes, domain exits and late excitation. A point optimizer or inverse GN is
   not a posterior reference.
3. Compare on a physically generated trajectory with enough time for learning,
   weak-use retention and renewed excitation, using the earlier four-hour
   experiment as the intended matched horizon. Freeze commands and finite work
   budgets first. Retain 64/4,096 fixtures only as numerical regressions. This
   design task does not launch another sweep or overnight posterior study.
4. Score SOC/capacity accuracy and availability, predictive voltage, uncertainty
   behavior, likelihood/update errors where comparable, complete SRAM, and
   update latency. Truth is post-run scoring only. The earlier preferred
   0.5-percentage-point SOC and 0.5%-relative capacity targets are task scales,
   not permission to tune on truth or to disregard hard limits and unknowns.
5. Test self-organizing placement against fixed placement at the **same node,
   memory and compute budget**, once the underlying evidence objects work.
   Include a state-aware segment coreset only after its boundary payload is
   specified. No automatic parameter removal or neural-network adoption.

My preferred lead is the small joint-posterior mixture, because it directly
matches the selected aging-aware current-boundary message. The atlas is the
essential comparator because it retains a closer relationship to the existing
rolling likelihood interface. Geometry should guide the approximation and its
evaluation; self-organization should earn its complexity in that comparison.
These are proposed adaptations, with no theorem or implementation claim inherited
from the cited papers or the NAIA manuscript.
