# SOC and capacity uncertainty: supported-correction decision

## Decision

The single-h-bound correction is a useful exact reference, but **it is not a
general repair for the narrow SOC and capacity intervals**. Retain its
distribution and evidence identities as requirements for a future estimator.
Do not install it as a drop-in modification to the present learner.

The user's objective remains useful, defensible SOC/capacity uncertainty. The
[one-prefix historical-likelihood control](../historical_likelihood_control_001/REPORT.md)
has now completed its three declared fits at 7,200 seconds, before the earlier
weight switch and later h-bound witness. It reevaluates the archived nonlinear
evidence and supplies a concrete target-discrepancy witness. Better points or
different local widths do not by themselves establish coverage.

This report is accompanied by the [frozen reference contract](../../plans/support_consistent_conditional_001.json),
[mathematical specification](mathematics.json), executable reference and
independent review. The [executed reference](attempt001/result.json) passed all **79 checks** in one invocation. The largest raw reconstruction discrepancy was **6.22e-14**. Six independent scalar-oracle evaluations used 24 quadrature integrals; no battery model or learner ran. The [whole-process receipt](attempt001/process_receipt.json) records 1.834 seconds and 87,691,264 bytes peak RSS. See the [compact summary](summary.json).

## What the previous probe established

The previous [three-checkpoint probe](../conditional_belief_adequacy_001/REPORT.md)
found a saved h mean of exactly 1 with positive variance. Such a pair cannot be
the moments of a distribution confined to[-1,1]. It occurred in an already
downweighted alternative after the component switch. It does not establish
the cause of the broader SOC/Q failures.

Its 100 microvolt reporting scale is not an acceptance criterion here. The
1 millivolt observation-noise SD matches the synthetic source's declared noise
law. It is an inference parameter, not a residual rejection threshold.

## A coherent supported conditional law

Let x contain the 16 chart coordinates, with q=log(Q_Ah), z=SOC and h the
hysteresis state. For the single-bound reference, define

\[
 p_C(x)=\frac{\mathbf1_C(x)\,\mathcal N(x;m,K)}{Z(m,K)},
 \qquad C=\{-1\le h\le1\}.
\]

The stored m,K are **Gaussian kernel parameters**. They are not the physical
mean and covariance of p_C. The kernel center can lie outside C while the
normalized physical distribution remains entirely within C. The other 15
coordinates are not physically bounded by this single-bound reference.

For an affine voltage likelihood y=c+J^T x+epsilon with variance R, define

\[
 S=R+J^TKJ,\quad r=y-c-J^Tm,
 \quad m_G=m+KJr/S,\quad K_G=K-(KJ)(KJ)^T/S.
\]

Multiplying the Gaussian kernel by the likelihood gives another Gaussian
kernel. Integrating over the already-owned support gives the predictive
evidence

\[
 p(y\mid C)=\mathcal N(y;c+J^Tm,S)\frac{Z(m_G,K_G)}{Z(m,K)}.
\]

The prior normalizer in the denominator is necessary. The normalizer ratios
telescope over successive distinct observations; the source/sample ledger
must still prevent duplicate observations. A constant likelihood leaves the
normalized law unchanged. Missing voltage contributes an evidence factor 1.

This follows directly from the Gaussian-product identity. The standard
definition and moment calculation for truncated Gaussian distributions are
also documented by [Manjunath and Wilhelm](https://doi.org/10.35566/jbds/v1n1/p2).
The equations and implementation obligations here are derived for the stated
single-coordinate reference; the literature citation does not supply a
full-model coverage claim.

### Joint physical moments

Let s²=K_G,hh, alpha=(a-m_G,h)/s, beta=(b-m_G,h)/s and
Z=Phi(beta)-Phi(alpha). The scalar supported moments are

\[
 m_T=m_{G,h}+s\frac{\phi(\alpha)-\phi(\beta)}Z,
\]

\[
 v_T=s^2\left[1+\frac{\alpha\phi(\alpha)-\beta\phi(\beta)}Z
 -\left(\frac{\phi(\alpha)-\phi(\beta)}Z\right)^2\right].
\]

For d=K_G[:,h]/K_G,hh, the complete joint moments are

\[
 M=m_G+d(m_T-m_{G,h}),\qquad
 V=K_G+dd^T(v_T-K_{G,hh}).
\]

This changes correlated SOC, logQ and nuisance coordinates together. Changing
h alone or zeroing its factor row would define a different operation. A PSD
matrix with zero h variance must have a zero h cross row. The deterministic
inside-support case is valid; a deterministic outside-support case has zero
support mass and must fail explicitly.

### Why this cannot repair arbitrary target overconfidence

For an interval-truncated normal, v_T<=K_G,hh. Thus V<=K_G in PSD order. If
K_G[z,h]=K_G[q,h]=0, the entire z,q marginal is unchanged by support
conditioning. An already biased, narrow target marginal can therefore survive
this correction intact. With correlation, the support operation reduces
chart covariance relative to that same Gaussian kernel.

This comparison is **not** a claim that an exact supported posterior's variance
must decrease relative to its previous supported prior. Evidence can move mass
away from a boundary and increase physical variance even while the Gaussian
kernel covariance decreases. A fixed scalar qualification checks that case.

### Why moment repair cannot be repeated as fresh conditioning

An already-supported half-normal has mean sqrt(2/pi) and variance 1-2/pi.
Replacing it with an unrestricted Gaussian with those moments and truncating
again shifts the mean and contracts variance without new information. The
operation has changed the law by projecting and conditioning again.

Carry the kernel/support semantics, or define and assess an explicit
approximation. Do not silently use physical moments as fresh Gaussian kernel
parameters. The archived impossible physical moment pair has no exact
supported-distribution inverse; reinterpreting it as a kernel is not an exact
warm migration.

## A stronger obstruction: two moments do not determine the next posterior

Consider two laws on[-1,1]. A places probability 1/2 at each of
X=+/-1/sqrt(2). B places probability 1/2 at 0 and1/4 at each of +/-1. Both
have mean 0 and variance 1/2. Under y=X+epsilon with y=0 and Gaussian SD sigma,
A retains posterior variance 1/2. B has posterior variance

\[
 \frac{r}{1+r},\qquad r=\exp[-1/(2\sigma^2)].
\]

Their evidence and posterior laws differ even though their prior support,
mean and variance agree. No updater receiving only those moments and the
new observation can reproduce both posteriors. This is a sufficiency
counterexample, not an assertion that these discrete laws occurred in the
battery experiment. A specifically declared identifiable probability family
can still be parameterized compactly; its approximation to the historical
posterior is the separate obligation.

## Concrete early nonlinear terms the local approximation can lose

The independent [source audit](../historical_likelihood_control_001/source_audit.json)
identifies two computable examples from public initialization, without using
truth or running the battery learner.

For independent initial H and h with E[h]=0,

\[
 \operatorname{Var}(Hh)=E[H]^2\operatorname{Var}(h)
 +\operatorname{Var}(H)\operatorname{Var}(h).
\]

The first-order observation map retains the first term. The second equals
2.7777778e-4 V² for the public initial moments. This is 277.78 times the
1e-6 V² sensor-noise variance, **not** 277.78 times the total predicted voltage
variance; other uncertain coordinates also contribute. A degree-three axis
quadrature rule can miss this fourth-moment product term as well. Small
late-stage results from that rule do not certify broad-prior adequacy.

For a Gaussian log-capacity q with variance v,

\[
 E[1/Q]=\exp(-E[q]+v/2),
\]

where the point transition uses exp(-E[q]). The public split's v gives a
ratio 1.02219003. This is an omitted moment under the declared Gaussian chart
law, not an assertion of a 2.219% SOC or capacity error in the actual stream.

A further semantic distinction concerns the innovation-dependent selected
gain. In an affine Gaussian reference let g=PJ/sqrt(S), t the selected
normalized gain and a=r/sqrt(S). The exact posterior covariance is
P_G=P-gg^T. About the selected mean m+t*a, conditional mean-square error is

\[
 P_G+(g-t)(g-t)^Ta^2.
\]

The stored Joseph matrix is P_G+(g-t)(g-t)^T. The latter is a fixed-gain
unconditional error identity, not generally the conditional posterior
covariance or conditional error about a data-dependent bounded estimate.
This is a semantic limitation of the assumed covariance. It does not justify
an innovation-based inflation patch or prove the historical bias mechanism.

## What a reported interval would mean

The supported z or q marginal is generally not Gaussian. A nominal posterior
interval must use its marginal quantiles. Capacity quantiles are the
exponentials of log-capacity quantiles. exp(E[q]) and E[Q] are different point
summaries. Under this single-h-bound family,

\[
 E[Q^k]=\exp(km_q+k^2K_{qq}/2)
 \frac{Z(m_h+kK_{hq},K_{hh})}{Z(m_h,K_{hh})}.
\]

Even exact quantiles of this reference law establish probability content
under that law only. They do not establish repeated-sampling SOC/Q coverage
for the nonlinear historical estimator. Neither a width increase nor an
all-unresolved reporting policy counts as a successful repair.

## Prediction, complete support and resources

The actual transition depends nonlinearly on Q, tau and gamma, and voltage
contains nonlinear OCV and Hh. The reference family is not closed under these
operations. Even an affine map must transport the support: replacing a
transported narrow h interval with[-1,1] changes the law. A full correlated
physical box needs its joint normalizer; marginal normalizers cannot simply
be multiplied.

The existing owned objects use 7,152 bytes. The proposed complete subsystem
allocation is 10,032 bytes, including unmeasured stack/runtime reserves,
against a 10,240-byte planning ceiling. One 16D binary64 mean plus packed factor
uses 1,216 bytes. Naively retaining both kernel and physical moment objects for
two components in live and staged banks adds 4,864 bytes, reaching 14,896 bytes.
Even one extra derived moment object adds 1,216 bytes, exceeding the 208-byte
planning headroom. Storage reuse would need explicit lifetimes, factor
algorithms, query/prediction work and checkpoint semantics. No such target
implementation is claimed here.

An affine scalar-observation kernel update and single-bound joint moment
projection use O(16²) arithmetic plus scalar normal probabilities. That count
does not cover full-box integration, nonlinear pushforward, tail algorithms,
factor maintenance or marginal quantile queries. The source/compiler/memory
and timing qualifications of a full Cortex-M23 implementation remain open.

## Verification and next action

The frozen reference has three families: interior affine, an outward
correlated h update, and zero-information preservation. Additional declared
branches check singular support, evidence composition, covariance growth,
moment insufficiency and public-start nonlinear moments. Independent scalar
integration supplies the moment/evidence comparison. Numerical reconstruction
tolerances qualify arithmetic only; there is no voltage-materiality gate.

The separately frozen historical-likelihood control has completed one free
fit and two target-constrained fits on the same archived prefix. It uses no
recursive posterior penalty and no truth in inference. The free result is
Q=64.703737 mAh and current SOC=51.602859 percent. Fixing the saved recursive
Q or SOC increases the best found negative log likelihood by 26,254.615 and
17,453.912 respectively; the nuisance quantities are reoptimized in each case.
The [control report](../historical_likelihood_control_001/REPORT.md) records
local precision, post-inference scoring and the selected evidence-retention
work. Its bounded likelihood objective differs from the online prior, and
local optimum costs cannot establish global exclusion or calibrated coverage.

A future compressed representation needs an explicit approximation account.
The [likelihood-fidelity requirement](likelihood_fidelity_requirement.json)
relates a global bound on parameter-dependent log-likelihood error to exact
posterior tail-probability bounds under a common prior and target map. It is
an acceptance principle, not an implemented certificate or an obstacle to
building a finite retained-evidence prototype. No voltage cutoff or arbitrary
uncertainty multiplier is introduced.
