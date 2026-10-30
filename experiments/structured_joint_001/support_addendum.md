# Additional joint-support and repeated-normalization controls

The main attempt's 150 checks and source snapshot remain unchanged. A separate
[support attempt](support001/result.json) adds24 checks. These are mathematical
counterexamples, not a calibrated battery-aging model or an additional battery
simulation. Both increasing and decreasing scalar support are covered.

For standard bivariate Gaussian coordinates with correlation rho,

    Pr(X>=0,Y>=0) = 1/4 + asin(rho)/(2*pi).

At rho=0.8 the joint mass is about0.397584, compared with0.25 if their two marginal
probabilities are multiplied. At rho=-0.8 it is about0.102416. Independent
conditional numerical integration verifies these values. Thus even a
coordinatewise monotone constraint needs joint uncertainty when integrating
correlated variables. A joint quadratic core followed by independent scalar
support corrections does not generally preserve the posterior.

For a simple normalized monotone kernel on the unit interval,

    a0 ~ Uniform[0,1),
    K(a_next|a) = 1{a<=a_next<=1}/(1-a),

the n-step density is

    p_n(a) = [-log(1-a)]^n/n!, 0<=a<1.

This follows by induction: integrating p_(n-1)(x)/(1-x) from0 to a raises the
log power and divides by n. Its integral is1 by the change of variable
z=-log(1-a), giving a Gamma integral. Independent quadrature checks n=1,2,4.
The endpoint a=1 can separately be assigned an absorbing point mass; it has
probability zero under these finite-step continuous fixtures.

Omitting the transition normalizer produces the first-step unnormalized
density a. Globally normalizing that answer yields2a, which still differs from
-log(1-a). Resetting the carried shape to a uniform prior at every boundary
also gives the wrong later distribution. This counterexample has a compact
exact log-power representation; it is **not** evidence that every constrained
message must grow without bound. It demonstrates which factor must survive
composition before any proposed compact family can be qualified.

There is a direct error consequence for the scalar Gaussian monotone example
in the main derivation. If D(s)=[0,s] and the conditional density is continuous
and strictly positive at x=s=0, then

    M(s)=f(0|0)*s+o(s),
    log(f_unbounded_marginal/f_constrained_marginal)=-log M(s).

Consequently the missing log-mass error diverges like -log s as s approaches
zero from above. Its strong log-density oscillation is unbounded on that open
domain, even though each point s>0 has a finite value and the normalized
posterior can be well behaved. This is an analytic omitted-support error,
not roundoff or evidence that actual battery error diverges with age.

The existing lifetime defect recurrence can only be used after a local defect
has been bounded in the chosen metric. It cannot turn this omitted term into a
uniform finite NLL budget. Preserve the mass, prove a legitimate narrower
domain, or derive an appropriate integrated/query error bound. Do not introduce
an arbitrary boundary cutoff or numerical epsilon and call it physical support.
