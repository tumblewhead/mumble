# Stationary residual envelopes and a moving centroid

This step implements the [next gate](../../proofs/partitioned_battery_001/next_gate.json)
as a deliberately simple fixed-point field, and examines the user's proposed
four-knot centroid trajectory. It keeps conditional amplitude structure exact
and makes the price of approximating nonlinear coordinates explicit. No new
aging law, posterior family, or fitted battery center is introduced.

## E1. A field cell with an explicit defect

Fix a nonlinear box D in the original seven eta coordinates and a public
reference eta0 inside it. At every eta in D approximate the conditional
likelihood by the exact amplitude square root constructed at eta0. This is a
zero-order field, not interpolation or a claim that eta is known. A query
outside D is unavailable. Smaller boxes are conditional experiments and do not
discard the posterior outside them. Original prior and supported amplitudes
remain outside this prior-free object.

For an RC mode write the actual voltage v and reference response v0 at the
same amplitudes. If the previous uniform voltage error is d_i, then

    d_i,new <= e_max*d_i + de*(abs(a0_old)*V_enter_max
                                      +abs(f0_old-I)*R_max),

where e=exp(-dt/tau), e_max is its box maximum and
de=max_D abs(e-e0). This follows by subtracting the two recurrences:
e*(v-v0)+(e-e0)*(v0-RI). For w=H*h use the same formula with a_h,b_h,
H_max and B_max=abs(H*h_enter)_max; e_h depends on the active directional
rate and actual throughput. At rest e_h=1 and no hysteresis attenuation is
invented. The bounds start at zero for a common entering amplitude argument.

SOC is evaluated exactly as z=z_enter-charge/Q. Monotonicity of U gives an
OCV-error bound from the box's two extreme supported SOC values. Reject a cell
if its propagated SOC box exits [0,1]; do not clamp it or quietly shrink it.
The joint voltage envelope is

    epsilon_k = epsilon_OCV,k + sum_i d_i,k + d_w,k.

All likelihood cross terms stay in the square root. Adding absolute errors is
a conservative envelope, not an assumption of independent physical partitions.
Actual time and charge/throughput are retained; 35 Hz is not substituted for dt.

## E2. An accumulated norm bound from the retained square root

Retain E2=sum_k(epsilon_k/sigma)^2. For a query alpha, the represented
normalized residual vector has norm r0=||S*[alpha;1]||. Cauchy–Schwarz gives

    abs(L_exact(eta,alpha)-L0(alpha)) <= r0*sqrt(E2)+E2/2.

This requires only E2 and the retained factor, not the raw observations.
For a uniform bound over alpha, bound every row of S*[alpha;1] by interval
evaluation on an amplitude box containing the original wedge |B|<=H; sum the
squared row bounds to get r0_max^2. Using a containing box is conservative.
The measurement normalizer is identical and cancels. This improves the crude
global voltage-range residual bound without dropping any cross term.

These are real-arithmetic bounds under the admitted stationary model.
The implementation uses float64 and reports its arithmetic bound as unresolved.
Finite comparisons allow a separately registered rounding tolerance; passing
them is not a rigorous outward-rounded certificate. With E2=0 the mathematical
representation is exact, while measured floating-point discrepancies can remain.

## E3. Compatible block composition retains spent error

The second block's nonlinear domain must cover the first block's propagated
SOC box at the same Q/rate bounds. Its center must be the transported first
center. Its entering RC amplitude support must cover all possible carried
states, [-0.25,0.25] V under the inherited stationary support. The initial
[-0.08,0.08] V bound must not be reused at a later boundary.

Let d_A contain three RC and one H*h exit errors. For B retain four weights
W_B,j=sum_k a_max,j(k)^2/sigma^2, where a_max is the slowest permitted free
attenuation from the start of B. Minkowski's inequality gives

    sqrt(E2_B_with_carry) <= sqrt(E2_B) + sum_j d_A,j*sqrt(W_B,j)
    E2_AB <= E2_A + (sqrt(E2_B)+sum_j d_A,j*sqrt(W_B,j))^2
    d_AB,j <= a_max,B,j(end)*d_A,j + d_B,j.

The likelihood factors compose using the exact reference amplitude map.
W_AB,j=W_A,j+a_max,A,j(end)^2*W_B,j. No spent error disappears at retirement.
The envelope can grow differently for different legal merge trees; it remains
an upper bound, not an associative exact uncertainty statistic. Empty identities
must contribute no new factor or defect. A known block incoming-error estimate
could be tighter, but is not assumed. QR state storage remains bounded while
these scalar bounds can grow without limit.

## C1. Separate a center from shape by translation, preserving their relationship

For a deterministic chosen chart center m(t), theta=m(t)+u is an exact
unit-Jacobian coordinate change. Transform the likelihood, support, initial
prior and transition together:

    L_u(y|u)=L_theta(y|u+m(t))
    K_u(u_next|u)=K_theta(u_next+m(t_next)|u+m(t)).

Nothing is forgotten, and choosing or moving m adds no evidence. A center
selected from already-seen data can be a chart choice; the statistical target
must still be the same data-conditioned distribution. It cannot be counted
again as an independent observation or prior.

If the physical center itself is uncertain, m(t)=b(t)'beta, retain the joint
distribution of beta and u. In scalar form,

    Var(theta)=b' Cov(beta) b + Var(u) + 2*b' Cov(beta,u).

The vector version has both transpose cross terms. Keeping only the centroid
curve and an independent residual covariance generally changes uncertainty.
Conversely, if m is only a deterministic chart, residual uncertainty already
represents total uncertainty; do not subtract a second estimated-center variance.

The relevant centroid must be defined: a posterior mean under a declared prior
and measure, a likelihood optimum, and an average of observations are different
objects. Voltage/current sample centroids move with load and SOC. A rolling
estimate can move because excitation improves, old bias is corrected or the
model is wrong. Its trajectory is not automatically physical aging. A full
SOC/RC-state centroid also follows fast cycles; a small long-term spline is
more plausible for health quantities, with these distinctions preserved.

## C2. A sufficient-statistic example where center and shape can be separated

For unique scalar observations y_k=b(t_k)'beta+epsilon_k with known independent
Gaussian noise, a fixed four-knot spline basis gives exact sufficient sums

    A=sum w_k*b_k*b_k'; h=sum w_k*b_k*y_k; c=sum w_k*y_k^2.

Then NLL=(beta'A beta-2h'beta+c)/2 plus known noise constants. For a new center
beta=beta0+d, exact recharting gives A unchanged, h_new=h-A beta0 and
c_new=c-2h'beta0+beta0'A beta0. It keeps residual energy, normalization and
cross terms. Constant representation size follows from the specified finite
linear basis, not from a generally smooth-looking history.

These sums are not a numerical recommendation near cancellation; the battery
prototype keeps a square root. For independent equal-noise vector observations,
the analogous matrix statistics can share the basis Gram matrix. The actual
battery and overlapping rolling posterior outputs do not meet those independent
observation assumptions automatically. Correlated data need their joint noise
model or prior-free disjoint operators, not just a count and a centroid.

## C3. Four knots are a hypothesis requiring a remainder bound

The control uses four fixed knot times 0,1/3,2/3,1 and a natural cubic spline
(three cubic pieces, with zero endpoint second derivatives). A piecewise-linear
interpolant through the same knots supplies a separate elementary bound:
if |m''|<=M, interpolation error on width h is at most M*h^2/8. To see this,
the interpolation remainder is m''(xi)*(t-a)*(t-b)/2, whose magnitude is
bounded by M*h^2/8. This bound belongs to the linear interpolant; it is not
silently transferred to the natural cubic spline.

Consider two dimensionless health paths:

    m1(t)=1+0.3*t
    m2(t)=1+0.3*t+0.01*sin(6*pi*t),  0<=t<=1.

They agree at all four knots. Both are smooth, strictly increasing
(m2'>=0.3-0.06*pi>0) and stay between1 and1.3. Their four-knot natural cubic
and linear interpolants are identical straight lines, yet their true curves
differ by up to0.01 between knots. These are mathematical counterexamples,
not cell truths used to center or fit an estimator. The proposed range and
even monotonicity therefore do not certify spline accuracy. Derivative bounds,
change-point assumptions or a retained residual envelope are additional premises.

Four knots do not necessarily mean four free parameters overall: eight health
quantities require32 values plus shared knot locations. Calendar age, throughput
and temperature may not reduce to one time coordinate. Future knots cannot
be estimated from future observations in an online system. Changing knots or
the time normalization changes old basis rows; an exact coefficient conversion
or charged approximation is needed before discarded observations can stay gone.

## Storage and interpretation

The stationary cell retains a packed factor55, center7, domain endpoints14,
transport8, charge/extrema/time4, directional throughput2, outgoing errors4,
attenuation weights4, and E2 one double:99 doubles=792 B. A uint64 count,
first index and entering-amplitude limit add24 B, for **816 B** before source/
model/noise identifiers, sigma, query results, scratch, queues and optimizer.
Dense Python arrays and object overhead are larger. This is a conditional
box cell, not a complete current-boundary posterior.

For eight health quantities a deterministic four-knot curve costs256 B plus
32 B knot times. A fully joint Gaussian example with32 uncertain coefficients
and eight residual coordinates costs6912 B:256 coefficient means,4224 packed
coefficient covariance,64 residual means,288 residual covariance,2048 cross
covariance and32 knot times. This is an illustrative dense layout, not a selected
battery posterior or an allocation to add to the existing estimator. Separability
or fewer health directions can reduce storage only under justified structure.

The centroid proposal is therefore retained as a promising **coordinate and
model decomposition**. Whether it provides compression depends on a small,
adequate trajectory family, causal coefficient updates, uncertainty coupling
and a residual bound. A smooth-looking centroid alone does not establish any
of those conditions.
