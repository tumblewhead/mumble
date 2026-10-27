# Autonomous anchor refinement: finite host design

## Question and finish line

The preceding retained-likelihood replacement probe supplied its useful anchor
from an already completed historical fit. This experiment asks whether a bounded
refinement can obtain anchors from the fixed public entering mean and its own
accepted results. The [contract](../../plans/autonomous_anchor_refinement_001.json)
freezes one invocation on the same 252,000-observation prefix, at most 16 proposal
rounds and 33 full model passes, including the initial point and rejected trials.

The finish line is a preserved finite sequence of feasible anchors with audited
objective decreases, or an explicit unresolved stop. It is not a global optimum,
posterior calibration or streaming firmware qualification. This is an iterative
retained-history nonlinear refinement driver; only its inner proposal problems
avoid reading the observation history.

## The target remains the same

Let `x` be the original sixteen-dimensional entering-state chart, including
`logQ`, initial SOC, the RC parameters and states, and the hysteresis parameters
and state. Every model pass starts at the candidate's entering state and traverses
the original ordered current, interval and voltage records. The objective is

\[
F(x)=L(x)+p(x),\qquad
L(x)=\frac12\sum_i\left(\frac{\widehat V_i(x)-V_i}{0.001}\right)^2,
\]

where `p` is the negative log density of the same public two-Gaussian kernel
mixture. The mixture is conditioned as a whole on the unchanged physical support.
The density base measure is Lebesgue measure in this entering chart. Its common
support normalizer cancels from cost differences; no evidence probability or
posterior mass is inferred without it. The existing
[prior and support code](../retained_likelihood_replacement_001/replacement_math.py)
and [C evaluator](../retained_likelihood_replacement_001/stream_evaluator.c)
remain unchanged.

Initialization is exactly the public unsplit mean. No historical fit, recursive
posterior, previously fitted anchor or truth record is an inference input. An
infeasible public mean stops the experiment instead of triggering another seed.

## A derived metric for the proposal

For common component covariance `P`, component responsibilities `r0,r1`, and
\(v=P^{-1}(\mu_1-\mu_0)\), the exact mixture penalty satisfies

\[
\nabla^2p(x)=P^{-1}-r_0(x)r_1(x)vv^T\preceq P^{-1}.
\]

Therefore the quadratic prior remainder obeys

\[
p(a+d)\le p(a)+\nabla p(a)^Td+\tfrac12d^TP^{-1}d.
\]

At the currently accepted anchor `a`, form the full joint gradient and metric

\[
g=\nabla L(a)+\nabla p(a),\qquad B=G(a)+P^{-1},
\]

where `G` is the complete likelihood Gauss–Newton Gram. All off-diagonal
likelihood terms remain. The prior bound does not make the nonlinear likelihood
quadratic a global upper bound; that is why every trial receives a nonlinear
audit. `B` is an optimization metric, not a replacement prior or posterior
precision matrix. The accepted objective always uses the exact mixture penalty.

The proposal minimizes

\[
m(d)=g^Td+\tfrac12d^TBd
\]

over the original support and the step box
\(\lVert D^{-1}d\rVert_\infty\le1\), with
\(D=\operatorname{diag}(\text{PUBLIC\_SD})\). Numerical optimization uses
`x=a+D*u`, starting at `u=0`; this does not redefine the density measure. Scaling
uses the fixed formula \(\sqrt{\max(1,\lVert DBD\rVert_\infty)}\).
The actual scaled matrix must pass an unmodified Cholesky check. Failure stops
the run; there is no eigenvalue repair.

The feasible set is convex. If \(q=\log Q\), its two SOC conditions are

\[
z_0\ge C_{\max}e^{-q},\qquad
z_0\le1+C_{\min}e^{-q},\quad C_{\min}\le0\le C_{\max}.
\]

The first is the epigraph of a convex function; the second is the hypograph of
a concave function. Intersecting them with the entering and step boxes preserves
convexity. A true minimizer of this convex quadratic problem satisfies
\(g^Td\le-d^TBd\), so a nonzero step descends. The numerical implementation
does not assume that its finite inner solve reaches that minimizer: it checks
feasibility, negative directional derivative and positive model decrease
independently. An unresolved inner solve can supply a valid descent direction.
It cannot establish nonlinear stationarity.

The inner solver is the pinned SciPy `trust-constr` implementation with analytic
derivatives, a 100-iteration cap and 256 combined objective/gradient evaluations,
including final verification. Its convergence and multiplier semantics follow
the [SciPy 1.17 documentation](https://docs.scipy.org/doc/scipy-1.17.0/reference/optimize.minimize-trustconstr.html).
The frozen numerical policy records all tolerances and emitted warnings.

## Audited finite backtracking

Trials use the fixed fractions
`1, 1/2, 1/4, 1/8, 1/16, 1/32, 1/64, 1/128` along the feasible chord. At full
step the exact returned vector is used, avoiding a rounded reconstruction of
`a+(b-a)`. Partial steps use the declared expression `a+alpha*(b-a)`. Although
the real-arithmetic chord is feasible, each represented point is checked again
against raw support slacks before a model call. Negative slack is not clipped
or excused by an arithmetic tolerance.

Let `s=-g.dot(d)` and let `A_dot` bound the declared computed directional
product/sum arithmetic. Acceptance requires a resolved true computed cost
decrease and the conservative sufficient-decrease comparison

\[
\Delta F-A_{\rm cost}
>\tfrac14\alpha(s+A_{\rm dot})+A_{\rm combine}.
\]

`A_cost` reuses the previous summand-accumulation and four-term combination
account for the nonlinear likelihood and fixed prior costs. Source code freezes
the directional, quadratic-model and final-combination operation counts and
absolute-product scales. These are computed-arithmetic resolution accounts, not
certificates for the complete floating-point model, derivatives or `libm`.

The quarter-slope rule, one-public-SD step box, binary fractions and work limits
are declared optimizer choices. Their purpose is to control extrapolation and
require productive steps. They do not define observation noise, physical
accuracy or interval width, and they are not adjusted after seeing the run.
Smoothness and a descent direction motivate backtracking; the finite schedule
does not guarantee that an acceptable fraction will be reached before its cap.

## Reuse and evidence ownership

Every C audit already supplies the candidate's likelihood cost, gradient, full
Gram, endpoint state and derivative map. On acceptance those outputs become the
next anchor block directly. No second pass evaluates the accepted point merely
to begin the next round. Its exact prior evaluation is cached as well.

One immutable prior and one active likelihood block own source observations
`[0,252000)`. Acceptance changes the representation generation, point and block
together, while leaving the source cursor unchanged. Rejected trials are
diagnostic records, not additional observations or factors. A posterior derived
from this prefix is never multiplied into its replayed evidence.

## Bounded work and explicit stops

The global caps are 16 proposals, 33 model passes, 8,316,000 model steps,
60 CPU seconds, 90 active process wall seconds, 128 MiB process peak RSS, and
8 MiB of closed runtime output. Global caps take precedence over the per-round
trial schedule. Each call is reserved and fsynced before launch; incomplete
activity remains unknown with a conservative upper bound rather than being
reported as zero. Captures retain their original filenames throughout closure.

A normal work-cap stop, no admissible direction, or no accepted fraction is a
completed finite unresolved outcome. Input, numerical or resource failure is a
failed attempt. Neither outcome starts a retry, alternate seed or extended
campaign. Outer whole-process accounting includes waited children, and a failed
outer closure vetoes successful reporting.

Only after valid closure may reporting open the pinned preceding summary for
its feasible reference and already verified endpoint truth record. No new raw
truth file, model, optimizer or prior evaluation is needed for that report.
The reference is not a global optimum and is never an inference target.

The evaluator still has a 10,680-byte fixed workspace and needs 8,064,000 bytes
of external prefix data. Its 11,072-byte compiler-reported main frame contains
the workspace. These quantities remain distinct from host solver RSS and a
complete Cortex-M23 allocation. This experiment changes no production estimator
or uncertainty interval provider.
