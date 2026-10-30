# Forced RC coefficient recurrence

The derived recurrence is implemented and the frozen 36-case comparison is
complete. On the same 97 local query points, thirteen coefficients per forced
and free RC component reduce the 4,096-record discrepancy from **2.42538 to
0.134332 NLL**, an **18.06x** improvement over the free-response-only repair.
At 64 records the improvement is **1,945.65x**, to **0.000027296 NLL**.
Both results approach the independent exact-all-RC controls.

These are representation results on stationary fabricated prefixes of 1.874 s
and 119.954 s. They do not establish parameter convergence, calibrated coverage,
aging behavior, rolling-estimator throughput or M23 deployment readiness.
All historical artifacts remain unchanged. Work is on
`experiments/forced-rc-kernel-001`; the recorded revision plus source snapshots
identify the implementation, including uncommitted dependencies.

See the [frozen plan](plan.json), [implementation](forced.py),
[primary receipt](attempt001/receipt.json), [summary](summary.json) and
[verification](verification.json). No optimizer or truth inputs were used.

## What changed

The previous experiment represented free decay with coefficients of

```
A(z,t) = exp[-ct(1+z)/(1-z)] = sum beta_n(t) z^n
z = (lambda-c)/(lambda+c), lambda=1/tau
c = sqrt(lambda_min lambda_max), |z| <= rho < 1.
```

The pivot and rate support are inherited public bounds, or the frozen public
half-SD box. The local box is not claimed to be an identified posterior region.
The [earlier derivation](../free_rc_kernel_001/README.md) establishes the free
carrier construction, `|beta_n(t)|<=1` and its truncation bound.

For piecewise-constant current during a received interval, the physical forced
state per unit resistance obeys

```
f_new(lambda) = exp(-lambda dt) f_old(lambda)
                + I (1-exp(-lambda dt)).
```

Consequently its first K series coefficients obey

```
f_new[n] = sum_{j=0}^n beta_j(dt) f_old[n-j]
           + I (1[n=0]-beta_n(dt)), 0 <= n < K.
```

No coefficients beyond K-1 can contribute to these retained coefficients. Thus
truncated convolution gives the exact first K coefficients in formal arithmetic,
even through arbitrarily ordered current changes. The initial forced state is
zero; uncertain entering polarization stays in its separate free component.
`-expm1(-c dt)` evaluates the constant drive coefficient without subtracting
nearly equal numbers. Actual intervals and current order are preserved.

Each mode emits forced row coefficients `-f_n/sigma` and query features `R z^n`;
free rows/features remain `-beta_n/sigma` and `v_initial z^n`. All OCV,
hysteresis, observed-voltage and ohmic columns stay in the complete residual.
Full QR retains every likelihood cross term. Analytic derivatives use the
original sixteen coordinates; the parameter density and priors are unchanged.

The endpoint uses retained forced coefficients plus the exact queried free
decay, as in the predecessor. The approximation of historical free rows is
reported separately from endpoint state accuracy. No observation is forgotten,
and this physical exponential is not a discount on evidence.

For a chronological RC block with affine operator `(A,F)`, composition is

```
(A2,F2) after (A1,F1) = (A2*A1, A2*F1+F2) modulo z^K.
```

This is associative and preserves uncertain entering state. It is an RC state
composition law, not yet a complete independent event-history algebra for OCV,
hysteresis, health transitions and likelihood ownership. The separate QR merge
test uses already aligned global residual rows, without counting any row twice.

## Two physically derived error bounds

Let current `I_j` apply on `(t_(j-1),t_j]`, with `I_0=0`, and define
`delta I_j=I_j-I_(j-1)`. The independently derived current-step expression is

```
f(t_k,lambda) = I_k - sum_{j=1}^k delta I_j exp[-lambda(t_k-t_(j-1))].
```

It follows from superposing the step responses, or telescoping the original
recurrence. Combining it with the free-response bound gives

```
|f-f_K| <= TV_k(I) rho^K/(1-rho),
TV_k(I) = sum_{j=1}^k |delta I_j|.
```

The initial current step is included. This bound reflects the actual input
changes rather than a fitted history lifetime. Total variation can grow during
long use, so this form alone is not a uniform duration bound.

A second bound follows directly from the continuous response integral for the
same piecewise-constant current. For complex `|w|=r<1`, set
`lambda=c(1+w)/(1-w)`, which has positive real part. If `|I(u)|<=Imax`, then

```
f(w,t) = integral_0^t lambda exp[-lambda(t-u)] I(u) du
|f(w,t)| <= Imax |lambda|/Re(lambda)
          = Imax |1-w^2|/(1-r^2)
          <= Imax (1+r^2)/(1-r^2).
```

Cauchy's coefficient estimate and a geometric tail therefore give, for every
`t>=0` and `rho<r<1`,

```
|f-f_K| <= Imax (1+r^2)/(1-r^2) (rho/r)^K / (1-rho/r).
```

The study fixes `r=(1+rho)/2` before evaluation, and checks the smaller of these
two bounds at every sampled time/query. For each prefix, the observed running
maximum current is a valid bound over that prefix. A guarantee for future time
would require a valid future current bound. Multiplication by uncertain
resistance converts the forced-state bound in amperes into voltage error.

These are exact-arithmetic bounds for stationary rates. They do not certify
floating-point recurrence error, uncertain health transitions, likelihood
derivatives, accumulated NLL error or indefinite posterior coverage. They
establish no SCM/NAIA/D2 theorem transfer.

## Frozen comparison

All candidates keep degree-four physical-rate hysteresis and degree-twelve
charge-coordinate OCV. For each of two prefixes and two domains, the study
includes three predecessor baselines plus six joint candidates: K=5,9,13 for
both the time kernel and matched log-tau Chebyshev interpolation. The matched
control advances the original forced recurrence at K fixed interpolation nodes;
it uses the same number of residual features. K=5 reproduces the old degree-four
representation, apart from numerical rounding.

The metric is the range of represented-minus-reference NLL over the unchanged
queries. It describes tested pairwise likelihood distortion, not battery state
error. No 0.1-NLL physical acceptance gate or post-result degree selection is used.

| Representation | Local 64 | Local 4096 | Full-public 64 | Full-public 4096 |
| --- | ---: | ---: | ---: | ---: |
| Original physical-hysteresis baseline | 0.191261 | 4.707512 | 2,218.19 | 39,982.81 |
| Free kernel only, K=13 | 0.0531084 | 2.425380 | 598.57 | 9,941.12 |
| Joint time kernel, K=5 | 1.011273 | 85.884933 | 26,592.79 | 2,685,673.76 |
| Joint time kernel, K=9 | 0.000197334 | 0.132954 | 685.43 | 144,910.06 |
| Joint time kernel, K=13 | 0.000027296 | 0.134332 | 59.56 | 3,222.32 |
| Joint log-tau interpolation, K=9 | 0.000028904 | 0.134287 | 6.33 | 3,249.45 |
| Joint log-tau interpolation, K=13 | 0.000027293 | 0.134332 | 0.24224 | 3,175.68 |
| Exact all RC, raw diagnostic | 0.000027293 | 0.134332 | 0.23531 | 3,176.97 |

The coefficient recurrence is useful algebraically, but does not universally
outperform interpolation. Broad support is much harder, especially for the
kernel at K=9. At local K=9, the slightly lower total error than K=13 reflects
cancellation with remaining component errors; it is not greater RC accuracy.
Likewise, exact-all-RC is a mechanism reference, not a mathematical lower bound
on the error of all approximations.

For the local K=13 kernel, the largest forced-component voltage error at
4,096 records is **7.67e-14 V**, down from **2.12e-7 V** in the forced part of
the predecessor. The retained RC endpoint error is at most **4.88e-14 V**;
the inherited hysteresis endpoint still has error **4.65e-8** in its own state
coordinate. Precision of RC representation does not imply physical identification.

The new long-prefix worst-pair decomposition is:

| Component | Signed NLL contribution |
| --- | ---: |
| Forced hysteresis | +0.1217564693 |
| Free hysteresis | +0.0124657425 |
| OCV | +0.0001094973 |
| All forced/free RC combined | approximately +0.0000000687 |

Hysteresis accounts for **99.9184%** of this pair's discrepancy. Exact
hysteresis substitution leaves **0.000712227 NLL** across the entire local
query set; a new worst pair appears, so this is not the same-pair OCV contribution.
At 64 records OCV dominates: exact OCV substitution leaves **3.82e-8 NLL**.
Increasing RC order further would not target either remaining local discrepancy.

## Qualification and arithmetic

The primary completed **5,059 checks** and retained **27 aggregate numerical
flags**. No hard source/domain/nonfinite/work-limit failure occurred.

- Independent current-step superposition agrees with recurrence coefficients
  to a maximum absolute gap of **6.52e-16** on its frozen prefix checks.
- Zero current, constant current, signed current with zero/uneven intervals,
  chronological affine block composition, associativity and carried state checks
  all passed the inherited numerical allowances.
- Original-C cost/endpoint reproduction, all feature finite differences,
  direct/QR/merged costs, GN at the public mean, forced-endpoint consistency and
  sampled symbolic bounds all passed.
- The represented-zero-residual test gave direct cost **5.23e-22** and QR cost
  **4.38e-19**, without clipping.

The 27 flags are gradient arithmetic comparisons. Six are new joint candidates
on the short full-public prefix, at no more than **1.094** times the frozen
allowance. The rest concern inherited baseline/free-only arms and the optional
equilibration diagnostic. Both local joint K=9/K=13 candidates pass their
primary cost/gradient/GN numerical controls. The long full-public joint arms
also pass those controls despite large *approximation* errors.

Column-norm equilibration was frozen as a diagnostic before this study. It is
not an automatic fix: it worsens the original baseline's gradient comparison,
reaching **13.19** allowances. The new long-prefix joint K=9/K=13 arms pass both
raw and equilibrated gradient comparisons, including the frozen long-double
mean/worst-gradient witnesses. The primary raw QR results and every flag remain
recorded. No alternative arithmetic was silently substituted for a failed result.
This finite evidence does not certify arbitrary QR conditioning or optimizer
behavior.

The run took **17.30 s** on this host. It counted 1,751,360 model-node steps and
4,683,684 carrier values, below the respective frozen 3,000,000 and 10,000,000
limits. The convolution counter counts 11,531,568 multiply-adds contributing to
retained coefficients. NumPy computes full convolution before truncation;
the [accounting review](accounting_review.json) records a conservative full-work
upper bound of **23,063,136**, still below 30,000,000. The original receipt is
preserved, including this counter distinction. These study costs are not a
measurement of incremental firmware or rolling-estimator throughput.

## Storage and next decision

| Representation | Features | Packed QR, B | Complete prospective reserve, B |
| --- | ---: | ---: | ---: |
| Previous free-only K=13 | 99 | 39,600 | 48,288 |
| Joint K=5 | 75 | 22,800 | 30,856 |
| Joint K=9 | 99 | 39,600 | 48,520 |
| Joint K=13 | 123 | 61,008 | 70,792 |

The joint K=9 representation achieves the local improvement at almost the same
storage as the old free-only K=13 layout. Nevertheless, all remain above the
entire **10,240-B SRAM target**, even considering only the packed factor.
The ledger retains inherited boundary reservations conservatively, adds forced
coefficient state, and includes query scratch, source/domain metadata and
nonbank solver/runtime reservations. Optional equilibration adds `8F` bytes.
It is a prospective C plan, not a measured implementation or Python footprint.

Retain this result as the joint RC desktop reference, alongside matched
interpolation. Do not spend further RC degree increases on the remaining local
error. The next design should address **structured likelihood storage**, with
explicit mixed terms and numerical conditioning, and treat the now-isolated
hysteresis/OCV approximations according to useful SOC/capacity sensitivity rather
than an arbitrary NLL cutoff. Raising every basis degree cannot meet SRAM.
Broad-support fidelity, health evolution, complete event-history composition
and long-duration closed-loop qualification remain open before integration with
the fast rolling estimator.

Reproduce in a new exclusive directory:

```sh
python3 -B experiments/forced_rc_kernel_001/analyze.py experiments/forced_rc_kernel_001/new_attempt
```

An exit status of one can mean a **completed** comparison with retained numerical
flags; inspect `receipt.json` to distinguish that from a hard failure. The
archived source copies and their hashes are authoritative.
