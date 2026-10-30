# A physical voltage coordinate for the current-state message

Let `b` be the fifteen current physical quantities other than SOC `z`. Define
`s(b) = v1 + v2 + v3 + H*h` and `w = O(z) - s(b)`, where
`O(z) = 3 + 1.15*z + 0.08*tanh(8*(z-0.5))` is the existing illustrative OCV.
This is the predicted instantaneous zero-current voltage, not an additional
observation. No truth or new measurement is introduced.

The derivative `O'(z) = 1.15 + 0.64*sech²(8*(z-0.5))` lies between 1.15 and
1.79. Therefore `(z,b) <-> (w,b)` is bijective on the existing support. Its
inverse solves `O(z)=w+s(b)` on `(0,1)`. The allowed interval is
`a(b)=O(0)-s(b) < w < c(b)=O(1)-s(b)`. Bisection gives a bracket of width
`2^-52` after 52 iterations; unsupported inputs are rejected, never clipped.
The Jacobian is `O'(z)`, regardless of the off-diagonal derivatives of `s`.
For bounded-logit coordinates `y_i=log((b_i-L_i)/(U_i-b_i))`, multiply this
by each `dy_i/db_i`. Thus a physical-coordinate density includes
`log O'(z) + sum_i log(dy_i/db_i)`.

Within a mixture component, use the normalized generative factorization

```
p_j(y,w) = Normal_15(y; m_j, C_j)
           * Normal(w; alpha_j + beta_j*y, sigma_j²) / Z_j(y),
Z_j(y) = Phi((c(b(y))-mu_j(y))/sigma_j)
         - Phi((a(b(y))-mu_j(y))/sigma_j).
```

The second factor is zero outside its allowed interval. It integrates to one
for every `y`, hence the marginal density of the other fifteen variables is
unchanged by the conditional truncation. Mixture weights still sum to one.
This is not a globally truncated joint Gaussian, whose component masses and
other-variable marginal would generally change. Conditional normalization is
part of the declared approximation family; omitting `Z_j(y)` is incorrect.

For a disjoint capacity atlas, keep its bounded quadratic density of normalized
log-capacity `t`. The other fourteen bounded logits `eta` have a full Gaussian
conditional density given `t`, exactly as before. Replace the old SOC logit
with `w | (t,eta)`, using a linear conditional mean, residual variance, and the
same state-dependent truncation. Each chart is normalized sequentially. Its
Jacobian is `2/((right-left)*(U_logQ-L_logQ))`, times the fourteen logit
Jacobians, times `O'(z)`. Fixed and adaptive capacity placement remain unchanged.

Fit the untruncated transformed moments/linear regression from construction
samples, then normalize the conditional voltage distribution on its physical
interval. This is a declared projection followed by support correction, **not
the maximum-likelihood fit of the truncated family**. Record the support mass
removed before normalization on construction, held-out and generated samples.
If that correction is substantial, assess it explicitly rather than claiming
moment preservation. No division of posterior covariance by sample count occurs.

This change keeps all sixteen quantities uncertain and all linear conditional
cross terms. It does not promise to retain every nonlinear RC/rate/resistance
relationship or future-voltage distribution. The same held-out joint density,
SOC/Q/R0 marginals and future rest/load/reversal probes must assess that question.
There is no inference, aging update, source merge or likelihood-atlas transport
in this experiment. Each snapshot owns the same prior and source intervals as
its predecessor; the coordinate transform adds no evidence.

The numeric payload is unchanged at matched region count: a mixture component
has 15 marginal means + 120 factor entries + 16 voltage-regression coefficients
+ 1 log SD + 1 log weight = 153 doubles. An atlas chart has 14 conditional
intercepts + 14 slopes + 105 factor entries + 16 voltage-regression coefficients
+ 1 log SD + 2 quadratic parameters + 1 log normalizer + 1 log weight = 154
doubles. Interval edges remain shared. This excludes ownership metadata and
all construction/query workspace; it is not a firmware SRAM qualification.
