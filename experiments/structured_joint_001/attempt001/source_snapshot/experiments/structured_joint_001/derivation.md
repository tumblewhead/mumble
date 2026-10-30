# Joint storage: physical separation, chronological elimination and support mass

This is a derivation and finite algebra qualification, not a battery aging run.
It follows the user's monotone reference-condition aging and separate T(t)/g(T)
direction. Earlier results are preserved. The original rolling estimator is
unchanged. The complete 10 KiB subsystem and ten-year error bound remain open.

## 1. What transfers from SpanishCastleMagic

The reviewed NAIA branch is pinned to
`9cb846ef5e9838100f9c7d5156bb2fb01b90d957`. Paths, hashes and excerpts of the
source/evidence boundary are recorded in [sources.json](sources.json); the
retrieved source files are retained under `sources/naia/`. No remote source was
imported, built, run, rescored or modified. This is a source and saved-summary
review, not an independent reproduction of its trajectory results.

The linked tail-correction OWNER_RUN is a candidate execution plan. Its README
explicitly says the correction has not been tested/executed during preparation.
It preserves an earlier failed matrix. Consequently it supplies neither a
successful corrected experiment nor a joint posterior qualification.

Its frozen V3 dependency is nevertheless directly relevant. `joint_rows.py`
uses twelve common coordinates in each of eight nonlinear candidates:

    [A0, K0, p01, p02, p03, R0ref, R1ref, R2ref, R3ref, Href, eta0, 1/Q].

Here A0/K0 are OCV/thermal aggregates, p0 are entering polarization states,
and eta0=Href*h0. A retained voltage row relates these coordinates together.
The original h0 support also imposes a wedge between eta0 and Href. Its retained
individual-row, initial-rest-pair and thermal-anchor budgets are 128,128,64.
Rows have fixed normals; interval residual bounds tighten their right sides.
Unsupported additional history is relaxed explicitly. These are necessary
relations in an outer feasible set, not a normalized posterior density and not
an exact finite sufficient history for the nonlinear plant.

`certified_lp.py` separates a numerical optimizer's proposal from verification.
For A*x<=b and x in a box X, any lambda>=0 gives

    c*x <= lambda^T*b + support_X(c - A^T*lambda).

It checks this statement using exact rationals for the represented binary64
inputs. It does not certify the physical construction of every input row.
Optimizer failure is not physical exclusion. We retain this separation between
numerical proposal, mathematical certificate and physical premise.

The capacity protocol requires a known synthetic witness to satisfy all twelve
coordinates, z0 and authoritative constraints in **one common candidate**.
Marginal containment cannot substitute for that check. This is an evaluation
use of synthetic truth, not an estimator input or a proof of all-history
nonlinear compatibility. The saved A informative arm reports 40,950 updates
(1,170 simulated seconds), Q support 48–84 mAh to 50.0572–71.2327 mAh:
41.1792% width reduction, PASS under its frozen arm gates. The original matrix
remains FAIL: A zero-current stopped at update27,148 with one p2 numerical-point
miss in a subnormal tail; B arms were not reached. The correction proposes
whole analytic tail enclosure containment, with overlap inconclusive. It has no
completed correction result at the reviewed revision. The saved summaries do
not establish probability coverage, aging performance, or M23 resources.

Transfer to mumble: retain common-variable dependence and coherent support;
separate inference from diagnostics; treat unsolved numerical checks as
unresolved. Do not copy interval narrowing as Gaussian information. A rest
pair derived from already retained observations is not new independent noise.
Intersection with a redundant necessary constraint can be harmless for a set;
multiplying its likelihood again generally double-counts observations.

## 2. Physical partitions are not probabilistic independence

At fixed nonlinear eta, the existing exact conditional voltage model is

    mu = OCV(z) - I*R0 - sum_i(f_i*R_i + a_i*v0_i) - b_h*H - a_h*B,
    B = H*h0.

The nine amplitude coordinates share each scalar voltage residual. Its Hessian
contribution is x*x^T/sigma^2, so one excited row with all nonzero columns
couples all nine. Splitting physical response formulas remains useful for
specialized basis/remainder calculations; it does not justify separate
amplitude likelihoods. The 128-record control uses the existing conditional
model and demonstrates a fully populated amplitude Gram matrix.

Likewise, in a local linear surrogate for eight health quantities, with four
age, three anchored thermal and one residual coefficient per quantity, a
generic voltage row depends on all 64 coordinates. Sparse physical equations
do not guarantee a sparse reduced history factor. This example is a storage
comparison, not a claim that the nonlinear battery is linear in these controls.

**Lemma 1 — elimination fill.** Eliminating x from a quadratic whose neighbors
are s induces the Schur term `-H_sx H_xx^-1 H_xs`. Every pair of those neighbors
can couple. Unless a structural zero or exact cancellation is proved, keep the
new edges. Temporal locality, not independent physical families, is the useful
source of sparsity. The graph controls test both induced edges and fixed-size
separators over successively longer chains.

## 3. Square-root partition preserves the full joint object

For already owned whitened residual rows, including each required prior factor
once if doing posterior elimination, perform QR in order [x,s,1]:

    R = [ U  V  d ]
        [ 0  S    ],

where U is k-by-k and S is the augmented root over [s,1]. Then

    f(x,s) = exp(-c - ||U*x+V*s+d||^2/2 - ||S*[s;1]||^2/2).

**Lemma 2 — unrestricted Gaussian elimination.** If U is nonsingular and the
retired support is all R^k,

    integral f(x,s) dx
      = exp(-c-||S*[s;1]||^2/2) * (2*pi)^(k/2)/abs(det U).

The conditional mean is `-U^-1(V*s+d)` and covariance `U^-1 U^-T`.
For a proper Gaussian retained marginal with covariance C_s, define
`K=-U^-1 V`. Then

    Cov(x,s)=K*C_s; Cov(x)=U^-1 U^-T + K*C_s*K^T.

Keeping V is what preserves the trajectory/thermal/residual dependence. The
prototype checks these identities against separately assembled dense normal
equations, not a second call to the same QR implementation. The determinant
must remain when comparing different nonlinear conditioning arguments: even
`exp(-a^2*x^2/2)` has equal zero profile cost for every a but integral
`sqrt(2*pi)/abs(a)`. Profiling and marginalization are different operations.

Rank-deficient retired likelihoods cannot be integrated over all R^k without
a proper prior/support. The prototype rejects them, without invented jitter.
A flat retained direction is allowed and remains unresolved. Numerical rank
diagnostics are not a physical parameter threshold or proof of exact rank.

Partitioning without retirement saves **zero** generic numeric entries:

    k(k+1)/2 + k(p-k) + k + (p-k+1)(p-k+2)/2
      = (p+1)(p+2)/2.

Here the third term retains the conditional residual offset. The p64 augmented
root still costs17,160B in binary64, including cross terms and residual energy.
Eight independent p8 roots would cost2,880B but represent a different target.

## 4. Monotone support contributes a nonquadratic mass

**Lemma 3 — constrained elimination.** If the retired support at retained s is
D(s), the previous integral must be multiplied by

    M(s) = Pr{ X in D(s) | s },
    X ~ N(-U^-1(V*s+d), U^-1 U^-T).

For one retired scalar with bounds l(s),u(s),

    M(s)=Phi((u(s)-m(s))/sd)-Phi((l(s)-m(s))/sd).

The scalar prototype evaluates this term separately; independent Gauss–Legendre
integration checks its result. A monotone example x in [0,s] has nonzero third
finite difference of its log marginal, so it cannot be represented by any one
quadratic. This is not a floating-point discrepancy. Dropping M silently
changes relative probability near aging boundaries and under age/temperature
confounding. Re-centering or center codebooks do not remove it.

The multivariate version is a **joint** Gaussian probability over a polytope.
It is not generally the product of coordinate probabilities. Furthermore,
normalizing a monotone transition kernel introduces its own state-dependent
normalizer Z(x). A model such as

    K(a_next|a) = phi(a_next-a;...) * 1{a_next in ordered support(a)} / Z(a)

requires Z(a) inside the next integral. Lemma3 covers a quadratic times an
indicator; it does not assert closure after arbitrary normalized constrained
transitions or after repeatedly multiplying earlier mass factors. The
prototype rejects multidimensional bounded elimination and numerically
unresolved scalar mass rather than claiming a complete solution.

For support-set inference, eliminating x means existential projection. For
posterior inference, it means integration with the original measure. A box
projection, a feasible optimizer and a marginal likelihood are not substitutes.
The SCM certificate is useful as a separately labeled support diagnostic; it
does not supply the missing probability mass for this model.

## 5. What a chronological separator must contain

**Lemma 4 — conditional separator sufficiency.** Under a declared Markov
transition model, the past can be integrated into one message on the current
boundary state and shared static quantities. By factorization, future factors
depend on past variables only through that separator. Message recursion is
exact at the function level, with source order, state transport, original prior
and normalization preserved. It is not a theorem that the message is Gaussian
or finitely representable. A sum of independent coordinate messages is not the
same message.

For an explicit candidate additive thermal model, a plausible boundary is:

| Quantity | Coordinates | Reason retained |
| --- | ---: | --- |
| Current reference-condition Q,R0,R1:3,C1:3 | 8 | Monotone health state; tau=R*C |
| Anchored reversible thermal coefficients | 24 | Three per health quantity, shared across time |
| SOC,v1:3,h | 5 | Carried physical state, including charge/capacity path dependence |
| H,gamma+,gamma− | 3 | Original unresolved static nuisance parameters |
| Total | **40** | Full joint conditional message |

This count assumes H/gamma thermal laws are fixed; uncertain laws add dimensions.
It also assumes a specified health Markov model. A global cubic age curve
depends on all its controls and cannot be retired merely because time passes.
For local degree-one aging segments, retaining the next endpoint (or a slope)
adds eight coordinates:48. Curve remainders and knot-change rules must still
be supplied; monotonicity alone does not bound them. Four uncertain local
temperature-path controls would add four coordinates (44/52), whereas using a
measured temperature as an exact input conditions away sensor uncertainty.
The four-control count is a local segment assumption, not ten years of T(t).

This separator replaces a fixed whole-history trajectory parameterization;
it is a proposed model change, not a lossless conversion of every arbitrary
64-coefficient posterior. Any prior on eliminated coefficients must be pushed
forward, not discarded. Removing a redundant constant residual/age offset also
requires preserving its induced prior and support; no such reduction is used.

## 6. Storage and algorithm consequences

Packed binary64 augmented factors and12-bit centers give these lower accounting
components. One scratch row is included solely to expose update pressure; no
packed in-place updater or complete firmware allocation is implemented here.

| Candidate | Root | Centers | One row | Partial total |
| --- | ---: | ---: | ---: | ---: |
| 64 full trajectory coordinates |17,160 B|96 B|520 B|17,776 B|
| 40 boundary coordinates |6,888 B|60 B|328 B|7,276 B|
| 44 incl. uncertain T segment |8,280 B|66 B|360 B|8,706 B|
| 48 active age segment |9,800 B|72 B|392 B|10,264 B|
| 52 active age and T segments |11,448 B|78 B|424 B|11,950 B|

The48 case already exceeds10,240B with only one scratch row. The40/44 cases
leave2,964/1,534B for everything else, including nonquadratic support mass,
metadata, physical states not already represented, prior descriptors, error
ledgers, solver stack and other workspace. They are **not complete SRAM fits**.
The toy scalar object uses dense NumPy arrays; these are proposed packed sizes,
not measured firmware memory. A dense rank-one square-root update would cost
O(p^2) arithmetic; eliminating a boundary block costs more. This study measures
finite qualification time, not rolling-estimator throughput or M23 timing.

## 7. Decision and next falsifiable gate

Keep the full joint object. Use physical partitioning for response functions
and temporal elimination for history; do not delete cross terms to meet RAM.
The proposed history message is a joint quadratic core **plus an explicit
support/normalization factor**, with the existing nonlinear and curve remainder
ledgers. This is a representation contract; a bounded-size implementation of
the nonquadratic factor is not yet proved.

Before a full8-health expansion, use a small causal model with two monotone
health coordinates (Q and R0), their reversible thermal dependence, and carried
SOC, preserving joint nuisance uncertainty from the selected reference. Define
a normalized physical aging transition and its time/temperature dependence
before tests. Compare constrained-message retirement against a batch integration
oracle under weak excitation, temperature reversal and correlated aging/thermal
directions. Assess mass normalization, SOC/Q queries and errors, not only NLL or
one coherent witness. Measure the size of the retained nonquadratic factor and
its composition defect. If complexity grows or errors cannot be bounded, report
that failure before a longer run or full layout. Do not silently hold nuisance
truth fixed to make the smaller diagnostic pass.

Neither this step nor the SCM review repairs the earlier fixed-center nonlinear
operator field. Aging-rate calibration, the RC state convention when C changes,
coverage, complete runtime memory and ten-year qualification remain separate
obligations. The existing rolling solver remains the practical computation base.
