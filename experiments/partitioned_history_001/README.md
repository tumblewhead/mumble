**Partitioning substantially improved the represented likelihood, but none of the
tested candidates qualifies as a replacement compressor.** Giving OCV its own
charge coordinate reduced the degree-4 local-domain error oscillation from
319.740 to 0.1953 NLL at 64 records and from 27,922.62 to 103.494 NLL at 4,096
records. The dynamic basis and original physical model were unchanged. The
smaller moment layout has a separate cancellation defect; the square-root
control preserves the same represented likelihood with better behavior on that
control. Full deployment memory and lifetime fidelity remain unresolved.

The [plan](plan.json) was frozen before candidate evaluation. The complete
[comparison receipt](comparison001/receipt.json) includes all 48 candidate/prefix
cases and every numerical mismatch. Code, input/reference identities, source
snapshots and the build command are saved with it. This extends the
[uniform-basis comparison](../history_basis_comparison_001/README.md); old results
and tolerances were not altered.

**Connection to the manuscript.** The source is
[SCM_PEER_REVIEW_MANUSCRIPT_v1.2.pdf](/home/easy/Downloads/SCM_PEER_REVIEW_MANUSCRIPT_v1.2.pdf),
SHA-256 `f739744ae7756f4c22970298b06a123291ca53f32cd6fd609d923bbb20bf808a`.
Section 4.1 defines eight targets on one joint candidate. Section 6.2 requires
retaining every dependency that a future operation may read. Section 9.7 makes
future-query meaning part of retention sufficiency. Appendix I.2 establishes a
particular physically scaled orthogonality result, not general independence.
Those principles motivate this partition; their theorems do not automatically
qualify our Gaussian likelihood approximation or a memory layout.

| Physical part | Related manuscript families | Current mumble scope |
|---|---|---|
| Charge and equilibrium voltage | SOC, capacity, current equilibrium OCV | Uncertain initial SOC/Q; original known OCV law |
| Equilibrium curve | Learned OCV curve | Fixed tanh curve; no curve learning added |
| RC response | Foster parameters and states | Three uncertain RC modes and initial voltages |
| Directional hysteresis | Hysteresis | Both rates, amplitude and initial state uncertain |
| Temperature coupling | Thermal state | Fixed 25°C; no thermal estimator added |

These are connected parts of one model. Assigning the same measured voltage to
independent family estimators would lose ambiguity and potentially duplicate
evidence. The manuscript's learned cubic OCV model was not substituted for the
original tanh law to obtain a more convenient compressor.

**Exact dependency derivation.** In the stationary model, define η as the three
log time constants and two log hysteresis rates, and ζ=(z0,χ), χ=1/Q. With
α=(R0,R1,R2,R3,H,v10,v20,v30,Hh0), a normalized residual has the form

\[
r_k=d_k(\zeta)+X_k(\eta)\alpha,
\quad d_k=\{U(z_0-\chi C_k)-y_k\}/\sigma,
\quad C_k=\sum_{i\le k}I_i\Delta t_i/3600.
\]

The response rows include the negative signs and the same σ=0.001 V as the
reference. Hence

\[
L=\tfrac12\alpha^T G(\eta)\alpha+\alpha^T b(\eta,\zeta)+c(\zeta),
\quad G=\sum X_k^TX_k,\quad b=\sum X_k^Td_k,\quad c=\tfrac12\sum d_k^2.
\]

The exact coefficient dependencies are smaller than a generic seven-coordinate
function:

| G entries | Count | Nonlinear coordinates |
|---|---:|---|
| Ohmic self product | 1 | None |
| Ohmic–RC products | 6 | One RC time constant |
| Within-mode RC products | 9 | One RC time constant |
| Between-mode RC products | 12 | Two RC time constants |
| Ohmic–hysteresis products | 2 | Both hysteresis rates |
| RC–hysteresis products | 12 | One time constant and both hysteresis rates |
| Hysteresis self products | 3 | Both hysteresis rates |

The counts total the 45 entries of the symmetric 9×9 conditional matrix.
The nine b entries require respectively ζ alone (one), ζ and one time constant
(six), or ζ and both hysteresis rates (two). The scalar c uses only ζ.
The lift Hh0 is always evaluated as the original product, never treated as an
independent physical parameter or assigned an independent prior. No nuisance
quantity is frozen at truth. The prior remains separate and enters once.

This experiment exploits that split for OCV while retaining the predecessor's
fixed rate-response basis. It does not claim to have optimized every smaller
dependency block in the table.

**Representation and updates.** Let d be the dynamic polynomial degree and
t=(d+1)(d+2)/2. There are 6(d+1) RC feature coefficients, 2t hysteresis feature
coefficients and one ohmic coefficient. Add the measured-voltage constant to
obtain M=6(d+1)+2t+2 dynamic/observation features. Their query values f(η,α)
multiply a source row s_k. Fixed rate-node responses carry physical state in
chronological order, exactly as in the predecessor. They never follow a fitted
point.

For OCV degree q, let K=q+1. At query time evaluate the original U(z0−χC) at K
fixed Chebyshev charge nodes and obtain its interpolation coefficients u(ζ)/σ.
With t_k=(T0(Ĉk),…,Tq(Ĉk)), the represented residual is

\[
\widehat r_k=s_k f+t_k u.
\]

The source-owned history stores three blocks:

\[
A=\sum s_k^Ts_k,\qquad B=\sum s_k^Tt_k,\qquad
m_\ell=\sum T_\ell(\widehat C_k),\quad 0\le\ell\le2q.
\]

All entries of the OCV Gram matrix are reconstructed by the exact identity

\[
H_{ij}=\tfrac12(m_{i+j}+m_{|i-j|}).
\]

Thus W=[[A,B],[Bᵀ,H]] is the complete feature Gram matrix and
L̂=½vᵀWv, v=(f,u). With J=∂v/∂x in all 16 original coordinates, the gradient is
JᵀWv and the represented residual Gauss–Newton matrix is JᵀWJ. All RC–RC,
RC–hysteresis and dynamic–OCV terms remain. The observation constant and its
cross terms remain too. The C append kernel accumulates these blocks without
allocating memory or using a solver.

Appending globally expressed source rows adds these blocks. Tests cover one
batch, 17+remaining rows, and separately accumulated global-coordinate blocks.
They do not establish closure for independently entered blocks: their charge
origins and uncertain state-response maps must first be transported coherently.
Source identity, interval ownership and chronological physical propagation are
necessary even though addition of already expressed evidence coefficients
commutes. Generic merge trees, late calibration revisions and aging transitions
remain outside this prototype.

The charge domain is fixed from public support before observing outcomes:

\[
C\in[(z_{\max}-1)/\chi_{\max},\ z_{\min}/\chi_{\max}]
=[-0.0015,\ 0.006]\ {m Ah}.
\]

Every public z0/Q query remains physically legal on this domain. This deliberately
restricts the candidate's applicability; it is not a claim that all future charge
histories stay there. Domain exit returns unavailable. There is no clipping,
regridding, recentering, evidence decay or discarded old block. The local
parameter-domain arm also refuses queries outside its frozen public-half-SD
domain. Stationary C/Q is not silently reused when Q ages.

**Why cost-only algebra is insufficient for the present interface.** Combining
products of parameter-dependent basis functions can preserve a scalar cost
polynomial while losing its residual-Jacobian Gram. For example, residual vectors
(x²−1,2x) and (x²+1,0) both have squared norm (x²+1)², but their Gauss–Newton
values are 4x²+4 and 4x². A cost polynomial alone does not generally determine GN.
This is an algebraic counterexample, not a pair of physical battery histories.
The manuscript also distinguishes solver geometry from the scalar potential.

Accordingly, we retain the full A and B blocks needed by the unchanged rolling
query contract. The H identity is safe because it reconstructs the original
feature Gram entries; it does not merely preserve cost on a parameter manifold.
All mean-query GN checks against direct residual Jacobians and full QR passed.

**Frozen comparison and results.** Four dynamic degrees (1–4), three OCV degrees
(4,8,12), two parameter domains and two prefixes give 48 cases. The inherited
raw ADC fixture, actual intervals, source order and 129 query points are fixed.
There are 97 available local-domain queries and 129 full-domain queries. The
prefixes span 1.874 and 119.954 seconds. Repeated codes are declared new fabricated
observations with carried state; they are not a realistic battery benchmark or
minutes-to-hours parameter-convergence study.

The table uses the same 97 local queries and q=12 in every partitioned column.
Error is oscillation of the cost difference from exact C replay, in NLL.

| Dynamic degree | Uniform, 64 | Separate OCV, 64 | Uniform, 4,096 | Separate OCV, 4,096 | Planned moment subsystem bytes |
|---|---:|---:|---:|---:|---:|
| 1 | 33,367.12 | 616.425 | 2,190,778.65 | 170,264.07 | 9,768 |
| 2 | 7,940.84 | 47.424 | 485,567.71 | 39,512.74 | 14,056 |
| 3 | 1,061.53 | 5.310 | 47,408.41 | 1,760.58 | 20,512 |
| 4 | 319.740 | 0.1953 | 27,922.62 | 103.494 | 29,808 |

This is approximately a 1,637× and 270× reduction for degree 4. At q=12 the
sampled local OCV voltage error is below 7e−12 V; a desktop control with exact
OCV at every source sample gives 103.49424 NLL at 4,096 records. The remaining
error is therefore dominated by the retained dynamic approximation on these
queries. That control keeps the raw history and is not a bounded compressor.
The shorter q=8 arm scores 0.1851 at 64 records, slightly better than q=12 due
to signed error interactions; this is not evidence that its OCV approximation
is more accurate. No degree was selected by retuning after the results.

Every candidate fails the pre-existing descriptive 0.1 NLL criterion on its
complete available query set. The degree-4/q12 local arm does pass the original
33-point axis subset at 64 records (0.00396 NLL), while failing the broader
97-point set. A narrow-stencil pass is not sufficient. The 0.1 comparison is a
finite likelihood-shape regression, not a claimed physical necessity or a
replacement for the preserved canonical 545-query gate.

**Complete planned resource ledger.** For the moment layout, retained numeric
storage is 8[M(M+1)/2+MK+(2K−1)] bytes. The full square-root comparator needs
8(M+K)(M+K+1)/2 bytes. The exact saving is 8(K−1)(K−2)/2: only 48, 224 or 528
bytes at K=5,9,13. Partitioning gives most of its observed benefit by improving
OCV coordinates, not by eliminating the dense mixed block.

The ledger includes every following category, with no claimed workspace alias:

| Category | Accounting |
|---|---|
| Evidence | A packed triangle, all of B, all charge moments; or full QR |
| Boundary | 8[6(d+1)+2(d+1)²+1] bytes for response-node state and charge |
| New bank metadata/configuration/estimate | 400 bytes reserved |
| Inherited nonbank categories | 3,848 bytes: solver workspace 1,600; result 120; raw/ingress storage 408; calibration 56; auxiliary 128; project stack 768; runtime/IRQ/caller 768 |
| Additional candidate query scratch | 8[3(M+K)+3K+10(d+1)+16] bytes |

The 400-byte reservation allocates 144 to source/epoch/sequence/status/charge
extrema/work accounting, 128 to the estimate, 112 to query-domain endpoints and
16 to the charge domain. Fixed transform tables for a compiled model/domain may
live in program ROM; retained history is SRAM-only. The scratch reservation
allows feature values and two derivative columns, OCV coefficient work, basis
work and scalar accumulators; the existing solver workspace retains the 16×16
packed metric. Query evaluation can stream Gram entries instead of materializing
the diagnostic host's dense matrix.

The declared totals for degree 1 are 7,976 / 8,872 / 9,768 bytes at q=4/8/12.
They fit the planning target but fail fidelity. Degree 2 starts at 11,496 bytes;
all degree-2–4 layouts exceed 10,240 bytes under this allocation. At degree4/q12,
retained numeric evidence plus boundary is 22,920 bytes, compared with 24,056
for the old uniform degree-4 representation; neither is deployable.

These are complete **prospective allocations**, not a measured M23 footprint.
The Python harness holds full design matrices and derivative arrays. Node
propagation, solver integration, source transaction handling, target stack and
runtime timing have not been implemented/qualified as this proposed layout.
More aggressive workspace reuse could change the budget but requires its own
liveness proof. The prior whole-subsystem 768-byte stack reservations cannot
certify a newly integrated implementation by inheritance.

Update work is bounded by O(M²+MK+K), plus fixed-node response propagation, per
record. Cost/gradient/GN queries depend on fixed feature count and the 16 original
coordinates, not discarded source count. The full end-to-end same-host 10× speed
comparison remains unrun; Python diagnostic wall time is not that comparison.

**Numerical findings and severity.** All 48 cases completed. Across 13,269 checks,
16 numerical mismatches were recorded without changing tolerances: 15
partition-versus-QR gradient checks and one cancellation control. In the gradient
checks the largest absolute array discrepancy was approximately 1.23e−4, while
the worst component-relative allowance ratio was 4.60. All partition/direct
gradient checks, mean-query GN checks, source partition checks, ordinary cost
checks, query derivative checks and declared PSD roundoff checks passed.
Differences between QR and moment costs were at most 4.43e−5 NLL on the ordinary
fixtures. These arithmetic effects are much smaller than their fidelity failures.

However, the explicit zero-residual control is a structural numerical warning:
the moment calculation returned −1.0951e−5 NLL where direct squared residuals
gave 2.86e−22 and QR gave 1.73e−19. No negative value was clipped, repaired with a
ridge, or accepted by changing the allowance. Preserving PSD in real arithmetic
does not protect a subtraction of large terms in floating point. The ordinary
Gram eigenvalue checks passed their roundoff bounds but did not prevent this
near-null query failure. A stable implementation must handle it explicitly.

The experiment used 1,784,640 conservative model steps and 69,552 OCV node
evaluations, within the frozen caps. It made no optimizer or truth calls, did
not modify the rolling solver, and ran no long trajectory or aging campaign.

**Error bounds and scope.** The sampled tiny OCV errors are not uniform
certificates. An exact-arithmetic bound can be derived without truth: define
P0(t)=t and Pn+1(t)=(1−t²)Pn′(t). On the public charge/query domain, with K=q+1
and charge halfwidth hC, Chebyshev-root interpolation gives

\[
\|U-\widehat U\|_\infty\le
\frac{0.08(8\chi_{\max})^K\|P_K\|_1}{K!}\,h_C^K2^{1-K}.
\]

The linear part of U contributes no derivative at these orders. Using the
polynomial coefficient L1 norm bounds |PK(t)| for |t|≤1. The q12 local-domain
bound is about 6.72e−7 V, much looser than the sampled result. Numerical
evaluations of the bound in [analytic_controls.json](analytic_controls.json)
are binary64, not outward-rounded certificates. A normalized residual error δ
implies |ΔL|≤||r||₂||δ||₂+½||δ||₂², illustrating why voltage error below sensor
noise alone does not establish harmless likelihood error. Dynamic-response
approximation and lifetime composition need their own bounds as well.

**Decision.** Retain the physical dependency partition and the charge-based OCV
coordinates for further work. They expose the remaining dynamic error rather
than hiding it in an OCV approximation. Keep full square-root storage as the
numerical control: saving 48–528 bytes with the tested raw moments has not earned
a stable replacement. Do not integrate any tested candidate into the rolling
learner yet. The next bounded design should examine the RC/hysteresis dependency
blocks and their cross-term storage while preserving cost, gradient and GN;
uniformly raising all degrees is already over budget. Calibration, posterior
coverage, generic block transport and explicit physical aging remain separate
open obligations.

To reproduce the frozen comparison with a fresh output directory:

```sh
python3 -B experiments/partitioned_history_001/compare.py /tmp/mumble-partitioned-history-new
```

A nonzero exit reports numerical mismatches after recording all finite cases.
Existing output directories are never overwritten.
