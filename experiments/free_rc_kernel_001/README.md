# Free RC history: derivation and frozen comparison

The free response can be represented separately, while keeping every likelihood
cross term. On the same 97 local queries, replacing all three free RC responses
reduces the 4,096-record discrepancy from **4.70751 to 2.42538 NLL** with thirteen
coefficients per mode. Nine coefficients give **2.42549**. The exact-free raw
control gives **2.42538** too: further free-response accuracy alone no longer
addresses the main remaining discrepancy. Current-driven RC response is next.

This is a stationary representation experiment, not a fit, aging demonstration,
SOC/capacity accuracy result, or qualified M23 compressor. The full public domain
remains much harder. None of the prospective complete layouts fits 10,240 B.

The [frozen plan](plan.json), [primary receipt](attempt001/receipt.json),
[arithmetic follow-up](arithmetic001/receipt.json) and [summary](summary.json)
retain failures and provenance. The primary contains 52 cases and 6,827 checks;
52 numerical comparison flags were collected rather than aborting. They all
concern long-prefix gradients, including the unchanged baseline.

## Physical object and complex coordinate

For one mode, the carried initial voltage contributes
`v_initial exp(-lambda t)`, where `lambda = 1/tau`. The rate remains uncertain.
Choose a fixed positive pivot `c = sqrt(lambda_min lambda_max)` from the declared
support, and set

```
z = (lambda-c)/(lambda+c)
lambda = c (1+z)/(1-z)
rho = max |z| = tanh(log(lambda_max/lambda_min)/4) < 1.
```

This Cayley coordinate maps positive physical rates inside the real diameter
of the complex unit disk. Complex analysis supplies an approximation bound;
it does not introduce a second physical state or discard uncertainty. Queries
and derivatives still use the original sixteen coordinates and priors. No
prior Jacobian is added: the coordinate only represents a deterministic response.

Define `L_n(x) = sum_{j=0}^n binomial(n,j) (-x)^j/j!`. Summing this expression
over `n` gives

```
sum L_n(x) z^n = exp(-x z/(1-z))/(1-z).
b_n(t) = exp(-ct) L_n(2ct)
beta_0(t) = b_0(t)
beta_n(t) = b_n(t)-b_(n-1)(t), n >= 1
A(z,t) = exp[-ct(1+z)/(1-z)] = sum beta_n(t) z^n.
```

The finite representation retains `n=0,...,K-1`. Its entering value is exact:
`beta_0(0)=1`, and the other coefficients vanish. The implementation computes
the Laguerre recurrence in binary64; it does not need to store observations to
evaluate these free-response carriers. Historical likelihood storage is separate.

For `|w|<1`,
`Re[(1+w)/(1-w)] = (1-|w|^2)/|1-w|^2 > 0`.
Thus `|A(w,t)|<=1` for every `t>=0`. Cauchy's coefficient estimate on a circle
of radius `r<1`, followed by `r` increasing to one, gives `|beta_n(t)|<=1`.
Consequently, in exact arithmetic,

```
|exp(-lambda t) - sum_{n=0}^{K-1} beta_n(t) z^n|
    <= rho^K/(1-rho), for every t >= 0 in the declared rate support.
```

An optional tighter bound for `rho < r < 1` is
`exp[-ct(1-r)/(1+r)] (rho/r)^K / (1-rho/r)`.
These are symbolic response bounds; binary64 endpoints and recurrence arithmetic
are not interval-certified. They are not uniform lifetime NLL guarantees:
residual cross terms, observation count and parameter-domain changes still
matter. Time-varying rates under aging are outside this stationary derivation.

## Composition and joint likelihood

The physical identity `A(z,t+s)=A(z,t)A(z,s)` implies

```
beta_n(t+s) = sum_{j=0}^n beta_j(t) beta_(n-j)(s).
```

Truncated coefficient convolution is therefore exact and associative in
`R[z]/(z^K)`. Multiplying two decoded truncated scalar responses is a different
operation and is not asserted to preserve the retained coefficients.

This gives a closed time-translation algebra for the free state. The experiment
also merges QR factors whose rows already share the same global coordinates.
It does **not** establish independent event-block composition for the complete
OCV/forced-response/hysteresis history, especially across health transitions.

At each observation the selected free columns are `-beta_n(t)/sigma`, with
query features `v_initial z^n`, where `sigma=0.001 V`. All other columns remain.
The complete normalized residual has the form `D phi(x)`. A full QR factor
preserves its cost, gradient and Gauss–Newton matrix in exact arithmetic:

```
cost = 1/2 ||R phi||^2
gradient = (R J_phi)^T (R phi)
GN = (R J_phi)^T (R J_phi).
```

This retains free/observed, free/OCV, free/forced, free/hysteresis and free/free
products. Free/free products correspond to source-time Laplace sums evaluated
at `lambda_i + lambda_j`; the other products need their own source weights and
uncertain parameters. A compressed scalar cost polynomial alone would not
necessarily retain the residual-Jacobian information required by GN.

No earlier observation is discounted. The exponential is the physical RC state
response; the likelihood of the observation remains in the factor. No claim of
SCM/NAIA/D2 equivalence or proof transfer is made.

## Frozen results

The predecessor is degree-four log-tau RC plus degree-four physical-rate
hysteresis and degree-twelve charge-coordinate OCV. The frozen fabricated
prefixes span 1.874 s and 119.954 s, with actual intervals and order preserved.
No optimizer, truth, new centering or posterior support selection is involved.
The local domain is the inherited public half-SD box, not demonstrated posterior
concentration. Every original out-of-domain query is rejected.

The metric is the oscillation of represented-minus-reference NLL over the
same query set; it measures tested pairwise log-likelihood distortion, not
estimation error. The historical 0.1 NLL comparison is not used as a physical gate.

| Representation, all three free modes | Local 64 | Local 4096 | Full-public 4096 |
| --- | ---: | ---: | ---: |
| Predecessor | 0.191261 | 4.707512 | 39,982.81 |
| Time kernel, K=5 | 1.101148 | 103.796047 | 2,176,639.57 |
| Time kernel, K=9 | 0.053095 | 2.425493 | 90,745.27 |
| Time kernel, K=13 | 0.053108 | 2.425380 | 9,941.12 |
| Log-tau interpolation, K=9 | 0.053110 | 2.425129 | 10,461.28 |
| Log-tau interpolation, K=13 | 0.053108 | 2.425380 | 10,378.84 |
| Exact free responses, raw control | 0.053108 | 2.425380 | 10,387.86 |

The kernel is not a universal accuracy win over matched interpolation. K=5 is
worse; local K=9 is near the exact-free result, but full-public K=9 is worse than
the predecessor. Full-public K=13 can partly cancel errors in other components,
so an oscillation below the exact-free control is not evidence that the free
response is more accurate than exact evaluation. The exact-free control is a
mechanism reference, not a lower bound on total discrepancy.

For the local K=13 all-mode kernel, the largest free-component voltage error
at 4,096 records is **3.57e-13 V**, compared with **3.74e-7 V** previously.
That millionfold component improvement yields only about **1.94x** improvement
in total NLL oscillation because the other components now dominate. At its new
worst query pair, signed contributions are:

- Fastest forced RC: +2.048582 NLL (84.46% of the total).
- Middle forced RC: -0.041796 NLL.
- Slowest forced RC: +0.439582 NLL.
- Hysteresis combined: -0.021033 NLL.
- Free RC combined: approximately +3.48e-8 NLL; OCV: +0.000045 NLL.

Witnesses change when a component is repaired; signed percentages must not be
treated as guaranteed gains from removing that component. Repairing only the
slowest free mode reaches 2.415520 NLL locally with K=9, essentially its exact
control. Repairing the other free modes removes a small accidental cancellation.

The local K=9 symbolic attenuation bounds are approximately `1.07e-7`, `1.07e-7`
and `1.14e-6`. On the full public support they are `0.00573`, `0.00573`, `0.04561`.
This difference follows from the frozen rate ranges, without fitted tuning.

## Numerical controls and resource limits

All original-C cost/endpoint comparisons, feature finite differences, GN,
cost/merged-cost checks, endpoint free-part checks and sampled analytic-bound
checks passed their frozen numerical allowances. The maximum coefficient time
composition discrepancy was **8.50e-16**. The zero represented-residual control
gave direct cost **4.38e-22** and QR cost **1.35e-17**, without clipping.

The primary flags are 52 aggregate gradient comparisons, two for each of the
26 long-prefix cases. Maximum allowance ratio is **6.87**; the largest absolute
gradient difference across flagged comparisons is **4.29e-4** in original
parameter units. These are arithmetic discrepancies in the represented model,
separate from its several-NLL approximation discrepancy. They remain failures
of the frozen strict comparison, not a qualified gradient-parity pass.

The [separately frozen follow-up](arithmetic_plan.json) compared two evaluation
orders on four cases, then used long double at three witnesses per case. The
alternative contraction order did not fix the differences. Direct binary64
gradients agree with the extended-precision represented rows at those witnesses;
the single QR factor differs by up to 6.87 allowances. Partitioned/merged QR is
closer at those witnesses (all below 0.155 allowances). This localizes the observed
effect to numerical factorization/evaluation, rather than establishing a wrong
analytic derivative. It does not certify all untested gradients or predict the
effect on an optimizer. Equilibration or a more accurate incremental QR deserves
a separate bounded test before deployment.

| Layout | Features | Packed QR alone, B | Complete prospective reserve, B |
| --- | ---: | ---: | ---: |
| Predecessor | 75 | 22,800 | 30,336 |
| K=9, slowest free only | 79 | 25,280 | 33,360 |
| K=9, all free modes | 87 | 30,624 | 38,896 |
| K=13, all free modes | 99 | 39,600 | 48,288 |

The ledger includes boundary/source reservations, nonbank solver/runtime
reservations and expanded query scratch. It is a prospective C allocation, not
the Python process footprint or a measured integrated workspace. Even the
numeric factor alone exceeds the entire 10,240-B target. Faster per-query
formulas do not solve that memory problem. No firmware timing result follows.

The primary took 11.15 s on this host, the arithmetic diagnostic 1.35 s. Together
they consumed an upper-accounted 1,609,920 model-node steps, below the frozen
3,000,000 cap. The primary counted 2,716,848 new free scalar carrier values;
the follow-up adds 221,184. These are study costs, not rolling-estimator throughput.
Source hashes were unchanged and original receipts were preserved.

## Next specific experiment

Use the same coefficient algebra for the **forced RC response**, retaining the
free/forced split and all likelihood cross terms. This follows directly from
the original piecewise-constant-current recurrence. If `f` is forced voltage
per unit resistance and `B(z,dt)` is the free transition series, then

```
f_new(z) = B(z,dt) f_old(z) + I (1-B(z,dt))
f_new[n] = sum_{j=0}^n beta_j(dt) f_old[n-j]
           + I (1[n=0]-beta_n(dt)), n < K.
```

Truncated convolution preserves the first K coefficients exactly in formal
arithmetic. For a chronological block, the affine pair `(A,F)` composes as
`(A2*A1, A2*F1+F2)`. This is a physically derived update for actual input
intervals; there is no threshold, fitted forgetting rate or state reset.
Arbitrary-input forced-response error bounds and stable finite arithmetic still
need qualification; the free-response uniform bound cannot simply be reused.

Compare this unified RC representation against matched log-tau interpolation
and exact-RC controls on the same prefixes, with a plan frozen before evaluation.
Only after the remaining component mechanism and arithmetic are understood
should we test structural storage reduction and reconnect to the fast rolling
solver. Event-boundary source ownership, evolving health, learned OCV and
long-duration coverage remain explicit open work.

Reproduce in new, exclusive output directories:

```sh
python3 -B experiments/free_rc_kernel_001/analyze.py experiments/free_rc_kernel_001/new_attempt
python3 -B experiments/free_rc_kernel_001/arithmetic.py experiments/free_rc_kernel_001/new_arithmetic
```

The primary exits nonzero when it finishes with numerical mismatch flags; its
receipt, rather than the exit status alone, distinguishes completion from an
interrupted or hard-failed study. The arithmetic receipt likewise records its
remaining mismatches. Archived source snapshots and hashes are authoritative.
