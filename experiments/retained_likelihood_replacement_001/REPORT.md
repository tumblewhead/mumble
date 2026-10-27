# Retained likelihood replacement: completed finite host probe

## Outcome

Using the supplied historical-fit anchor, one joint likelihood-block replacement produced a **numerically resolved improvement in the audited common-prior objective** at the fixed 7,200-second prefix. The frozen candidate cost was **30,190,478.748544097**; the replacement candidate cost was **126,413.13410673568**. Their difference, **30,064,065.61443736**, exceeds the frozen computed-arithmetic allowance of **0.006785798899834227**. The recorded transaction is `accepted_feasible_point_improvement`. Both candidates are physically feasible, and **both surrogate solves remain numerically unresolved**. This completes the finite prototype; it establishes neither a nonlinear optimum nor calibrated uncertainty. See the [completed result](continuation001/result.json), [closed process receipt](continuation_process/receipt.json), and [decision](decision.json).

## What this comparison answers

The preceding [historical control](../historical_likelihood_control_001/summary.json) found a much better capacity center after reevaluating retained nonlinear evidence, with almost the same local capacity scale as the inaccurate recursive estimate. That motivated repairing the information representation that determines the center and joint shape, instead of applying a blanket interval multiplier.

This probe holds the observations, model, prior, support and coordinate measure fixed between two arms. It changes the anchor at which the retained likelihood is approximated. The old arm uses a quadratic formed at the public unsplit entering mean. The replacement arm uses a quadratic formed at the completed historical free-fit point. Both optimizations start from that same saved free-fit point.

These distinctions limit the conclusion. **The old frozen block is a declared control, not a reconstruction of the actual recursive learner.** The successful replacement was supplied a good anchor by an earlier retained-history fit; it does not demonstrate autonomous discovery of that anchor. The experiment supports joint evidence replacement as a useful mechanism within this explicit reference. It does not uniquely explain every earlier recursive error or the 7,811-second mixture-weight switch. The [design](../../plans/retained_likelihood_replacement_001.json) and [execution contract](../../plans/retained_likelihood_replacement_execution_001.json) preserve that scope.

## Common prior, complete dependencies and evidence ownership

The inference coordinates are the original sixteen entering quantities: log time constants, log positive/negative hysteresis rates, log capacity, four resistances, hysteresis amplitude, initial SOC, three initial RC voltages and initial hysteresis state. Density is defined with respect to Lebesgue measure in this chart. Both arms use

\[
\pi(x)=\frac{\mathbf 1_D(x)}{Z_D}
\left[\tfrac12\mathcal N(x;\mu_0,P_0)+\tfrac12\mathcal N(x;\mu_1,P_1)\right].
\]

The kernels are the two public initialization kernels, without a fitted center. The support combines the declared entering box with SOC feasibility throughout this known input prefix. Prefix charge extrema include zero. The mixture is conditioned **as a whole**; the common normalizer cancels in the reported cost contrast. This intentional supported reference is not claimed to reproduce the online initialization's exact probability semantics. No evidence probability or posterior mass is inferred from the unnormalized contrast. The exact mixture penalty, gradient and Hessian retain the responsibility-covariance term; they are not replaced by a single Gaussian prior. See [the saved prior](continuation001/solves/prior.json) and [math implementation](replacement_math.py).

At each anchor, the [stream evaluator](stream_evaluator.c) accumulates nonlinear cost, all sixteen gradient entries and the complete joint Gauss–Newton matrix with voltage-noise SD fixed at 0.001 V. The stored approximation is

\[
q_a(x)=L(a)+g(a)^T(x-a)+\tfrac12(x-a)^TG(a)(x-a).
\]

The mapping preserves the product `u0 = H*h0`, including both chain-rule derivatives. Dynamic state is propagated from each candidate's entering state through the original ordered prefix; current SOC is not substituted for initial SOC. Endpoint derivatives preserve the full joint dependencies for local shape transport. Optimization and reported density retain the original coordinate measure; a density expressed in legacy amplitude coordinates would require the corresponding Jacobian.

The host transaction owns source observations **[0, 252000)** once. Acceptance replaces generation 0's old block with generation 1's replacement block, archives the old block, and leaves one prior, one active likelihood block and the cursor unchanged at 252000. It does not multiply a replay likelihood by a posterior already derived from those observations. The [transaction record](continuation001/result.json) makes these ownership checks explicit.

## Candidate results and numerical status

Both candidates received their separately budgeted nonlinear audits. The following values come from those audits, not from the quadratic objective alone.

| Quantity | Frozen block candidate | Replacement block candidate |
| --- | ---: | ---: |
| Nonlinear likelihood cost | 30,190,477.310839716 | 126,417.51220331939 |
| Common prior kernel penalty | 1.4377043796768683 | −4.378096583704125 |
| Combined audited cost | 30,190,478.748544097 | 126,413.13410673568 |
| Capacity, Ah | 0.07506448716263708 | 0.06470374768047353 |
| Endpoint SOC, fraction | 0.5251004471487077 | 0.516028601622853 |
| Quadratic minus audited likelihood cost | −27,245,715.730924558 | +0.000040075203287415206 |
| Solver iterations / combined evaluations | 100 / 95 | 27 / 28 |
| Independent solve status | Unresolved | Unresolved |

The frozen quadratic substantially understates the nonlinear likelihood at its returned candidate, while the replacement quadratic closely matches its candidate's audited cost. This is direct approximation evidence at those two tested points. It supplies no whole-region likelihood-error bound, and does not reconstruct the old recursive learner's approximation.

The frozen solve reached its iteration limit. The replacement solve reported raw optimizer success, but its scaled complementarity residual, **5.117695042826075e−9**, exceeds the unchanged independent KKT tolerance, **2.346785832000663e−9**. Raw success therefore does not override its unresolved status. All objective/gradient evaluations, including final verification, are counted; neither solve reads observations or invokes the battery model. The [frozen](continuation001/solves/frozen.result.json) and [replacement](continuation001/solves/replacement.result.json) receipts retain gradients, constraint slacks, multipliers and warnings.

The contract allowed finite feasible unresolved candidates to receive exact-cost audits and to demonstrate a resolved feasible-point improvement. It did not require the comparison to prove an optimum. The cost allowance addresses accumulation of the computed summands and their combination; it is not a global model/libm or likelihood-approximation error certificate. No arbitrary voltage-error acceptance cutoff was introduced.

## Reporting and uncertainty interpretation

After inference closed, the [successful read-only report](reporting_attempt002/reporting_receipt.json) decoded one endpoint truth record and made two explicitly counted prior-algebra evaluations, with no additional model, optimizer or learner calls. Truth was **0.0647 Ah** and **0.5160528446308963 SOC**. The frozen candidate's errors were **+16.0193001% capacity** and **+0.90476025 SOC percentage points**; the replacement's were **+0.0057923964%** and **−0.0024243008 points**. These are post-inference point checks, not acceptance inputs or interval tests. See the selected [summary](summary.json) and [selection provenance](reporting_selection.json).

All four reported matrices—the surrogate and audited matrices for each arm—passed the numerical positive-definite/interior checks. Their full inverse-curvature shapes were transported through the endpoint Jacobian, retaining cross-dependencies. For the audited matrices, capacity/current-SOC shape scales are **3.6169e−6 Ah / 1.0025e−5 SOC** for the frozen candidate and **5.0782e−6 Ah / 1.6488e−5 SOC** for the replacement. These are local geometry diagnostics at nonstationary or unresolved points. Positive definiteness and an interior point do not establish a supported Gaussian approximation. The audited Gauss–Newton-plus-prior matrix omits residual-weighted second derivatives of the nonlinear likelihood; it is not the exact objective Hessian. No damping, eigenvalue repair, covariance inflation, candidate-centered intervals or coverage checks were applied.

The [first reporting receipt](reporting_receipt.json) remains failed: it stopped before prior algebra or truth decoding on two unexpected zero-byte capture files. A reviewed [metadata exception](reporting_outer_artifact_provenance.json) admitted only those exact empty files, whose origin remains unattributed. A separate reporting attempt then completed without changing inference or scientific calculations. The failed receipt and original reporting sources remain preserved.

## Preserved parity failure and bounded continuation

The [original attempt](attempt001/result.json) remains failed. It completed two anchor passes and stopped before either solve because one of 136 mapped Gram comparisons failed: the `v10` / `log_gamma_minus` entry was **−4.43101161e−315** in the new evaluator and zero in the legacy reference. Its original relative-only allowance rounded to zero. All other 135 Gram entries, cost and endpoint SOC passed.

Source review traced this to the ordering of scaling and whitening at the smallest binary64 subnormal. The old path loses a decayed initial-state feature when multiplying by its 0.03 coordinate scale before division by sigma; the new path preserves it when whitening first. A separate [saved-output diagnostic](parity_diagnostic/diagnostic.json) derives an additive underflow bound from binary64 constants, sample count, public scales and the saved counterpart diagonal. Its outward upper allowance is **1.1325343979e−313**. The [36-check fabricated qualification](qualification/underflow_parity_checks.json) includes subnormal witnesses and rejection controls. The result is a scoped arithmetic comparison, not a model or uncertainty certificate.

After [independent review](continuation_review.json), a separately frozen [continuation](../../plans/retained_likelihood_replacement_continuation_001.json) reused the two anchor outputs byte-for-byte. It performed the two solves and two remaining candidate audits, with **zero repeated anchor passes**. Original source, thresholds, receipts and the original failure were preserved. The adaptation added one supervisor invocation; it did not relabel the original attempt as successful.

## Work and storage accounting

Across the original attempt and continuation, the complete inference work was **four prefix model passes, 1,008,000 model steps, two surrogate solves and two supervisor invocations**. No learner or original fitter was called, and inference read no truth. Whole-supervisor accounting reports **4.565692 CPU seconds**, **4.671268788995803 active process wall seconds**, maximum `wait4` peak RSS **64,974,848 bytes**, and **393,863 bytes** of closed runtime outputs. Active wall excludes the intervening source-review time; peak RSS is a process high-water statistic, not summed simultaneous memory. See the [outer closure](continuation_process/receipt.json).

The evaluator's fixed C workspace is **10,680 bytes**; the compiler reports an **11,072-byte main stack frame**, which includes that workspace and must not be added to it as disjoint storage. Both already exceed a 10,240-byte subsystem budget, before other call frames, runtime, optimizer and system costs. The retained prefix occupies **8,064,000 external bytes**. The two quadratic payloads alone occupy 2,704 bytes before metadata. These are separate from host RSS; complete Cortex-M23 allocation remains unresolved. See [evaluator qualification](qualification/evaluator_summary.json) and the [resource design](../../plans/retained_likelihood_replacement_001.json).

## Decision and next engineering step

Close this finite probe as an accepted host replacement transaction with explicit unresolved optimization status. Production estimator code is unchanged. There is no interval-coverage result, candidate promotion, autonomous learning demonstration or firmware-readiness claim.

The next useful design is one bounded same-prefix refinement that chooses or revises its nonlinear anchor from public initialization or its own accepted state, using the same prior, support, full joint dependencies and exactly-once replacement. The historical free fit should remain a post-run reference rather than supply the starting anchor. Freeze its model-pass budget, acceptance arithmetic and stop rule before execution; retain exact nonlinear audits of proposed replacements. Its finish line is a finite record of whether an internally obtained candidate improves the common-prior objective and preserves evidence/state ownership, with unresolved outcomes retained. Calibrating uncertainty and compressing retained evidence remain separate requirements. This report initiates no further run or longer campaign.
