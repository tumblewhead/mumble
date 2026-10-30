# Partition-specific transport and probability coordinates

This experiment separates three tasks: choose deterministic physical transport
views, represent one joint probability message, and fit that message using the
density actually evaluated. It does not add independent measurements or split
the voltage likelihood into independent physical-family likelihoods.

Transport uses the existing physical model:

- `kappa=1/Q`, so `z'=z-kappa*DeltaC` over an interval with that capacity.
  Under health evolution, use the capacity for each interval and carried SOC;
  never rescale all old charge with today's capacity.
- For the illustrative OCV, `r=tanh(8*(z-.5))` and
  `r'=(r-b)/(1-r*b)`, `b=tanh(8*kappa*DeltaC)`. This is an exact Möbius
  transport view; the complete OCV includes a linear SOC term, so its output
  is not linear in `r`.
- For RC, `lambda=1/tau`, `A=exp(-lambda*dt)` and
  `[v',R]'=[[A,I*(1-A)],[0,1]]*[v,R]'`. Chronological matrix multiplication
  carries both free and forced response. Rates stay uncertain.
- For fixed current direction `s`, hysteresis obeys
  `log(1-s*h')=log(1-s*h)-gamma_s*abs(I)*dt/3600`.
  Reversals switch the chart; saturation makes this log view singular.
  The affine `(h,1)` or derived `(H*h,H)` transport remains available without
  dividing by H. No independent parameter or prior is assigned to H*h.

These transport views are linked deterministically to the physical state. They
are not extra uncertain state variables, stored observations, or a new aging
law. This experiment tests their identities and domain restrictions, not a
complete streaming history algebra or compressed likelihood bank.

The probability comparison keeps the existing response coordinates
`F_i=(1-exp(-D_i/tau_i))*v_i`, `G_i=(1-exp(-D_i/tau_i))*R_i` and physical
boundary rest voltage `w=OCV(z)-sum(v)-H*h`. The D values are the same fixed
public mode-scale values as the previous study. It compares:

| Partition | Current probability chart | Specialized probability chart |
| --- | --- | --- |
| RC poles | Bounded logit of log tau | Cayley rate `u=(lambda-c)/(lambda+c)`, scaled by public rho |
| Hysteresis rates | Bounded logit of log gamma | Physical gamma, affinely scaled on public support |
| Capacity | Bounded logit of log Q | Inverse capacity, affinely scaled on public support |
| R0, H, h | Bounded logits | Physical values, affinely scaled on public support |
| RC amplitudes | F1..F3,G1..G3 | Same F/G coordinates |
| SOC/measurement | Physical boundary voltage w | Same w coordinate |

For RC mode i, `c_i=sqrt(lambda_min*lambda_max)` and
`rho_i=tanh((log(tau_max)-log(tau_min))/4)`. The specialized pole coordinate
is `u_i/rho_i` in `(-1,1)`. Its absolute derivative with respect to log tau
is `2*c_i*lambda_i/(rho_i*(lambda_i+c_i)^2)`. Inversion uses
`lambda_i=c_i*(1+rho_i*y_i)/(1-rho_i*y_i)`. Physical gamma and inverse
capacity derivatives contribute respectively `2*gamma/range_gamma` and
`2*kappa/range_kappa` in absolute value. No logit is applied afterward to
these physical intervals: doing so would undo part of the intended change.

All16 coordinates are represented as a triangular sequence of scalar Gaussian
conditionals. Coordinate j has a mean linear in all preceding coordinates and
its own scale. Each bounded conditional includes its exact normalizer. The
first nine current-chart coordinates are unbounded; their triangular Gaussian
factorization is algebraically identical to the previous full9 Gaussian.
The specialized first nine coordinates have support `(-1,1)`. The F/G and
voltage bounds depend on preceding physical variables as in the previous study.
Every region remains a normalized full16 density. Regions are alternatives in
one mixture; the initial prior and observation/transition intervals are owned
once, exactly as before. Physical-coordinate density includes the full chart
Jacobian, including `product(a_i^2)` and `OCV'(z)`.

There are two fitting objectives for each coordinate set. The control uses
unbounded least-squares moments and then evaluates the supported normalized
density. The repaired method minimizes its full mean negative log density:

```
L = mean(.5*((target-mu)/sigma)^2 + log(sigma) + .5*log(2*pi)
         + log(Phi((upper-mu)/sigma)-Phi((lower-mu)/sigma))).
```

The support endpoints are fixed functions of the observed conditioning
coordinates during fitting. Their normalizer therefore participates in all
coefficient and scale derivatives. Construction samples approximate one
posterior; the objective is density approximation to those samples, not new
battery evidence. Covariance is never divided by sample count.

Write `a=(lower-mu)/sigma`, `b=(upper-mu)/sigma`, `p_a=phi(a)/Z`,
`p_b=phi(b)/Z`. Derivatives are
`dL/dmu=mean((mu-target)/sigma^2+(p_a-p_b)/sigma)` and
`dL/dlog_sigma=mean(1-((target-mu)/sigma)^2+a*p_a-b*p_b)`.
The coefficient derivative multiplies the per-row mu derivative by every
preceding feature. Use construction-only QR whitening and residual scaling
for numerical conditioning; invert them exactly before storing coefficients.
This does not change the represented family or introduce covariance shrinkage.

The finite optimizer is safeguarded BFGS with a registered gradient tolerance,
iteration/evaluation caps and backtracking. A finite low objective is not proof
of stationarity or a global optimum. Retain unresolved stops and their final
gradient instead of promoting them to converged fits. Uniform/exponential
limits of a bounded Gaussian can occur as sigma grows, so finite stationary
parameters are not guaranteed. No regularizer or physical cutoff is introduced
to force them.

The frozen experiment uses two fixed capacity-partition components at8/32saved
records: two coordinate sets times two fit methods, eight cases. This isolates
the two interventions; it does not repeat the already inconclusive search over
region organizations/counts. All existing rest/load/reversal probe horizons
remain. The existing first two populations construct and last two evaluate;
held-out samples and truth never affect optimization.

Component construction membership and weights stay fixed at the original
capacity partition. This fits each component's conditionals on its assigned
samples; it is not EM or a global maximum-likelihood fit of the overlapping
mixture. Stationarity claims apply only to those conditional objectives.

Storage is unchanged:136 triangular mean coefficients+16log scales+1log weight
=153doubles/component. Two components plus three edges and three response
intervals require **2,496B**; four would require **4,960B** (not tested here).
Fixed chart constants can be ROM; schema/model/source metadata, query scratch,
solver/queue/stack and constructor/update workspace remain additional. The
desktop builder retains construction samples and is not an SRAM-only update.
