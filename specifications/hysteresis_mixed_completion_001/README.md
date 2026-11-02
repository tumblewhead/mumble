# Targeted mixed-term completion experiment

Base d02bd36, experiment/conditional-architecture-001. This implements the next
bounded experiment from symbolic_system_001 and the reviewed H4 identity. No
production estimator, campaign default, calibration, support or native C changes.

## Registered arms and fixed evidence

- R2_H2: existing total-degree-2 hysteresis, width 34.
- R2_H2_c22: append (2,2) to each forced/free H basis, width 36.
- R2_H2_tensor: retain all nine quadratic H products, width 40.
- R2_H3: existing total-degree-3 H control, width 42.
- R5_H7: existing higher-fidelity reference field, not the direct reference.

The candidates reuse the same 3x3 H nodal recurrence and univariate RC degree 2.
Projection rows are selected from the full tensor inverse; no new native kernel.
All arms accumulate one joint square-root factor, retaining all cross terms.
Widths do not discretize physical parameters. The continuous domain and public
Gaussian prior are identical for every fit, including direct-history fits.

Use the frozen partitioned_coefficients_001/followup002 configuration, public
queries, recipes and observation hashes: rest, multiscale and embedded; 21008,
35520 and 126000 records at 35 Hz. Keep all 51 public queries and the preserved
out-of-box diagnostic. Each prefix is a correlated diagnostic, not an independent
trial. Hidden plant data are used only to regenerate observations and discarded
by inference; no truth scoring, fitted centering or hidden initial states.

## Matched probes and fits

First compare cost, full gradient, conditional amplitude precision and endpoint
transport against the direct C reference at every saved public query. Confirm
unchanged H2/H7 metrics against frozen controls. Separately test value and full
feature/transport derivatives, chunk ownership, domain refusal and joint factors.

Then fit all 16 origin-chart variables jointly at each prefix with the original
public Gaussian prior once. Use the existing solve/Exact/Compressed code with a
common log-shape box of +/-1 around the original public centre. Direct objectives
also enforce that computational domain. Physical path constraints remain active.
Two common public starts: zero prior-whitened displacement and a fixed small
alternating displacement (+/-0.05 in each coordinate). Use 60 GN rounds per start,
the existing convergence flags and line search. Select the lowest-cost converged
attempt; if none converge, preserve the lowest-cost attempt as unresolved. No
unsupported point is physical exclusion, and no fit is a global optimum proof.

At each selected supported fit evaluate direct residuals/derivatives and full
joint local GN precision with the same prior. Report direct-gradient stationarity,
compression-gradient dual norm, relative joint precision eigenvalues, and Q/SOC
width/centre comparisons. Do not interpret a prior-supported inverse as stimulus
identifiability or calibrated coverage; rest remains a weak-information control.

For each converged fit, compare its native compressed transport and its direct
C transport separately. Propagate the full joint local covariance to two read-only
future tasks at 25 C and 35 Hz: rest 60 s; +120 mA for 10 s then rest 30 s.
Compare sampled voltage traces, sampled minima and local widths to the converged
direct fit. These are diagnostic tasks, not a user-specified brownout authorization,
continuous-time safety bound or physical truth-accuracy test. Unconverged direct
fits prevent accepted fit-to-reference comparisons at that prefix.

## Adaptation and acceptance

Keep original runs and hashes; record numerical failures and adaptations separately.
No automatic winner is declared from centre-node equality or aggregate improvement.
Compare regressions as well as gains, native state validity, query/fit/forecast
support and source chronology. If domain or convergence prevents the fitted test,
report that limitation rather than silently changing support or tolerances.
Meaningful targeted tests and independent code/results review precede acceptance.
A substantive repair found in review requires a separately recorded rerun/re-review.

The experiment may retain one finite prefix in desktop memory for repeated direct
fits, without storing raw trajectories on disk. This is reference workspace,
not a deployable bounded-memory inference path. Each objective uses either its
field or its raw prefix, never both as independent evidence.

Packed likelihood factors are 4760, 5328, 6560 and 7224 B for the four R2 arms.
Corresponding lower numeric subtotals are 5168, 5736, 6968 and 7744 B. Report H7
and actual host scratch separately. Tables, priors, solver, metadata, stacks and
platform overhead are excluded; no full 10 KiB qualification or cycle saving.
