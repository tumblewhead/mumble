The derivation supports a history object with **physical transport and conditional
evidence**, kept separate from the rolling optimizer. The comparison rejects the
specific small polynomial and rational approximations tested here. It does not
reject that architecture, rational approximation generally, or complex-valued
coordinates. No rolling solver, prior, physical model or aging law was changed.

The frozen design is [plan.json](plan.json), the complete comparison is
[comparison002/receipt.json](comparison002/receipt.json), and the component
attribution and exact composition control are in
[diagnostic002/receipt.json](diagnostic002/receipt.json). Source snapshots, input
identities, commands and build flags accompany the receipts. This work follows
the [provider interface](../history_provider_001/contract.json) and the
[four-step architecture plan](../../plans/physical_history_next_step_001.json).

**What the I/Q analogy gives us.** A physical response has two complementary
parts: the response carried from the entering state, and the response forced by
the subsequent current. For one RC mode on a stationary block H,

\[
v_{\rm exit}=A_H(\tau)v_{\rm entry}+R F_H(\tau).
\]

For a single interval, A=exp(−dt/τ), F=(1−A)I. For chronological blocks A then B,

\[
A_{AB}=A_B A_A,\qquad F_{AB}=A_B F_A+F_B.
\]

Hysteresis has the analogous affine map h_exit=a_H h_entry+b_H, with a and b
depending on both directional rates and the ordered sign/current history. These
pairs form affine transport operators, represented by upper triangular 2×2
matrices. Multiplication is associative; order matters. They are not generally
orthogonal or independent. Treating their likelihood contributions separately
and discarding cross terms would change the inference problem.

Writing F+iA is a valid packaging of two real numbers. It neither halves storage
nor creates a physical quadrature relation. A real orthogonal rotation can be
useful for conditioning, but retaining all rotated coordinates preserves exactly
the same represented likelihood. Dropping coordinates needs a separate error
argument. In this experiment, 45-degree paired rotations passed all frozen cost
invariance checks. Their maximum absolute cost difference was 7.40e−6 NLL, on
large fabricated costs; this is numerical arithmetic, not improved fidelity.

Complex analysis is potentially useful for choosing rational approximations to
analytic response functions. It does not establish a small, exact closed algebra
for the entire unknown-rate battery model. Our rational arm uses a fixed Cayley
coordinate, not fitted complex poles, oscillatory battery modes, or vector
fitting. The distinction matters: [SINTEF's vector fitting description](https://www.sintef.no/en/software/vector-fitting/)
describes a different pole/residue fitting procedure. No passivity or uniform
approximation certificate follows from our coordinate choice.

**The likelihood has an exact conditional structure.** Let

\[
q=(\log\tau_1,\log\tau_2,\log\tau_3,
\log\gamma_+,\log\gamma_-,z_0,\chi),\qquad \chi=1/Q,
\]

and lift the remaining amplitudes into

\[
u=(1,R_0,R_1,R_2,R_3,H,v_{10},v_{20},v_{30},Hh_0).
\]

At fixed q each normalized voltage residual is linear in u. Therefore a block
likelihood is exactly L_H(q,u)=½||S_H(q)u||². At one fixed q the triangular factor
has only 55 doubles, or 440 bytes. The difficult part is retaining its dependence
on all seven uncertain nonlinear coordinates. A factor evaluated at the latest
estimate is not a sufficient history object when those coordinates change.

The lift is a query feature map, not a new independent parameterization: Hh0
remains the product of the original H and h0, and the original joint prior and
support remain authoritative. In particular, h is carried independently when
H=0; no division by H is used to reconstruct it.

For stationary blocks, q_B=ψ_A(q) advances z0 by the measured charge times χ.
The entering amplitude vector for B is u_B=T_A(q)u. For example, each entering
RC voltage becomes A_i v_i+F_i R_i, and Hh becomes a(Hh)+bH. Thus the exact
composition rule is

\[
S_{AB}(q)=\operatorname{qr}_{R}
\begin{bmatrix}
S_A(q)\\S_B(\psi_A(q))T_A(q)
\end{bmatrix}.
\]

More generally a history message is (Φ_H,L_H), with
Φ_AB=Φ_B∘Φ_A and L_AB=L_A+L_B∘Φ_A. Metadata must carry source intervals,
chronology, model/health epochs, valid entry domain and approximation status.
The rolling estimator queries this object; its best-fit answer does not replace
the object. This is the useful connection to the reviewed NAIA architecture,
without transferring NAIA's fixed-model closure or resource claims.

The exact two-block control here passed at all 33 original query nodes. Splitting
4,096 observations into 17+4,079 and carrying SOC, all three RC voltages and
hysteresis gave a maximum cost discrepancy of 1.03e−8 NLL and state discrepancy
below 1.39e−16. This validates that finite control, not an indefinite-time theorem.

**What was implemented and compared.** The prototype propagates free and forced
responses at fixed parameter nodes, independent of any estimate. Each residual
is projected into a common feature basis and appended to a square-root factor.
It keeps the residual constant, amplitude products and likelihood cross terms.
Actual intervals and sample order are retained. Two coordinate families were
fixed before evaluation:

- Chebyshev polynomials in log time constants/rates.
- Chebyshev polynomials in the rational coordinate
  u=(p−pc)/((p+pc)ρ), with pc=√(pmin pmax) and
  ρ=tanh((log pmax−log pmin)/4), for each positive time constant/rate p.

Both use polynomial coordinates in z0 and χ for the original tanh OCV curve.
Degrees 2, 3 and 4 were tested on the entire public support and a declared local
domain (public mean ±0.5 public SD, intersected with support). Nodes and domains
never follow the optimizer. Queries outside the local domain return unavailable;
there is no extrapolation or assertion that the true battery lies in that domain.

The local-domain comparison has 97 available queries: the original 33 mean/axis
points and 64 joint perturbations. Another 32 frozen global queries test the full
domain candidates. The 64-record fixture is inherited from interface
qualification. A 4,096-record extension repeats its raw ADC codes as declared new
fabricated observations while continuously carrying state. Their durations are
1.874 and 119.954 seconds. These are algebra/representation tests, not plausible
plant trajectories or tests of minutes-to-hours parameter learning. No truth,
optimizer, posterior or canonical long trajectory enters this experiment.

For degree d the feature count is
F=6(d+1)+3(d+1)(d+2)/2+1. The factor stores F(F+1)/2 doubles. The table shows
local-domain likelihood error oscillation, max(error)−min(error), across its 97
queries. The descriptive finite criterion is the preserved 0.1 NLL; it is not a
physical accuracy requirement or a replacement for the canonical 545-node gate.

| Degree | Factor + boundary numeric bytes | Polynomial, 64 | Rational, 64 | Polynomial, 4,096 | Rational, 4,096 |
|---|---:|---:|---:|---:|---:|
| 2 | 5,920 | 7,940.84 | 7,911.46 | 485,567.71 | 487,069.46 |
| 3 | 12,776 | 1,061.53 | 1,057.63 | 47,408.41 | 52,149.85 |
| 4 | 24,056 | 319.74 | 319.75 | 27,922.62 | 28,059.50 |

Every candidate fails the finite fidelity criterion. The wider domains also
fail, often by more. Degree 3 and 4 factors alone exceed the entire 10,240-byte
subsystem budget. Degree 2's lower bound excludes the solver, raw window, queue,
configuration, source metadata, query/append scratch, stack and runtime. It is
not a complete memory pass. The Python diagnostic retains full design matrices
as scratch; its runtime is not a candidate firmware speed measurement.

On the identical original 33-point, 64-record stencil, the inherited fixed-anchor
rolling summary had 71.904 NLL error oscillation. The smallest local new factors
have about 1,221 NLL. Degree 4 reaches about 40.345 NLL there, but remains above
0.1 and over budget. Thus even on the matched narrow comparison there is no
qualified replacement. Full table values must not be compared to the old
33-point score without accounting for the different query stencil.

**The dominant failure is identifiable.** Component attribution retains signed
cross effects: if the exact residual is r and component errors are δ_j, each
component contributes Σ δ_j(r+½Σδ) to the cost error. These contributions sum to
the total; their individual oscillations need not sum to the total oscillation.
For the degree-4 local polynomial arm at 4,096 records, OCV has a peak voltage
discrepancy of 0.04619 mV and an attributed cost-error oscillation of 27,935.57
NLL. Forced hysteresis contributes 96.81 NLL and each RC component less than
4.25 NLL. The fabricated residuals are large, so a small systematic voltage
approximation can have a large likelihood effect. Being smaller than 1 mV does
not by itself make an accumulated likelihood error harmless.

The rational map changes the rate responses but leaves this OCV approximation
unchanged. It improves some RC terms and worsens some hysteresis terms; it is
not a consistent winner. An orthogonal rotation of either finite basis cannot
restore the missing nonlinear functions.

**Numerical issues remain explicit.** The completed comparison performed 1,148
checks and recorded one mismatch: factor versus direct-row gradient for the
degree-4 full-domain polynomial arm at 4,096 records. The worst normalized
component differed by about 1.30e−7 at a gradient near 233.25, or 1.94 times its
frozen allowance. Long-double accumulation reproduces the direct result and
locates the difference in the already rounded QR factor; the component has a
cancellation ratio around 8,012. This small arithmetic issue is distinct from
the much larger representation failures. Its tolerance was not relaxed.

All cost/endpoint recurrence controls, feature-derivative checks, direct-cost and
NumPy-QR controls, rotated-cost checks and domain checks passed. Partitioning
identical globally generated rows also passed. That last test is only QR append
consistency: it does not demonstrate closed composition of independently entered
finite-basis blocks. An orthogonal change can alter rounding and conditioning
even though the exact represented likelihood is invariant.

The first comparison's numerical stop is preserved in comparison001. A launcher
syntax error before any evaluation is recorded in preflight.json. The attribution
run completed its 24 cases but hit a list/abs reporting error, preserved in
diagnostic001; diagnostic002 repairs reporting and repeats only the exact
composition control. All attempts together used a conservative 8,362,304 model
steps, below the predeclared 10,000,000 cap. No long sweeps were run.

**Decision and next derivation.** Keep the provider boundary, the exact
conditional-amplitude structure and the free/forced transport pair. Reject these
specific uniform-degree factors as deployable replacements. The next bounded
design should give the known nonlinear OCV term its own representation and
budget, then retain its cross terms with the dynamic response terms. Simply
increasing every basis degree already loses the SRAM comparison.

One concrete stationary alternative is a vector-valued measure over accumulated
charge C. OCV is the known function U(z0−χC); history needs sums of U, U² and
U times observed voltage and dynamic-response features. A charge-domain
quadrature/moment representation could approximate those sums without replacing
U itself by the same low-degree parameter polynomial. Dynamic-response weights
must retain the original ordered history and rate dependence: a histogram of
charge alone is insufficient. Signed cross weights, bounded quadrature error,
memory saturation and legal composition all require derivation before coding.
This is a proposed next candidate, not a demonstrated solution.

Only after a stationary representation and full resource ledger pass should it
be connected to the unchanged rolling solver for a matched four-hour run.
Explicit aging then requires transition kernels and integration over uncertain
past health; stationary charge/Q formulas cannot simply be reused under varying
Q. No exponential forgetting, truth-based centering or new aging coefficients
were introduced here. Current model calibration and uncertainty-coverage gaps
remain open.

Reproduction commands (use fresh output directories; existing receipts are never
overwritten):

```sh
python3 -B experiments/history_basis_comparison_001/compare.py /tmp/mumble-basis-comparison-new
```

The comparison returns a nonzero exit status when a numerical control fails,
while still writing all comparison outcomes. Diagnostic scripts deliberately
bind the saved comparison002 evidence and aggregate work ledger; they are
research receipts, not general-purpose campaign launchers.
