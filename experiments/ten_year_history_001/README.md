# Ten-year history foundation: proofs before another fit

**The history target is now approximately ten years.** The work here establishes
a mathematical foundation and an explicit error model; it does not claim a
ten-year battery certificate. The confirmed C quantity is RC-branch capacitance,
`C_i=tau_i/R_i`, distinct from charge capacity Q. The proposed0.5–1.5aging
envelope and more likely0.7–1.3range remain design assumptions, not calibrated
support or coverage.

The main artifacts are the [contract](../../proofs/ten_year_history_001/contract.json),
[13 lemmas with proofs](../../proofs/ten_year_history_001/lemmas.md),
[explicit error model](../../proofs/ten_year_history_001/error_model.json),
[gallery design](../../proofs/ten_year_history_001/gallery.md) and
[gated roadmap](../../proofs/ten_year_history_001/roadmap.json).
The proofs are written derivations, not proof-assistant or independent-review
certification. **423 finite mathematical checks pass.** They check examples
and algebraic correspondences; they do not supply universal lifetime claims.

The user's gallery idea has a precise foundation. If repeated events have
log-likelihoods in one fixed finite function span, only the summed coefficients
are needed. For repeated independent Gaussian observations of the same
conditional response, `count, sum(y), sum(y²)` replace the complete record.
Events disappear; their accumulated evidence and uncertainty do not. The same
input shape at different SOC, entering RC state or health is not automatically
the same likelihood function. The gallery must represent physical operators
and their context, rather than just cluster posterior point estimates.

Chronological elimination supplies the dynamic extension. A current-state
belief is sufficient under an admitted Markov model, and proper linear-Gaussian
models have a closed finite representation. The finite witness checks exact
forward filtering against a joint batch Gaussian marginal. The real battery
is nonlinear, bounded and potentially multimodal, so its closure remains a
proof obligation. A fixed-dimensional state does not imply a fixed-size exact
posterior representation.

The error model separates observation count, future forecast horizon, physical
age/throughput and number of approximation operations:

```
e_next <= L*e_current + representation_defect
                         + numerical_defect + update_model_defect.
```

Iterating this relation gives an explicit finite-horizon bound. Without a
proved contraction, bounded per-update error can accumulate. With an actual
proved contraction and bounded defects, a uniform bound follows. This
contraction is a property to establish, not an exponential forgetting factor
to select. A sufficiently accurate exact-update gallery can avoid some local
defects altogether. Local error budgets must come from useful physical query
requirements, not a universal0.1NLL threshold.

![Analytic error mechanisms](attempt001/error_mechanisms.png)

[Download the figure as PDF](attempt001/error_mechanisms.pdf). These curves
are analytic mechanisms, not calibrated cell predictions or a simulation of
billions of observations. They distinguish repeated approximation error,
increasing confidence around fixed bias, stale pooling under aging, and a
bounded forecast-response gain. The recent8/32record studies contain only
0.229/0.914seconds of source history; they cannot determine a ten-year growth
law. Their longer forecast probes exposed mixed-moment error, a different axis.

Aging changes relevance through state transport. In a scalar local Gaussian
example, old uncertainty P plus admitted aging uncertainty A gives current
variance P+A, with precision1/(P+A). Nothing requires an arbitrary age discount.
If old observations share aging increments, that shared uncertainty must not
be counted independently. If drift rates/uncertainty are unknown, bounded
parameter values alone cannot establish continued accuracy during weak stimuli.
The estimator must then admit unresolved directions. The existing minimal
health model evolves only Q,R0; independent RC aging and its state transfer
remain unimplemented and uncalibrated.

For the confirmed RC aging quantities, `tau/tau_ref=(R/R_ref)*(C/C_ref)`.
R increasing and C decreasing do not determine the direction of tau change.
The broad independent0.5–1.5envelopes imply a0.25–2.25tau ratio. Adding actual
directional bounds narrows that to0.5–1.5. Neither envelope bounds the rate of
change or guarantees informative observations. A no-excitation counterexample
proves why unconditional fine point accuracy cannot follow from those premises.

**Storage:** at nominal35Hz, ten years contain11,045,160,000records; a lifetime
count needs34bits. A64bit count and two64bit scalar sufficient sums require
24bytes per repeated-response group, before context and provenance. A16D
Gaussian mean and packed covariance require1216numeric bytes in its exact
base case. The current research message remains2544bytes. None of these figures
certifies a full<=10240byte battery subsystem or a chosen gallery size.
The actual maximum delivery rate and all accumulator/expression ranges must
be specified; nominal35Hz alone is not a worst-case count bound.

The next implementation is **P1: a prior-free incremental rolling token with
exact source ownership and chronological composition**, backed by the closed
reference in P2. P3 then derives the physical gallery and its approximation
remainder; P4 proves lifetime numerical/resource bounds; P5 tests the composed
system on fresh causal trajectories. Every new representation must identify
which lemma it preserves and which error budget it consumes before another
battery-fitting sweep. The current rolling solver and original evidence are
unchanged.

Related primary literature supports the distinction between filter stability
and finite representation, and between coreset redundancy and approximation
guarantees: [Van Handel's survey](https://web.math.princeton.edu/~rvan/mtns10.pdf),
[uniform observability](https://arxiv.org/abs/0804.2885),
[Hilbert coresets](https://jmlr.org/papers/v20/17-613.html), and
[general coreset bounds](https://arxiv.org/abs/2405.11780). Their hypotheses are
not established for this cell or its ten-year envelope. The elementary lemmas
used here are proved explicitly in the local proof document.

Finite witness command (the saved output path is exclusive):

```sh
MPLCONFIGDIR=/tmp/mumble-tenyear-mpl OPENBLAS_NUM_THREADS=1 \
python3 -B -m experiments.ten_year_history_001.witnesses
```
