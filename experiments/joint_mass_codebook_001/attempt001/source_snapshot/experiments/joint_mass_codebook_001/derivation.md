# Quantized joint probability geometry and monotone history

This step implements the proposed small joint history comparator and tests two
meanings of a probability-geometry codebook. It does not yet connect a compressor
to the production rolling solver. All claims below distinguish exact finite
algebra from approximation of a continuous battery posterior.

## 1. A boundary shape is not its probability mass

For a conditional Gaussian retired state X with mean m(s), covariance C(s), and
support D(s), the previous derivation gives the multiplier

    M(s) = Pr{X in D(s) | s}.

Whitening maps the Gaussian to a standard spherical measure and maps D(s) to a
polytope. Facet directions, offsets and their correlations are useful codebook
coordinates. Its Euclidean volume is not generally its Gaussian probability.
The geometry must be described relative to the probability measure.

A two-variable example uses standardized upper thresholds a,b and correlation
rho. These three numbers determine the joint Gaussian mass at **one query**.
Uniform quantization gives three bytes at8bits each, or five packed bytes at
12bits each. This does not encode the functions a(s),b(s),rho(s) over the retained
domain, their prior, or a whole history. Nor does repeated constrained aging
remain in this three-parameter Gaussian family.

At fixed rho, shifting the thresholds changes probability by at most

    (|delta_a|+|delta_b|)/sqrt(2*pi),

because the changed set lies in the union of two strips and each standard
normal marginal density is bounded by1/sqrt(2*pi). For changed correlation,
the probability difference of any fixed set is bounded by Gaussian total
variation, which in turn is at most sqrt(KL/2). For centered unit-variance
Gaussians with correlations rho and rq,

    KL = .5*[2*rq*(rq-rho)/(1-rq^2)
              + log((1-rq^2)/(1-rho^2))].

Combining those bounds gives an absolute mass-error bound for the geometry
codeword. Small absolute error does not ensure small log-mass error near zero.
The implementation uses finite quadrature and ordinary binary64 arithmetic;
these evaluations are not outward-rounded certificates. The [-4,4] threshold
and[-.9,.9] correlation domains are explicit test domains, not battery priors.

## 2. The full probability shape has a natural geometry

Let p_i be **joint** probabilities on a declared finite state grid, including
the quadrature/cell weights if approximating an integral. Define s_i=sqrt(p_i).
Then s is in the positive orthant of the unit sphere. No factorization of
health, temperature, SOC or nuisance coordinates is involved.

For two distributions p,q, their inner product in this geometry is

    A = sum_i sqrt(p_i*q_i),
    H^2 = 1-A = ||sqrt(p)-sqrt(q)||^2/2.

Cauchy–Schwarz applied to
`|p_i-q_i|=|sqrt(p_i)-sqrt(q_i)|*(sqrt(p_i)+sqrt(q_i))` gives

    TV(p,q) <= sqrt(1-A^2)
            = d*sqrt(1-d^2/4),  d=||sqrt(p)-sqrt(q)||.

Any bounded query f therefore satisfies

    |E_p f-E_q f| <= (max f-min f)*TV(p,q).

These are statements about the whole joint distribution. Marginal boxes or
separate coordinate histograms do not preserve this geometry. The simplex also
has boundary faces: zeros encode impossible states and must remain explicit.
On a continuous domain the analogous object is sqrt(density) in L2 relative to
a fixed reference measure. Changing coordinates must transform that measure;
sampled density values without weights are not probability masses.

## 3. An implicit projective amplitude codebook

A first unit-sphere rounding implementation changed again after normalization
and re-encoding, even with no new evidence. Its source and witness are preserved
in `development001`; it is not the qualified implementation.

The repaired code uses relative amplitudes. Set B=2^bits-1, m=max_i sqrt(p_i),
and encode each positive coordinate as

    k_i=max(1,round(B*sqrt(p_i)/m)),

with k_i=0 exactly when p_i=0. Decode q_i=k_i^2/sum_j k_j^2. The largest code is
B. In real arithmetic, decoding followed by re-encoding produces the same
integer vector because all amplitude ratios are preserved. Finite tests check
bitwise idempotence and100 repeated empty re-encodings. This removes a purely
representational drift; it does not eliminate error from genuine future updates.

Let K be the number of positive coordinates and t_i=m*k_i/B. Each amplitude
error is at most m/B, including the nonzero escape code. Thus

    ||s-t|| <= sqrt(K)*m/B,
    ||s-t/||t|||| <= 2*sqrt(K)*m/B,
    TV(p,q) <= min(1,2*sqrt(K*max p)/B).

The local observed angle gives a usually tighter bound. Retaining the smallest
positive code is an explicit quantization operation, not a newly invented
physical probability floor; its distortion is charged. Exact support zeros
remain zeros. No probability is silently pruned. The construction is a uniform
product codebook modulo amplitude scale and has no stored table of all possible
codewords. It costs ceil(N*bits/8) bytes, which still grows with grid dimension.

## 4. A small explicit dictionary comparator

Four joint Gaussian shapes are fitted to moments of two separate, public
training fixtures at declared checkpoints. A uniform shape supplies a fifth
template. Their parameters are frozen and hashed **before** held-out evaluation.
No training observations come from held-out fixtures or from hidden truth.

Each shape retains a full six-coordinate precision matrix. Its probability
values on the active grid are restricted by an exact support bitmap and
normalized. Nearest-template selection uses the spherical/Hellinger distance.
This is a lossy shape approximation, not exact marginalization. A template
with unresolved numerical tails is rejected, without jitter or clipping.

Four six-coordinate Gaussian shapes require4*(6+21)*8=864B of packed numeric
parameters. An index uses1B; the support mask requires ceil(N/8)B. Basis/grid
descriptors and evaluation workspace are additional. The Python implementation
also caches dense arrays for evaluation, which are counted separately. A tiny
index alone is not a memory estimate. Rebuilding the dictionary from deployment
data would add storage, work and an adaptation/error contract; it is not done.

## 5. The small joint aging/thermal comparator

The retained distribution has six coordinates: capacity damage, resistance
damage, current SOC, reversible Q temperature coefficient, reversible R0
temperature coefficient, and a joint nuisance coordinate. The latter indexes
three public combinations of three-RC parameters, H/gamma and entering RC/h
states. All three candidates remain in inference; no nuisance truth is fixed.
This is a deliberately discrete standalone prior, not a replacement of the
original continuous16-coordinate prior or a claim to cover all nuisance values.

Reference Q=0.06Ah and R0=0.1ohm are declared engineering constants. Damage
levels0,.15,.30 give decreasing Q and increasing R0. Three uncertain thermal
slopes per quantity give reference-anchored reversible laws:

    Q(dq,T)=Qref*(1-dq)*(1+gq*(T-25)),
    R0(dr,T)=Rref*(1+dr)*(1+gr*(T-25)).

Both slopes are retained jointly with health, SOC and nuisance state. Temperature
history is measured piecewise linear T(t); parameter dependence g(T) is a
separate uncertain function. Linear functions are the smallest spline family
for this diagnostic. Sensor-temperature uncertainty and age-dependent thermal
laws are not modeled here.

### Normalized monotone boundary kernel

The health transition is a finite pure-birth Markov generator: separate Q-loss,
R-growth and shared Q/R-damage channels have nonnegative rates. All forbidden
backward moves have exactly zero rate. At the declared design-envelope edges,
outgoing moves beyond the grid are absent; the fully damaged corner is
absorbing. These boundary dynamics and rates are engineering model choices,
not validated battery laws. Two supplied rate scales distinguish slow and
accelerated stress controls; the latter tests representation, not realistic
aging over a few minutes.

Exposure is proportional to measured elapsed days and absolute charge
throughput, multiplied by an explicitly positive linear thermal activity law.
The generator exponential is a normalized transition probability, not an
exponential history-forgetting rule. Uniformization expresses it as a Poisson
mixture of stochastic matrices. An analytic geometric bound covers the omitted
Poisson tail; remaining probability is assigned to the identity. Floating
row-sum correction is recorded as numerical bookkeeping and is not a physical
support change. No prior-derived evidence is counted again.

The event comparator first applies this boundary transition, then freezes the
selected health value for that electrical interval. This is an explicit split
event model, not simultaneous continuous-time aging and charge integration.
The aging kernel alone has the semigroup property; the complete split/grid
operator is not asserted to be interval-partition invariant. No calibrated
aging rates or ten-year physical error bound are claimed.

### Carried physical state and likelihood

For held current and linearly varying measured T, the charge decrement uses
the analytic integral of1/Q(T). SOC probability is then deposited on its two
bracketing grid nodes with positive barycentric weights. This preserves its
conditional mean but introduces grid diffusion and changes later nonlinear
voltage likelihoods. It is an explicit numerical approximation to be assessed
separately from codebook distortion. Probability leaving the SOC grid is an
unresolved domain error, not silently clipped or discarded.

Each nuisance candidate transports all three RC states and hysteresis through
the actual current and interval, using the original recurrence. Nominal35Hz
submodel controls compare this response directly with the saved C library.
The larger diagnostic fixtures contain eight held-current events, not a full
35Hz acquisition trace; their event intervals are preserved and not reported
as eight nominal-rate samples. Their deliberately fabricated voltages have no
hidden parameter truth used for centering or correction.

Each voltage likelihood updates the full joint distribution and contributes
its normalizer to the evidence. Old states are integrated out, and the
resulting non-Gaussian shape is retained. The finite-state integral is a sum;
an independent unmerged two-event path sum checks the filter's joint posterior
and evidence. It shares the declared elementary kernels, so this tests
elimination/ownership algebra, not independent physical model calibration.

## 6. Accumulation and qualification limits

For a common stochastic kernel, TV cannot increase. For likelihood0<L<=1 with
exact-reference normalizer Z, the elementary triangle inequality gives

    TV(Bayes_L(p),Bayes_L(q)) <= min(1,2*TV(p,q)/Z).

If encoding the updated approximate distribution contributes local TV eta,
an explicit ledger is

    delta_next <= min(1,(2/Z)*delta_previous+eta).

The study records both this conservative bound and the actual finite-grid TV
against uncompressed inference. A ledger reaching1 is vacuous, not a stability
pass. The exact reference Z is available in the diagnostic; a deployable bound
needs its own computable lower bound. There is no assumed global contraction:
static thermal and nuisance coordinates need not mix under health transport.
An idempotent codebook prevents drift from storage alone but does not prove
approximately indefinite accuracy under successive observations.

Base storage has3*3*17*3*3*3=4,131 joint masses:33,048B as binary64,
4,131B at8bits, or6,197B at12bits. The shape index and mask use518B, plus864B
of dictionary parameters, before descriptors/workspace. These representations
replace this small model's whole probability vector; they are not an additional
factor to add blindly to the prior40-coordinate root estimate. Conversely they
do not encode a40-coordinate continuous posterior. Exact/decoded working
arrays, transition operations and dictionary evaluation in Python exceed10KiB.

SOC-grid refinements17/33/65 report discretization sensitivity independently.
Health, thermal and nuisance discretization remain fixed, so even agreement
under SOC refinement would not certify the continuous posterior. No arbitrary
0.1NLL threshold or selected compression success tolerance is used. All local
and accumulated distortions, query differences, numeric checks and resource
costs are reported. Product accuracy, probability coverage, physical aging and
ten-year usefulness remain later obligations.
