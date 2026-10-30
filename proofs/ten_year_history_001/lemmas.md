# A mathematical foundation for ten-year retained history

These are written mathematical proofs under stated hypotheses, not a proof-
assistant certificate or a ten-year battery qualification. The
[contract](contract.json) records the user-confirmed meaning of C and separates
proposed aging envelopes from physical guarantees. No new battery fit is used.

## Definitions and the error to be bounded

Let X_k contain current fast state, health, remaining uncertain parameters and
any necessary aging-law variables. The admitted Markov model has transition
K_k and positive observation likelihood L_k. Known inputs, actual intervals,
temperature/model scope and observation provenance are part of their context.
Its exact filter is `pi_k = B_k(pi_(k-1) K_k)`, where B normalizes multiplication
by L_k. The decoded implementation belief is `q_k`.

Distinguish four axes: accumulated history n, future prediction horizon H,
physical age t, and number of approximation/arithmetic operations m. They need
not be proportional. The recent source histories are0.229/0.914seconds, with
future probes up to20seconds. They do not establish a calendar-time trend.

There are distinct errors:

- physical/model discrepancy between the actual cell and the admitted model;
- inferential uncertainty and lack of excitation within that model;
- history representation and token/transport approximation;
- finite arithmetic and solver residual;
- sampling error in a desktop comparison reference.

Only the last three are implementation/comparison defects. An exact posterior
can be broad or physically wrong under a misspecified model. A narrow fitted
distribution is not evidence that those defects are small.

For a strong audit use `D(p,q)=ess sup log(dp/dq)-ess inf log(dp/dq)` on common
support; set D=infinity when bounded mutual density ratios do not exist.
It is invariant to normalization constants and obeys the triangle inequality
by subadditivity of oscillation. It is conservative and is not required to be
the only practical metric. A discrete point approximation to a continuous
posterior may have infinite D; that is not repaired by silently adding noise.

For physical queries g, also track differences of E[g], E[g_i*g_j], and
requested tail/interval functionals on a declared query family. This family
must include the response couplings demonstrated by the backward study.
A recurrence in a restricted query distance requires its own propagation
closure proof; agreement of16marginal moments supplies no such theorem.

## L1. Exact finite-span gallery compaction

Assume all admitted token log-likelihoods, expressed on the SAME unknown
theta with valid shared boundary/aging semantics, satisfy

`log L_e(theta) = c_e + sum_(j=1..d) a_ej phi_j(theta)`.

For a prior counted once, the history likelihood depends on tokens only
through `A_j=sum_e a_ej` and a query-independent constant. Adding A vectors is
associative and commutative. In exact arithmetic all raw token records may be
eliminated without changing the posterior.

**Proof.** Multiply likelihood factors and take logarithms. Their sum is
`sum c_e + sum_j A_j phi_j(theta)`. Normalization cancels the first term within
one proper posterior. Relative branch evidence needs its constants retained.
This proves the factorization and exact compaction. It does not prove that
the nonlinear aging battery admits a finite d, nor bounded machine word size.

**Repeated-Gaussian example.** For a fixed conditional response f_s(theta),
known constant variance sigma² and independent observations y_i, retain
`n, S=sum y_i, T=sum y_i²`. The negative log likelihood, up to normalization,
is `(n*f_s²-2*S*f_s+T)/(2*sigma²)`. Three statistics replace every repetition.
For known unequal variances use sums of1/sigma_i², y_i/sigma_i² and
y_i²/sigma_i². Correlated noise requires the appropriate joint covariance;
counting correlated repetitions as independent breaks the premise.

**Meaning.** Repetition may add no new FUNCTIONAL direction while still adding
statistical information. A gallery entry is not merely one representative
measurement. Multiplicity and sufficient residual statistics survive.

## L2. Incremental ownership and overlap

If a token contains p(theta|D_old), it already includes p0 and D_old. Treating
it as a new likelihood and multiplying another posterior containing D_old
duplicates that evidence. Overlapping rolling windows are not disjoint tokens.

**Proof.** `p(theta|D) proportional p0(theta)L_D(theta)`. Multiplying two such
posteriors gives p0² L_D², whereas one copy requires p0 L_D. For overlapping
sets, the intersection likelihood is repeated as well. A valid new token is
an owned conditional evidence increment, or an explicitly defined replacement
message—not another independent copy of the posterior. Unique source IDs,
intervals and boundary ownership must therefore accompany composition.

## L3. Chronological elimination is associative, not generally commutative

Define an unnormalized token operator
`(T_e mu)(dx') = integral G_e(x,dx') mu(dx)`, including the ordered physical
transition and owned likelihood. For nonnegative proper finite factors,
integration of intermediate states makes operator composition associative.
The current boundary measure is a sufficient history message for future
queries under the admitted Markov model.

**Proof.** Repeated integration of nonnegative kernels may be regrouped by
Tonelli; normalization can be postponed while retaining finite nonzero mass.
This establishes exact elimination of past states. Operators generally do
not commute. For instance A(x)=x/2+1/2 and B(x)=x/2-1/2 give B(A(0))=-1/4
and A(B(0))=1/4. A histogram containing one A and one B loses their endpoint.
A composed affine map retains the order in two coefficients. The same issue
applies to RC/hysteresis boundary state and age-dependent responses.

Constant DIMENSION of a probability measure's argument does not imply a
finite-dimensional representation of that measure. A finite operator gallery
alone supplies no closure theorem for arbitrary compositions.

## L4. A closed dynamic base case: linear Gaussian elimination

Assume a known linear Gaussian state/observation model with proper Gaussian
boundary belief, positive noise variances, and integration over full Euclidean
space. Its current belief remains Gaussian. Thus fixed mean/covariance storage
exactly eliminates arbitrary past observations and states in real arithmetic.

**Proof.** Products of Gaussian factors have exponent
`-.5 [r,z]'J[r,z] + h'[r,z] - c`. If J_zz is positive definite, integrating z
gives

```
J_new = J_rr - J_rz solve(J_zz,J_zr),
h_new = h_r  - J_rz solve(J_zz,h_z),
c_new = c - .5 h_z' solve(J_zz,h_z)
        - dim(z)/2 log(2*pi) + .5 logdet(J_zz).
```

Completion of the square proves the formulas. Positive proper marginal
covariance and induction give closure; L3 gives equality to batch elimination.
This is a usable base proof for a reference implementation, not proof that
our nonlinear, bounded, multimodal battery filter is Gaussian. Finite support
truncation introduces additional factors and generally breaks this closure.
Zero process noise is a deterministic constraint, not an epsilon variance.
Floating-point implementations need a separate square-root/range analysis.

## L5. Aging makes relevance change through transport

In a scalar local Gaussian model, an old state estimate has variance P and
the accumulated independent physical aging innovation has variance A. The
current predictive variance is P+A, and its precision is1/(P+A), with any
known drift applied to the mean. In a vector model it is F P F'+Q_age.

**Proof.** Convolution of the independent Gaussian transition and old belief
adds their covariances; linear transformation gives the vector formula.
No arbitrary exponential age weight appears. If A=0 and the mapping is known,
the old information need not decay. If A is unknown, its inflation cannot be
certified from an endpoint parameter envelope alone. Separate old observations
share transition innovations; they cannot each be propagated and then counted
as independent current-state evidence. L4's elimination preserves this coupling.

For set-valued aging, propagate an old support S through the admitted relation
K_set: `S_new=union_(x in S) K_set(x)`. Containment is preserved if the true
transition is admitted. Intersecting stale S directly with current constraints
can exclude the actual aged cell. Certified monotone R retains old lower
bounds and monotone Q/C old upper bounds; numerical values and uncertainty
still require the transition convention. These are conditional statements.

## L6. Envelope and repetitiveness do not guarantee identifiability

Suppose two admitted health paths give the same observation law over an
uninformative interval but end with target values a and b. No estimator using
those observations can guarantee point error below |a-b|/2 for both paths.

**Proof.** The data and estimator output distribution are indistinguishable.
For any proposed common point m, `|a-b|<=|a-m|+|m-b|`. At least one error is
at least half the separation. Capacity changes during a zero-current interval
can have this property under the inherited SOC-continuous capacity convention.
No number of repeated zero-current observations identifies that capacity drift.

A bounded scalar sequence can also alternate between0.7and1.3 indefinitely:
its range stays bounded while total variation grows0.6per transition. If
monotonicity is actually imposed, total variation is bounded, but an arbitrarily
fast one-way change is still allowed. Thus neither an envelope nor monotonicity
supplies a local drift rate or a maximum safe gap between informative stimuli.

This is an impossibility of unconditional useful accuracy—not of maintaining
a valid broad uncertainty set. Availability, containment and useful precision
must be separate product states.

## L7. RC aging envelopes must respect R*C

For positive reference quantities, set r=R/R_ref and c=C/C_ref. Then
`tau/tau_ref = r*c` and `delta log tau=delta log R+delta log C` exactly.
Independent[0.5,1.5]design factors imply[0.25,2.25]for tau. If one additionally
certifies R nondecreasing in[1,1.5]and C nonincreasing in[0.5,1], the implied
tau envelope is[0.5,1.5], and tau still need not be monotone. Corresponding
±30percent boxes imply[0.49,1.69], or[0.7,1.3]with those directional bounds.

**Proof.** Multiply positive endpoints; log identities follow from tau=RC.
These are conditional envelope calculations, not aging calibration. Evolving
R,C,tau independently can violate the physical parameterization. Whether v
or C*v is continuous across an effective-capacitance update is not settled
by this algebra and must be specified separately.

## L8. Strong error propagation without artificial forgetting

For the same Markov kernel K, `D(pK,qK)<=D(p,q)`. For the same positive
likelihood L and shared support, `D(B_L p,B_L q)=D(p,q)`.

**Proof.** If m<=dp/dq<=M, the propagated density ratio is a conditional
expectation of dp/dq under q, hence also lies in[m,M]. Multiplication by L
cancels in the ratio; normalization adds a constant to its logarithm, which
oscillation removes. Apply the two facts consecutively.

Let C_k be representation compaction, A_k numerical evaluation, F_k the exact
admitted update, and Fhat_k the implemented physical/aging update. Define on
the actual approximate input

```
d_k = D(pi_k,q_k),
c_k = D(Fhat_k(q_(k-1)), C_k Fhat_k(q_(k-1))),
n_k = D(C_k Fhat_k(q_(k-1)), A_k C_k Fhat_k(q_(k-1))),
m_k = D(F_k(q_(k-1)), Fhat_k(q_(k-1))).
```

Triangle inequality and nonexpansivity give
`d_k <= d_(k-1)+c_k+n_k+m_k`.
The physical-model discrepancy relative to the real cell is still outside
this admitted-model ledger unless independently bounded. A wrong deterministic
aging transition can make m infinite. No process noise may be invented merely
to make the bound finite. This ledger is a sufficient audit route and may be
too conservative for some otherwise useful query approximations.

## L9. Conditional lifetime error theorem

In any declared distance for which actual block updates obey a proved
Lipschitz bound L_k, let total local defect be delta_k. Then

```
e_n <= (product_(j=1..n) L_j)*e_0
       + sum_(i=1..n) delta_i * product_(j=i+1..n) L_j.
```

**Proof.** Insert `e_k<=L_k e_(k-1)+delta_k` repeatedly; induction gives the
formula, with empty products1. If L_k<=1, a finite-horizon budget
`e_0+sum_(k<=N) delta_k<=B` suffices for every n<=N. If actual blocks contract
uniformly by rho<1 and delta_k<=delta, then
`e_n<=rho^n e_0+delta*(1-rho^n)/(1-rho)`.
Identity operations with zero local defect may be inserted without penalty.

Rho describes proved physical/inferential propagation in that distance. It
is not a tunable forgetting coefficient. Do not infer strict Hilbert-distance
contraction merely from an informative likelihood: L8 shows that multiplication
alone is an isometry there. Other query metrics can have different behavior
but need their own theorem. Compactness of the health box proves neither a
useful B nor a rho. No such battery-specific rho is currently established.

This theorem supplies the form of a ten-year certificate; it is not the
certificate until the local defects, admissible update count and every stated
premise are established for an actual bounded-memory implementation.

**A proved contracting toy, not a battery assumption.** A two-state transition
with switch probability a in(0,1/2) maps log odds u to
`f(u)=log(((1-a)*exp(u)+a)/(a*exp(u)+1-a))`. Its derivative is
`(1-2a)*exp(u)/(exp(u)+a*(1-a)*(exp(u)-1)²)`, between0and1-2a.
Two-state D is the absolute log-odds difference, so this particular kernel
contracts with rho=1-2a by the mean-value theorem. This is the source of the
rho in the finite toy witness; no such switch kernel is assumed for the cell.

## L10. Relating log-density error to physical query budgets

For normalized common-support densities with D<=d,
`TV(p,q)<=tanh(d/4)`, using TV=sup_A|p(A)-q(A)|. Thus for any bounded g with
range width W, `|E_p g-E_q g|<=W*tanh(d/4)`. A simple variance bound is
`|Var_p g-Var_q g|<=3 W²*tanh(d/4)`.

**Proof.** Write r=dp/dq in[m,M], with E_q r=1. Convexity of(r-1)_+ bounds TV
by `(M-1)*(1-m)/(M-m)`. With M/m<=exp(d), maximizing this expression gives
m=exp(-d/2),M=exp(d/2), and the displayed tanh bound. Bounded test-function
expectation error is at most W*TV. Shift g to[0,W]; its second moment differs
by at most W²*TV and its squared means by at most2W²*TV, proving the loose
variance bound. Tighter query-specific bounds are allowed when proved.

Consequently a log-likelihood approximation tolerance must be derived from
a declared physical query budget and domain, rather than declaring0.1NLL a
universal correctness criterion. This only bounds approximation relative to
the exact model posterior, not actual-cell point error or coverage.

## L11. Nearly repeated events can still accumulate systematic error

Suppose actual log factors equal dictionary factors plus remainders r_e(theta).
The exact history log error is `sum_e r_e(theta)`, so its oscillation is at
most `sum_e osc(r_e)`. Storing one template does not remove a systematic
remainder repeated n times.

**Proof.** Add log factors and use subadditivity of oscillation. In a scalar
Gaussian response with a fixed response bias b, likelihood discrepancy grows
with repeated information even though the induced point bias may approach a
constant b. Under repeated independent observations, posterior SD can fall
as n^(-1/2), making the standardized bias grow as sqrt(n). Thus growing
confidence can expose a fixed model error without an increasing point error.

Repeated approximate reprojection is another mechanism. On a two-point state
space with no informative data, add epsilon to posterior log odds at each
compaction. After m compactions, D=m*|epsilon|, although the true belief is
unchanged and the physical state space is bounded. Idempotent compaction or
exact sufficient-statistic accumulation avoids this particular repeated defect.
It does not erase approximation error from genuinely new, nonidentical tokens.

## L12. Existing prediction-horizon error is not lifetime evidence

For a carried RC coordinate F=a(t_star,tau)*v, response at horizon H is
`r(H,tau)*F`, with `r=(1-exp(-H/tau))/a(t_star,tau)`. On a declared compact
positive tau range, `0<=r<=1/a_min`, uniformly over H>=0. Its mean and variance
depend on E[rF] and E[r_i*r_j*F_i*F_j], respectively.

**Proof.** The numerator is between0and1, and the denominator has a positive
minimum on that domain. Expand first and second moments. Increasing H can
therefore reveal a fixed mixed-moment defect and then saturate; it does not
prove secular accumulation with the number of history tokens. The diagnosis
in backward_response_001 is evidence for this mechanism, not a ten-year
growth law. Aging changes the admitted domain and transport and is a separate
variable in the error model.

## L13. Finite storage needs range and representation proofs too

Exact finite-span closure gives fixed statistic COUNT, not fixed bit precision.
At nominal35Hz,10years of365.25days contain11,045,160,000records, requiring
34bits for a cumulative count. For12bit nonnegative codes, scalar n,S,T obey
`S<=4095*n`, `T<=4095²*n`; all three fit unsigned64bit integers at that nominal
count. This restricted accumulator example has zero summation roundoff.

**Proof.** Integer range bounds and addition establish the claim. It does not
cover real-valued regressors, weighted sums, unknown-input gaps, response
states, or timestamps. Nominal35Hz does not bound maximum delivered count,
especially if zero-duration observations are allowed. A deployment contract
must bound delivery rate/count and all arithmetic expressions. Query-time
evaluation/centering still needs numerical analysis. The scalar statistics
occupy24bytes; their context and provenance cost additional memory.

## What the base proves and what remains

L1–L5 prove that retaining every event is unnecessary in specified closed
models, and that aging can change relevance through actual state transport.
L6–L7 define unavoidable physical/observability assumptions. L8–L13 provide an
explicit error ledger, a conditional lifetime theorem and falsifiable failure
mechanisms. The missing nonlinear battery closure, useful query budgets,
aging calibration, stimulus guarantees and finite-precision implementation
are obligations, not gaps filled by optimistic extrapolation.

The earlier integer-provider proofs cover restricted static submodels and
containment; their assumptions do not extend automatically to this full aging
estimator. See [the earlier contract](../indefinite_stability_004/contract.json).

For external context, nonlinear-filter stability connects to observability
under stated conditions; it does not follow merely from a bounded parameter
domain. [Van Handel, uniform observability](https://arxiv.org/abs/0804.2885),
[filtering/systems survey](https://web.math.princeton.edu/~rvan/mtns10.pdf).
Likelihood-function dictionaries and weighted coresets have theoretical
precedents, with assumptions governing their approximation guarantees.
[Campbell–Broderick, Hilbert coresets](https://jmlr.org/papers/v20/17-613.html),
[Campbell, general bounds](https://arxiv.org/abs/2405.11780).
Our elementary lemmas above are proved here; none of those publications
certifies this battery, ten-year envelope, gallery size or MCU memory budget.
