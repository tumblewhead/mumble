# Bounded stationary prototype and centroid trajectory study

The stationary prototype and centroid controls are implemented: **1,725 finite
checks pass** (1,717 main checks plus eight targeted causal-spline checks).
The prototype preserves the conditional amplitude likelihood and carries an
explicit accumulated representation bound. Its fixed-center approximation is
**not accurate enough on the tested nonzero-width domains**; it is an error-
accounting baseline, not a selected compressor.

The user's proposal to track a centroid trajectory separately from the
statistical shape is useful as a coordinate decomposition. It becomes a
compression method only if the curve's remainder and its relationship to
residual uncertainty are retained. Four knots are a candidate, not an established
aging law. [Derivation](derivation.md), [plan](plan.json),
[main results](attempt001/result.json), [causal control](causal001/result.json)
and [summary](summary.json) retain the evidence and scope.

![Envelope growth and same-knot trajectories](attempt001/envelope_and_centroid.png)

## Implemented stationary operator

[envelope.py](envelope.py) retains a nine-amplitude square root at a fixed public
conditioning point, its nonlinear domain, source ownership, physical transport
and four outgoing RC/H*h error bounds. For nonlinear arguments within the
domain it returns an approximate likelihood with a representation bound.
It rejects outside-domain queries, duplicate input and unsupported SOC domains.
No posterior, initial prior or rolling estimate is added as evidence.

The bounds come from subtracting the physical RC/hysteresis recurrences and
using monotone OCV extrema. They retain cross terms in the likelihood factor.
The accumulated scalar E2 is the sum of squared voltage envelopes normalized
by measurement variance. For the retained residual factor S,

```
|exact NLL - represented NLL| <= ||S*[alpha;1]||*sqrt(E2) + E2/2.
```

An amplitude-box bound on the same residual norm supplies a uniform likelihood
envelope. Compatible block composition carries earlier outgoing-state errors
into later likelihood bounds using physical free-response attenuation weights.
It never resets the spent budget. Blockwise bounds may be looser than rowwise
bounds; their equality or associativity is not claimed.

These inequalities are derived in real arithmetic. Float64 evaluation is not
outward rounded, and numerical error remains explicitly unresolved. The finite
controls use a separately registered arithmetic allowance. The zero-width
domain has zero mathematical representation defect and measured NLL roundoff
up to 2.31e-7; this is not a zero numerical-error certificate.

## Results and what they rule out

Eighteen cases use public, narrow conditional and singleton domains, each with
mixed-current or rest inputs at 64/256/1,024 records. The narrow box has halfwidth
1% of the public coordinate width around the public mean; it is not a learned
posterior region. All amplitude coordinates retain their inherited support.
Observations are fabricated independently of queried model parameters.

There are 216 query comparisons to the existing C physical recurrence.
Likelihood and outgoing-state discrepancies lie within the implemented
representation envelopes plus registered arithmetic allowances. Merge, ownership,
domain rejection and failure-atomicity controls pass.

At 1,024 records (29.696 seconds):

| Domain / stimulus | Uniform NLL envelope | Largest sampled absolute NLL discrepancy |
| --- | ---: | ---: |
| Public / mixed | 6.23e9 | 5.05e7 |
| Public / rest | 6.16e8 | 8.87e7 |
| Conditional / mixed | 7.93e6 | 1.25e6 |
| Conditional / rest | 2.92e6 | 1.78e6 |

These large discrepancies show that simply freezing the nonlinear response at
one center is insufficient on these domains; this is not merely a loose bound.
The corresponding uniform posterior-mean bound is effectively the full query
range, so it supplies no useful precision guarantee. No arbitrary NLL acceptance
threshold was introduced. The result does not reject higher-order physical
response fields, smaller justified domains, or a centroid trajectory coupled
to a richer residual representation. It also does not establish error growth
in an aging cell: these are short stationary representation controls.

The main suite took about2.07CPU seconds with109.9MB peak host RSS, including
plotting and excluding compilation. It is not an estimator-speed benchmark.
There were no battery fits, particles or canonical trajectories.

## What the centroid study establishes

**A moving coordinate center can be exact.** Write theta=m(t)+u and transform
the likelihood, support, prior and transition together. This changes coordinates
without changing evidence. A center chosen from existing estimates is not a new
independent observation. Tracking a smoothed voltage/current centroid would mix
stimulus changes with aging; the useful physical trajectory is more likely a
health-coordinate trajectory than a full SOC/RC-state trajectory.

**An uncertain center needs its correlation with residual shape.** If the
curve coefficients beta are uncertain, theta=b(t)'beta+u has covariance terms
from both beta and u and their cross covariance. In the controlled example,
retaining that relationship gives variance0.014; assuming independence gives
0.05. The example illustrates a mechanism, not measured battery uncertainty.
If the center is merely a deterministic chart, the residual distribution already
carries total uncertainty and must not have a second center variance removed.

**Finite-basis sufficient statistics can work exactly under explicit premises.**
[centroid.py](centroid.py) implements a four-knot natural-cubic basis and the
Gram/linear/residual-energy statistics for unique independent Gaussian scalar
observations. Streaming statistics match batch regression; changing the
coefficient center preserves the complete quadratic. This is a small algebraic
control, not a noise model for correlated rolling posterior outputs. The raw
moment implementation also carries no lifetime cancellation guarantee; stable
square-root storage remains the preferred implementation direction.

**Four knots alone cannot certify curve accuracy.** Two constructed paths
`1+0.3*t` and `1+0.3*t+0.01*sin(6*pi*t)` share the same four values at
0,1/3,2/3,1. Both are smooth, monotone and within a30% range. Their identical
four-knot natural cubic misses the second path by up to1% of the initial
reference value between knots. These are mathematical curves, not plant truth
used to center an estimator. A known curvature bound gives the elementary
piecewise-linear bound M*h²/8; a cubic-spline bound needs its own premises.

**Early data do not identify the whole future curve.** On the first interval,
a natural cubic has only constant, linear and cubic terms. The four knot values
therefore contain an unobserved direction. The targeted
[causal control](causal001/result.json) observes only times0–0.25 and confirms
that this direction changes future predictions while retaining its prior
variance. There is no future-data lookahead. Updating knot locations or time
normalization later would require a valid coefficient conversion or a charged
approximation, not silent deletion of older evidence.

## Storage and decision

| Object | Estimated numeric payload |
| --- | ---: |
| Stationary field cell with domains, transport and error ledger | **816 B** |
| Four knot values for each of eight health quantities | **256 B** |
| Four shared knot times | **32 B** |
| Illustrative dense joint Gaussian of32 curve coefficients plus8 residuals, including means/covariances/cross terms and knot times | **6,912 B** |

The cell estimate excludes source/model/noise identifiers, sigma, query output,
workspace, queue and optimizer. Python storage is larger. The6,912B example is
not a selected battery posterior and excludes other fast/nuisance states and
their relationships. Structured uncertainty might be cheaper, but needs a
justified factorization. None of these numbers establishes a complete10KiB fit,
and the existing estimator's allocations must not simply have these added to them.

Retain the user's center-plus-shape direction. The next development should use
an **exactly recenterable square-root representation with a curve remainder and
joint center/residual uncertainty**, attached to a richer physical response
representation. Re-centering an amplitude quadratic is exact; moving the
nonlinear conditioning point of discarded battery history is not. The new
error ledger must remain authoritative when the center changes. Four knots
should be tested against that ledger and causal observability, rather than
selected solely because the trajectory looks smooth.

Commands, using a new main destination:

```sh
MPLCONFIGDIR=/tmp/mumble-envelope-mpl OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.operator_envelope_001.qualify /tmp/mumble-envelope-new
```

The additional causal control was run with
`python3 -B -m experiments.operator_envelope_001.centroid_prefix`; its exclusively
named `causal001` directory is preserved. All previous proof/reference artifacts
remain hash-identical. The production solver and physical aging model are unchanged.
