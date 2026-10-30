# A finite representation of the bounded-exponential limit

The specialized chart already expresses each physical hysteresis rate as a
coordinate y in(-1,1). Replace only its conditional Gaussian parameters with

```
p(y | f) = exp(eta(f)*y - kappa*y*y/2 - A(eta(f),kappa)),
eta(f) = alpha_0 + sum alpha_i*f_i,
A(eta,kappa) = log integral_{-1}^{1} exp(eta*y-kappa*y*y/2)dy,
kappa >= 0.
```

The conditioning coordinates f and the physical chart are unchanged. For
kappa>0 this is exactly the previous bounded Gaussian, with
`alpha=beta/sigma²`, `kappa=1/sigma²`. At kappa=0 it is a supported exponential;
eta=0 additionally gives the uniform density. These are finite densities with
uncertainty, not point masses or frozen hysteresis rates. No positive precision
floor, clipping, pseudocount or regularizer is introduced.

For zero precision, `A=log(2*sinh(eta)/eta)` with continuous value log2 at eta=0.
Stable expm1 forms avoid overflow and cancellation. For positive precision,
Gauss-Legendre quadrature evaluates the finite log partition and moments after
subtracting the largest exponent. Orders64/128 must agree within the registered
arithmetic tolerance. Quadrature failure remains explicit. No subtraction of
two extremely small Gaussian tail probabilities is needed for these two rates.

The fitting objective is the mean conditional negative log density on the
original construction samples, with fixed component memberships. Write
`m_j=E[y^j | f]`. In QR-whitened construction features X,

```
g_alpha = mean(X*(m1-y)),
g_kappa = mean((y²-m2)/2),
H_alpha,alpha = mean(X*X'*(m2-m1²)),
H_alpha,kappa = -mean(X*(m3-m1*m2))/2,
H_kappa,kappa = mean(m4-m2²)/4.
```

The Hessian is a covariance of sufficient statistics, hence the exact objective
is convex in these natural parameters. The constraint kappa>=0 is convex too.
This is conditional fixed-membership fitting, not global optimization of the
overlapping mixture. Numerical quadrature and finite tolerance do not furnish
an exact global-optimality certificate.

At an interior solution, both gradients vanish. At kappa=0 the appropriate
conditions are `g_alpha=0`, `g_kappa>=0`; increasing precision cannot lower the
objective locally. Requiring g_kappa=0 there would incorrectly reject a valid
boundary optimum. The reported residual is the maximum coefficient-gradient
magnitude and the feasible precision-gradient violation. Also record primal
feasibility and complementarity. These are numerical fit criteria, not bounded
history error, lifetime stability, physical identification or coverage.

A damped Newton step solves the small quadratic subproblem with kappa>=0. If
the unrestricted step crosses the boundary, solve with its precision step fixed
to -kappa. Backtracking preserves feasibility and decreases the normalized
objective. Initialization is the exact natural-parameter conversion of the
saved iteration-limited Gaussian. No other conditional is refitted.

For zero precision, draw directly by inverting the supported exponential CDF.
For small positive precision use a tangent exponential envelope with exact
rejection; for larger precision use the inherited truncated-normal sampler.
These switches affect arithmetic/work only, never the target density. Strict
physical support is checked after decoding the complete full16 sample.

All sixteen variables remain joint: later conditionals still depend on the two
sampled rate coordinates. Mixture weights, physical chart/Jacobian, source
intervals and absorbed prior ownership are unchanged. A versioned schema
distinguishes natural precision from the other coordinates' stored log scales.

Storage is unchanged: each conditional still stores its linear coefficients
and one scalar shape parameter. The two-component numeric payload remains
**2,496B**, including edges and response frame; the four-component formula is
**4,960B** (not tested). Schema/model/source metadata, solver, queue, stack and
query/construction workspace remain additional. The new desktop quadrature and
sample-based builder do not establish a deployable bounded-memory update.

For an additional finite change diagnostic, let delta_alpha and delta_kappa be
the new-minus-old natural parameters of one changed rate conditional. Since
its preceding specialized coordinates all lie in(-1,1), the conditional
log-density ratio has absolute value at most
`2*sum(abs(delta_alpha)) + abs(delta_kappa)/2`.
This follows by bounding the oscillation of the exponent difference on y in
[-1,1]; normalization subtracts a value between its minimum and maximum.
Sum this bound over the two changed rates per component; take the maximum
over components to bound the full mixture ratio with unchanged weights.
This exact-arithmetic form is evaluated in binary64 and is not an interval-
certified error bound, a reference-posterior error or an indefinite-time claim.
