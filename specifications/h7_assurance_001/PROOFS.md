# H7 assurance lemmas and optimization obligations

Status: hand-derived conditional lemmas and open implementation obligations.
These are not machine-checked proofs of the C program or certificates of H7
posterior calibration. The local SOC diagnostic supports selected identities;
it does not discharge the global assumptions below.

The [first detailed proof tranche](../h7_proofs_001/README.md) develops ownership,
posterior distortion and joint numerical error bounds, and records a refuted
universal field-rollback claim. Its claim ledger supersedes any interpretation
of this outline as an implementation-wide certificate. The qualified estimator
is unchanged.

## P0. Supported model and units

Use positive-discharge current, Q in Ah, and dt in seconds. Conditional on the
measured current/temperature sequence, the stationary reference parameters are
positive, tau1 < tau2 < tau3, and sample intervals are preserved. Define
Q(T) = Qref kQ(T), with known positive Arrhenius factor kQ. The current harness
measures I exactly and models voltage with additive noise plus ADC rounding.
A likelihood that replaces rounded Gaussian noise with Gaussian noise of the
same variance is an approximation, not the exact ADC likelihood.

Aging, current sensor bias, unknown thermal laws, and unmodeled electrical modes
require additional assumptions/models. Do not silently include them in a proof
about this stationary, known-thermal model. A fixed finite degree is not a
certificate of a uniform approximation error across the declared rate box.

## P1. Physical state invariants, exact arithmetic

For each interval with constant inputs and positive tau,

    v_next = a v + (1-a) R I,       a = exp(-dt/tau) in (0,1].

This is a convex combination, so |v_next| <= max(|v|, |RI|). Induction gives a
bound from the initial state and the admitted input/resistance envelope. For
hysteresis, with b = exp(-gamma_dir |I| dt/(3600 Q(T))),

    h_next = b h + (1-b) sign(I).

Thus h in [-1,1] is invariant; at rest b=1 and h is unchanged. For two states
with identical fixed parameters and inputs, the RC difference contracts by a
and the hysteresis difference by b. There is no strict hysteresis contraction
at rest, nor a rate-independent uniform RC contraction without an upper tau
bound. These physical-model properties do not prove that a polynomial
interpolation of its response preserves the same domain everywhere.

SOC obeys

    z_next = z - I dt/(3600 Q(T)).

It is an integrator, not a contraction. SOC support is invariant only under an
admissible stimulus policy or an explicit domain response. Parameter/current
error can accumulate. Monotone aging by itself is insufficient to prove that a
stationary estimator tracks ten years of changing capacity or RC parameters.

Implementation obligations: bounds on exp/expm1 and rounding, input validation,
underflow cases, native transport support, and deterministic out-of-domain
behavior. Preserve existing guards until those obligations are discharged.

## P2. Ordered evidence ownership and exact square-root compaction

For a fixed feature map phi(theta), let disjoint ordered blocks have whitened
coefficient rows A1,...,Ak, including the observed-voltage constant column.
If an orthogonal QR transformation gives R with

    R' R = sum_i Ai' Ai,

then for every admitted theta,

    ||R phi(theta)||^2 = sum_i ||Ai phi(theta)||^2.

Proof: expand both quadratic forms and use the stated Gram identity. Therefore
QR compaction is lossless for the chosen feature model in exact arithmetic.
It says nothing about how accurately that feature model represents the battery.
All cross terms must be retained. Reordering already constructed rows preserves
the quadratic; reordering inputs before generating dynamic rows does not.

Inductive ownership contract: the committed cursor denotes an exact prefix;
a new block starts at that cursor, physical state advances in order, and the
cursor advances once. A refresh re-expresses the same likelihood with the
original prior once; its readout posterior is not a second prior on that
likelihood. A rejected refresh retains the accumulated evidence. Independent
arms may process the same stream for comparison, but their posteriors must not
be multiplied as if they came from independent experiments.

An invertible feature change phi_new = M phi with A_new = A M^-1 preserves this
identity. Dropping a mode or quantizing a coefficient requires a separate error
bound. No lemma licenses restricting continuous battery parameters to codebook
nodes. Finite-precision QR requires a separate rounding-error analysis.

## P3. Local positive precision, not calibrated uncertainty

In whitened original-prior coordinates w, the local Gauss-Newton precision is

    P = I + B' B.

For nonzero u, u' P u = ||u||^2 + ||B u||^2 > 0. Thus P is positive definite
in exact arithmetic, even for weak stimulus. If U' U=P, the joint original
chart covariance is L U^-1 U^-T L'. Endpoint transport is D C D'. Using a
square-root row norm avoids explicitly subtracting covariance components.

This proves existence/positivity for the specified local quadratic. It does not
prove that the true posterior is Gaussian, that GN equals the observed Hessian,
or that a nominal 3SD interval has fixed-parameter frequentist coverage.

Implementation obligations: backward error of QR/triangular solves, minimum
usable diagonal, overflow/underflow and condition-number contracts, scaling,
and cancellation in queried quantities. Fixed matrix dimension alone does not
bound error accumulated through billions of updates.

## P4. Exact SOC transport and the necessary cross term

Let q=log Qref, and let A=sum I_k dt_k/(3600 kQ(T_k)). Conditional on the input
sequence and stationary Qref,

    z_end = z0 - A exp(-q).

Its Jacobian has entries J_z0=1 and J_q=a=A exp(-q); all other entries are zero.
For a joint original-coordinate covariance C,

    Var_linear(z_end) = C00 + a^2 Cqq + 2 a C0q.

Dropping C0q changes the uncertainty. The native H7 diagnostic reproduces the
full expression, including negative covariance and sign changes during charge.

If (z0,q) is exactly jointly Gaussian, put e=exp(-mu_q+Cqq/2). Its *exact*
transported moments are

    E[z_end] = mu_z - A e
    Var(z_end) = C00 + A^2 e^2 expm1(Cqq) + 2 A C0q e.

Proof: the Gaussian exponential moment gives E[e^-q]=e and
Var(e^-q)=e^2 expm1(Cqq); differentiating the joint moment-generating function
gives Cov(z0,e^-q)=-C0q e. Substitute into the variance of z0-Ae^-q.
This does not make a local Gaussian approximation to the actual posterior exact.

## P5. Local error budgets for a changed representation

Let P be a reference positive precision and Ptilde a candidate precision. If

    ||P^-1/2 (Ptilde-P) P^-1/2||_2 <= epsilon < 1,

then (1-epsilon)P <= Ptilde <= (1+epsilon)P, and inversion reverses the order:

    (1+epsilon)^-1 P^-1 <= Ptilde^-1 <= (1-epsilon)^-1 P^-1.

This gives a *joint* covariance distortion budget, including all cross terms.
It is a local-quadratic statement; obtain a bound, not just a sampled estimate,
before calling it a proof over a parameter domain.

For centers, suppose an exact objective F has Hessian >= P throughout a convex
region containing an interior minimizer x* and candidate xtilde. Strong
monotonicity and Cauchy-Schwarz imply

    ||xtilde-x*||_P <= ||grad F(xtilde)||_(P^-1).

For a queried state f, a bound on ||grad f||_(P^-1) over the segment converts
that center bound into a state-error bound. Endpoint approximation requires its
own residual/Jacobian bounds. Local stationarity alone does not establish the
convex-region or global-mode premises. GN precision cannot silently replace a
proven Hessian lower bound.

## P6. Persistent approximation bias can defeat indefinite calibration

Counterexample: y_i=theta+epsilon_i with independent Gaussian noise variance
sigma^2. Fit the misspecified mean theta+b, with a flat-prior Gaussian reference.
Then theta_hat=mean(y)-b and reported SD=sigma/sqrt(N). The standardized error
has mean -b sqrt(N)/sigma. For any fixed nonzero b, the probability of truth
being inside a fixed multiple of that SD tends to zero as N grows.

Thus small physical error, a fixed-size sufficient statistic, and a numerically
stable solve do not jointly imply indefinitely calibrated uncertainty. Mumble
needs a representation-error budget that stays controlled relative to useful
information, or a justified model of discrepancy/evolution. Increasing degree
alone reduces an observed error; it does not prove that budget for ten years.

## P7. Calibration has population and conditioning assumptions

If theta is drawn from a specified prior, y from the matching likelihood, and
C(y) has exact posterior probability 1-alpha, then

    Pr(theta in C(y)) = E_y[Pr(theta in C(y) | y)] = 1-alpha.

This is prior-predictive calibration. It is not uniform coverage at every fixed
cell parameter and is not automatically valid for a local Gaussian H7 output.
The engineering population may differ from the inference prior. ADC, current
feedback, temperature and support restrictions must match in a calibration lane.
For a known feedback policy based only on recorded past measurements, use the
causal sequential likelihood conditional on the past and current action. The
policy factors in the joint action/measurement density cancel from parameter
inference when they are parameter-independent given that recorded history.
This is not a license to condition on the entire future action path as if it
were an exogenous fixed design. Unrecorded information or direct truth-based
control can break the cancellation and must be modeled or removed from the lane.

See the [Monte Carlo plan](MONTE_CARLO.md) for empirical tests, independent units
and multiplicity. No zero-miss requirement is appropriate for a correctly
calibrated interval with a nonzero nominal miss probability.

## P8. Bounded resources and refinement ledger

Fixed-width history has O(1) storage in sample count. This is not a proof that
its current constants fit SRAM or that its evidence remains accurate. At 35 Hz,
ten Julian years contain 11,045,160,000 samples; even at nominal rate a 32-bit
sample cursor is insufficient. At 100 Hz there are 31,557,600,000 samples.
Prove every cursor/tick/byte-product bound and every conversion, not only the
primary counter. Generated intervals, rates and state dimensions need ABI tests.

For each optimization, record: immutable control; named lemma and premises;
changed code/data; reachable behavior equivalence or a bounded numerical change;
negative tests outside premises; target compiler/flags/ABI; same-harness flash,
SRAM, stack peak, scratch lifetimes and worst-case cycles; comparison evidence;
accepted/neutral/rejected decision. Treat input as externally changing so LTO
cannot fold away the estimator. Keep the generic checked reference available.

The [ArghtOS R6j experiment](https://github.com/tumblewhead/arghtos/blob/implementation/r6-size-research-001/implementation/R6j-proven-wake-domain.md)
uses an invariant and explicit profile restrictions to remove unreachable
branches; its [footprint methodology](https://github.com/tumblewhead/arghtos/blob/implementation/r6-size-research-001/implementation/FOOTPRINT-HARNESS-METHODOLOGY.md)
keeps historical and externally observable harnesses distinct. We adopt that
traceability pattern. These examples are not proofs of Mumble's estimator.

Next proof obligations: formalize ownership/refresh transitions; certify basis
approximation and its derivatives on the admitted domain; bound finite-precision
updates for the declared horizon; validate joint uncertainty; then prove or bound
each sparse basis, quantized coefficient, reduced precision and lifetime-based
workspace reuse transformation separately. Neither small observed errors nor a
successful Monte Carlo campaign permits removal of an unproved runtime guard.
