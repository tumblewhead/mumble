# E: conditional uncertainty and estimation guarantees

Status: mathematical proofs under explicit hypotheses. No H7-wide constants
are certified here. The exact algebra checks cover supporting polynomial
identities, not the analytic integration or all hypotheses. This develops P4–P7
of the earlier outline into an error contract suitable for later compression.

## E0. Distinguish the reference objects

F is a declared reference negative log density on domain D with proper prior.
F_H7 is the finite-feature objective. F_store is a further compressed/quantized
representation. F_fp is its computed floating-point evaluation. The delivered
local Gaussian is a further approximation to a normalized posterior.

Errors between these objects are different obligations. Accurate storage of H7
does not prove H7 matches the exact Foster likelihood; matching that likelihood
does not establish an accurate battery/noise model. A theorem about F_store
versus F_H7 must not be presented as coverage relative to physical truth.

## E1. Exact joint error identity for coefficient storage

For a fixed feature map phi and a symmetric stored-Gram error E=Gtilde-G,

    d(theta) = F_store(theta)-F_H7(theta) = (1/2) phi' E phi.
    grad d = J_phi' E phi.

The prior cancels because it is unchanged. In whitened parameter coordinates,
the local GN precision difference at a common point is exactly

    Delta P = L' J_phi' E J_phi L.

This is a full matrix identity. Small marginal coefficient errors do not bound
weak joint directions unless their projection through the information geometry
is controlled. It is not legitimate to keep only diagonal cross-section checks.

At an anchor theta0, set phi0=phi(theta0), v=phi(theta)-phi0. Then

    d(theta)-d(theta0) = phi0' E v + (1/2) v' E v.

If ||v||<=r, ||E phi0||<=a and ||E||_2<=b throughout the admitted set, its absolute
value is at most ar+(1/2)br^2. Therefore the oscillation of d over that set is at
most 2ar+br^2. These bounds may be conservative, but have an explicit meaning.
An error only in the constant-feature/constant-feature entry changes d by a
parameter-independent constant and has zero posterior effect. Errors coupling
the constant feature to other features generally DO move the center.

This distinction is essential: an absolute NLL threshold alone is not the right
posterior guarantee. However, dropping constants is not automatically a
behavior-preserving code optimization. H7's cost-roundoff stopping rule depends
on the total cost. Preserve the normalizer/solver contract or bound the changed
termination error separately, even if the exact normalized posterior is unchanged.

## E2. From log-density oscillation to posterior mass

Assume both reference and approximation are normalized over the SAME domain D,
with finite nonzero normalizers and the same base measure/prior. Suppose

    a <= F_store(theta)-F_H7(theta) <= b       for all theta in D.

Let omega=b-a. Then

    TV(pi_store,pi_H7) <= tanh(omega/4).

Proof. Under pi_H7, write h=exp(-(F_store-F_H7)), with m<=h<=M and M/m=exp(omega).
Let Z=E[h]. The density ratio is h/Z and TV=E|h-Z|/(2Z). Convexity of absolute
value bounds |h-Z| by the chord joining its values at m and M. Taking expectation
therefore gives

    TV <= (M-Z)(Z-m)/(Z(M-m)).

For Z in [m,M], this expression is maximized at sqrt(mM); the maximum is
(sqrt(M)-sqrt(m))/(sqrt(M)+sqrt(m))=tanh(omega/4). The omega=0 case is identical
normalized distributions. The algebra checker verifies the nonnegative-square
identity used to locate this maximum, after m=s^2 and M=t^2.

Consequences:

- If |d-c|<=delta, omega<=2delta and TV<=tanh(delta/2).
- Every measurable event probability differs by at most this TV bound.
- To budget mass error epsilon in (0,1), it suffices to certify
  omega<=4 atanh(epsilon). This is a derived tolerance, not an arbitrary NLL cutoff.
- Approximation errors across multiple stages add in oscillation by the triangle
  inequality. Choose a total budget before assigning stage budgets.

A sampled maximum is not a uniform bound. A rate-box-only bound is not a global
posterior bound if relevant mass lies outside the box. If the exact reference
assigns mass tau outside D while the candidate is supported inside D, then

    TV(global reference,candidate) <= tau+(1-tau) epsilon_D,

where epsilon_D bounds the conditional discrepancy within D. This follows by
writing the reference as (1-tau)pi_D+tau*pi_out and applying convexity of TV.
Without a certified tail-mass bound, global calibration remains unresolved.

## E3. State transport and probability statements

Suppose the two parameter distributions differ in TV by at most epsilon and
query maps satisfy |f_store(theta)-f_ref(theta)|<=eta over their common support.
If the candidate assigns probability at least 1-alpha to f_store in [l,u], then
the reference assigns probability at least 1-alpha-epsilon to

    f_ref in [l-eta,u+eta].

Proof: the event f_store in [l,u] is contained in f_ref in the enlarged interval;
transfer its probability using the TV bound. The multidimensional version uses
set enlargement in a declared norm. This separates likelihood-storage error
from transport error instead of treating both as independent sensor noise.

This is a posterior-probability statement conditional on the data. Frequentist
coverage or physical truth coverage needs the additional calibration/model
premises in P7. Also, a local Gaussian's nominal 95% interval is not known to
carry 95% of the H7 nonlinear posterior. Its approximation error needs its own
budget. E2/E3 do not turn a local GN root into an exact posterior certificate.

## E4. Local precision and query-width bounds

Let P be SPD and suppose

    ||P^-1/2 (Ptilde-P) P^-1/2||_2 <= epsilon < 1.

By the Rayleigh quotient,

    (1-epsilon)P <= Ptilde <= (1+epsilon)P.

Congruence by P^-1/2 reduces this to eigenvalues in [1-epsilon,1+epsilon].
Inversion reverses positive-definite matrix order, giving

    (1+epsilon)^-1 P^-1 <= Ptilde^-1 <= (1-epsilon)^-1 P^-1.

For any common row query j, its variance lies between the corresponding scalar
multiples of j P^-1 j'. Thus every joint direction is controlled, including those
with severe cancellation in individual covariance components.

If the query derivative also changes by d, define sigma=||j||_(P^-1) and
eta_j=||d||_(P^-1). Triangle/reverse-triangle inequalities give candidate SD in

    [max(0,sigma-eta_j)/sqrt(1+epsilon),
     (sigma+eta_j)/sqrt(1-epsilon)].

This absolute form remains meaningful when the reference query variance is
small. Relative tolerances on each parameter separately do not imply this bound.
These are local-quadratic guarantees; they are not E2 posterior mass guarantees.

## E5. Center and practical query error

Assume F has Hessian >=P throughout a convex region containing an interior
minimizer x* and candidate xtilde. Integrating the Hessian along their segment
and using grad F(x*)=0 gives

    (xtilde-x*)' grad F(xtilde) >= ||xtilde-x*||_P^2.

Cauchy-Schwarz in the P metric implies

    ||xtilde-x*||_P <= ||grad F(xtilde)||_(P^-1).

If ||grad f||_(P^-1)<=L_f throughout that segment, and the candidate query map
has a uniform pointwise error eta_f, then

    |f_store(xtilde)-f_ref(x*)|
       <= eta_f + L_f ||grad F(xtilde)||_(P^-1).

The model, representation, finite-precision evaluation and solver residual each
contribute to that gradient. A small residual of F_store alone does not bound
the gradient of F_ref. GN precision is not a proved Hessian lower bound; local
checks cannot establish the convex-region/global-mode premise.

For the log-capacity query, |q_store-q_ref|<=beta implies relative capacity error
at most expm1(beta). A 0.5% candidate/reference requirement corresponds to
beta<=log(1.005). It becomes a truth requirement only after adding a reference
truth-error guarantee. If reference relative error is <=e_ref, a sufficient
combined bound is (1+e_ref)exp(beta)-1. SOC absolute errors add directly.
Application tolerance and uncertainty fidelity remain different budgets.

## E6. Error in the physical feature model

Let r be exact whitened residuals, with approximation r+e and Jacobian J+dJ.
Then, exactly,

    Delta F = r'e + (1/2)e'e,
    Delta g = J'e + dJ'r + dJ'e.

The algebra checker verifies the component identity. Projection of this *joint*
gradient through the inverse information metric explains why errors in
hysteresis can move Q or SOC. Contributions may cancel; their absolute magnitudes
are not independent variances and signed attribution is not a variance fraction.

If each normalized residual error is bounded, ||e|| can still grow like sqrt(N),
and coherent J'e can grow with N. A finite degree and bounded storage alone do
not give a horizon-independent budget. Parameter-independent portions of Delta F
can be removed in analysis, but its parameter-varying portion must be bounded.

For scalar affine state recurrences with per-step error e_k and contraction
coefficient rho_k in [0,1], induction gives

    |delta_s_N| <= (product rho_k)|delta_s_0|
                  + sum_j (product_(k>j) rho_k)|e_j|.

A geometric bound epsilon/(1-rho) requires a *uniform* rho<1. SOC has rho=1;
hysteresis at rest also has rho=1, though its ideal rest update adds zero local
error. Therefore uniform exponential forgetting cannot be inserted as a proof
shortcut. The actual physical excitation and error injection determine the sum.

## E7. Impossibility statements delimit the performance claim

At zero current, the new voltage likelihood is independent of Q when other
states/parameters are held fixed. It cannot uniformly identify arbitrary Q to
0.5%. Prior correlations and earlier evidence may legitimately update Q during
rest; they do not create fresh independent Q excitation. A convergence theorem
therefore needs an identifiability/information premise and a defined initial
uncertainty, not only stable numerical iterations.

A persistent model bias b in y=theta+noise, fitted as theta+b, gives standardized
bias b sqrt(N)/sigma. For nonzero b it eventually escapes every fixed-SD band,
even with an exact sufficient statistic and arbitrarily small physical error.
This counterexample rules out an unconditional ten-year calibration claim from
fixed-size history plus numerical stability alone.

Bounded collocation values also do not prove bounded interpolation: nodes
(-1,0,1) with values (-1,1,1) have interpolant 1+x-x^2, equal to 1.25 at x=0.5.
Thus the physical h invariant cannot simply be assigned to H7's polynomial
transport. This is a counterexample to an inference from bounded nodes, not a
claim that this particular polynomial is a reachable H7 response. A reachable
response/domain bound or an explicit unresolved response remains necessary.

## E8. What must be discharged before compression is certified

Obtain bounds on H7 versus the declared physical likelihood, including derivatives
and endpoint transport, on a stated domain and horizon. Add model/noise and
outside-domain mass obligations for truth/calibration claims. Then bound each
candidate's storage error E, finite-precision accumulation and solver residual.
Use E2/E3 for probability mass, E4 for local joint widths and E5 for practical
estimation error. Retain explicit unresolved status when premises fail.

None of these proofs chooses the acceptable error budget for the application.
They turn a declared requirement into a mathematical obligation and expose which
parts of an optimization are exact, bounded, empirical or still unsupported.
