# RC response coordinates with uncertain time constants

Keep the previously repaired physical boundary voltage `w`. For mode `i` and
fixed declared response interval `D_i > 0`, define

```
a_i(tau_i) = 1 - exp(-D_i/tau_i)
F_i = a_i * v_i
G_i = a_i * R_i.
```

These are the free-voltage release and forced-response coefficient of the
existing RC model. They introduce no extra observation. The unknown `tau_i`
remains a coordinate. Given it, `0 < a_i < 1`, so `v_i=F_i/a_i` and
`R_i=G_i/a_i` recover the original quantities exactly. The physical support is
`-.25*a_i < F_i < .25*a_i` and `0 < G_i < a_i` for the current declared bounds.
Independent logit normalization against these moving bounds would cancel the
coordinate change; retain physical `F_i,G_i` instead.

The nine base variables are the three log time constants, two log hysteresis
rates, log capacity, R0, H and h. Their bounded logits retain joint uncertainty.
Generate `F1,F2,F3,G1,G2,G3,w` sequentially, each with a Gaussian mean linear
in **all preceding coordinates**, residual variance, and its own exact
conditional support normalizer. `w` has the same dependent OCV interval as
before, computed after recovering RC voltages. This is a normalized conditional
chain, not a globally truncated multivariate Gaussian. Its ordering is frozen;
the experiment does not search orderings against held-out outcomes.

The full coordinate Jacobian is

```
OCV'(SOC) * product_i a_i^2 * product_base logit_derivatives.
```

Derivatives of `a_i` with respect to time constants and the off-diagonal
derivatives in `w` do not change this determinant: in the declared order the
transform is block triangular. For a capacity atlas, substitute the existing
bounded `t` coordinate and its Jacobian for the capacity logit.

Two response frames are predeclared: `D_i=1 s` for all modes, matching the
previous diagnostic, and `D_i=sqrt(tau_i_lower*tau_i_upper)` based only on public
mode supports (about0.0474,0.4743,6.7082seconds). The latter is the midpoint of
each public log-time-constant interval, not a learned timescale or truth-based
center. A physical-amplitude control uses `a_i=1` with the same seven-step
conditional density. It isolates changes from replacing bounded logits with
conditional physical amplitudes. A saved voltage-only baseline is also scored
on the same extended future probes.

Within each region, regress the untruncated transformed data and then normalize
each scalar conditional over its physical support. This is a declared moment
projection followed by conditional normalization, not a truncated-family MLE.
Support correction can change means, covariance and modes; record it and judge
the resulting density. Never divide covariance by construction sample count,
clip draws, freeze a nuisance parameter or add the inherited prior twice.

For mixtures, nine base means plus45 Cholesky entries use54 doubles. Seven
conditionals require `sum(j+2,j=9..15)=98` doubles; one log weight gives153
doubles per region. Atlas charts retain8 base intercepts+8 slopes+36 factor
entries=52, plus98 conditional entries, quadratic parameters/log-normalizer
and weight=4, giving154 doubles. Thus packed payload is the previous
2,472/4,936B (mixture) or2,488/4,968B (atlas), **plus24B for three frame values**:
roughly **2.5kB with two regions or5.0kB with four**. Metadata, query scratch,
solver state and construction/update workspace are additional. No complete
10,240B SRAM implementation follows from this calculation.

All messages describe one posterior and own exactly the same source intervals
and initial prior as their inputs. There is still no streaming Bayesian update,
physical-aging transport, re-centering algebra or firmware implementation here.
