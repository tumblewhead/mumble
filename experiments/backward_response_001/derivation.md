# Working backward from predictive error

All identities below refer to the saved fixed-health, constant-temperature
probe model. They do not assume a Gaussian posterior or independence. Let
`w=OCV(z)-sum(v_i)-H*h`, and let a future input sequence transport each RC state
and hysteresis state as `v_i'=A_i*v_i+B_i*R_i`, `h'=A_h*h+B_h`.
Composition uses the exact affine physical operators. Then

```
V' = w + [OCV(z')-OCV(z)] - I_end*R0
     + sum((1-A_i)*v_i-B_i*R_i)
     + H*h*(1-A_h)-H*B_h.
```

Split B_h into its positive-current and negative-current forcing histories.
This gives twelve additive terms, with three carried and three forced RC terms.
For their vector T, the predictive moment errors relative to a source population
are exactly

```
delta mean(V) = 1' delta mean(T),
delta variance(V) = 1' delta covariance(T) 1.
```

Every cross covariance must be retained. Allocating covariance row sums to
physical groups gives additive bookkeeping; it does not uniquely identify a
causal defect in a fitted conditional. Changing one conditional can change many
downstream groups. Population differences also include finite reference and
generated-sample variation. Means and covariances are necessary diagnostics,
not complete predictive distributions or calibrated coverage.

## A reversal isolates the relevant response functions

For current +I for t seconds and then -I for t seconds, define
`a_i=exp(-t/tau_i)`, `q=I*t/3600`, `a=exp(-gamma_plus*q)` and
`b=exp(-gamma_minus*q)`. Charge balance gives `z'=z`, so the OCV-change
term vanishes exactly. The terminal current is -I. Direct composition gives

```
v_i' = a_i²*v_i - I*R_i*(1-a_i)²,
h' = -1 + 2*b + (h-1)*a*b,
V_rev = w + I*R0
        + sum((1-a_i²)*v_i + I*(1-a_i)²*R_i)
        + H*(1+h)*(1-b) - H*(1-h)*b*(1-a).
```

Thus there is no direct capacity-induced OCV-change error in this probe.
Capacity correlations can still affect the learned joint message, and w
already carries the original OCV dependence. This identity does not excuse
capacity/OCV modeling in other probes or changing-health trajectories.

The response depends on amplitude-weighted transforms, not just rate marginals.
Write `L_X(s)=E[X*exp(-s/tau_i)]` for each RC mode and
`M_X(u,v)=E[X*exp(-u*gamma_plus-v*gamma_minus)]`. Define
`U=H*(1+h)`, `D=H*(1-h)`. The mean reversal corrections are

```
RC carried: E[v_i] - L_vi(2*t),
RC forced:  I*(E[R_i]-2*L_Ri(t)+L_Ri(2*t)),
hysteresis: E[U] - M_U(0,q) - M_D(0,q) + M_D(q,q).
```

Mixed rates, amplitudes and carried state therefore matter even when each
individual marginal is well fitted. Variance requires transforms weighted by
products of amplitudes, plus their cross terms with boundary voltage, R0 and
other modes. Matching a few marginal moments cannot generally match these
functions over all inputs and horizons.

For a small charge exposure, the hysteresis correction is

```
q*(U*gamma_minus-D*gamma_plus)
+ q²*(-U*gamma_minus²/2
      +D*(gamma_plus*gamma_minus+gamma_plus²/2)) + O(q³).
```

These coefficients name the leading mixed moments to inspect. This expansion
is a diagnostic, not a substitute for exact propagation. A rate second-moment
deficit alone does not fix the sign of a voltage error when these weights and
correlations are unknown.

## Why the previous optimizer stopped at zero precision

For the scaled physical rate y, the previous conditional is
`p(y|f) proportional exp(eta(f)*y-kappa*y²/2)` with `kappa>=0`.
Its construction objective obeys

```
d loss/d kappa = (E_source[y²]-E_source_f E_model[y²|f])/2.
```

All eight saved derivatives are positive at kappa=0. Consequently the family
cannot match that conditional second-moment statistic at its optimum. A small
negative kappa is a descent direction in the enlarged family. On a finite
support, it remains normalizable. This is a demonstrated construction-family
restriction, not evidence that more Newton iterations are needed. It does not
by itself explain the reversal discrepancy, generalize to heldout populations,
or account for self-generated conditioning inputs.

There is also a symbolic source for positive curvature. The actual declared
prior is a truncated normal in `log(gamma)`, with mean m and SD s; it is not
uniform in physical rate. Its physical-rate density is

```
p0(gamma) proportional exp(-(log(gamma)-m)²/(2*s²))/gamma,
d² log(p0)/d gamma² = [1+(log(gamma)-m-1)/s²]/gamma².
```

It is log-convex when `gamma > exp(m+1-s²)`. An affine physical-rate scaling
preserves the curvature sign. Meanwhile the bounded natural Gaussian assumes
constant nonpositive log curvature in that coordinate. The posterior need not
retain prior curvature: likelihood, support conditioning, mixture selection and
marginalization all contribute. Therefore this is a structural explanation to
test, not a complete attribution from the prior alone. The mixture can also
create curvature that is absent within each component conditional.

## Reformulating the representation

1. Separate the known reference density from the learned correction:
   `p(y|f)=b(y|f)*exp(theta'phi(y,f)-A(theta,f))`. A normalized transformed
   prior can be a reference b, so a known Jacobian/curvature need not be
   rediscovered by the learned coefficients. This is a representation of the
   already-owned posterior, never multiplication by a second prior. With
   sufficient statistics linear in theta, the conditional fitting objective
   remains convex. A signed quadratic coefficient is the simpler control
   that removes only the nonnegative-precision restriction, without adding
   a scalar. The fixed prior factor and signed curvature address different
   restrictions; they should be tested separately with a frozen protocol.
2. Use physical response amplitudes to expose the needed products. For
   hysteresis, replace (H,h) by `(U,D)=(H*(1+h),H*(1-h))`. This is invertible
   for H>0, with H=(U+D)/2 and h=(U-D)/(U+D), and absolute Jacobian 2H.
   Its joint support is U>0, D>0, U+D<2*H_max; independent boxes would change
   the physical model. The zero-H boundary is singular and requires an
   explicit convention if atoms on that boundary are later allowed.
   A further response scaling, P_plus=D*(1-exp(-gamma_plus*q_star)) and
   P_minus=U*(1-exp(-gamma_minus*q_star)), is invertible at a fixed positive
   public charge scale q_star. Its absolute Jacobian is
   `2H*(1-exp(-gamma_plus*q_star))*(1-exp(-gamma_minus*q_star))`.
   It has the same dimension, but its transformed support and normalizer
   must be implemented; retaining the old rectangular support is invalid.
3. Use discrepancies in the exact response functions above to decide which
   representation needs repair. Fit construction data; qualify heldout
   physical means, variances and cross terms. The objective should preserve
   useful response evidence across a declared range of inputs, not merely
   stationarity in an arbitrary coordinate chart or one favorable probe.
   A normalized joint posterior is still needed for reuse and uncertainty;
   a table of probe moments alone is insufficient.

These are prospective design changes. This study changes no density, solver,
prior ownership or aging law. The saved two-component message is still 2,496
numeric bytes. A signed shape scalar or replacing two coordinates does not by
itself add retained coefficients, although support/workspace costs are not yet
qualified. A twelve-term mean and symmetric covariance take 720 numeric bytes
per probe as diagnostics; they are not a replacement compressor. Complete
Cortex-M23 SRAM, causal updates and indefinite accumulation remain open.
