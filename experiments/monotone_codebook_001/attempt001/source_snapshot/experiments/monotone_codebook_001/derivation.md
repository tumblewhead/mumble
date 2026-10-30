# Recenterable square roots, monotone aging and quantized curve codebooks

The user's chosen direction is now monotone **latent reference-condition**
aging: R0 and RC resistances increase or stay fixed; capacity Q and branch
capacitances C_i decrease or stay fixed. Equality is allowed. Temperature is
represented separately, both as measured T(t) and as reversible parameter
dependence g(T). The total observed effective R/Q/C may move either way as
temperature or stimulus changes; the irreversible component obeys the selected
constraint. tau_i=R_i*C_i is not assigned a monotone direction.

This is a model assumption, not a calibrated statement about every fitted
equivalent-circuit parameter. The old two-sided bounded Gaussian health kernel
does not enforce monotonic paths; it remains preserved as historical reference.
A future monotone health transition requires a separately normalized supported
kernel or set-valued law. There is no silent relabeling of that old kernel.

## 1. Exact square-root coordinate translations

Let the prior-free data likelihood be

    L(theta)=||R*[theta-c;1]||^2/2 + ell_noise.

R is upper triangular and includes the residual-energy row. The initial prior
is external and evaluated in the unchanged physical chart. For a new center
c_new, put d=c_new-c. Then

    R_new = R * [[I,d],[0,1]].

Only the final column changes: R_new[:,-1]=R[:,:-1]*d+R[:,-1]. The product
is still upper triangular. Substitution proves the same likelihood, gradient,
cross terms and noise normalization at every theta in real arithmetic. Do not
discard the residual-energy row or translate the physical support/prior as if
the center were a new observation. A center can lie outside supported theta;
it is merely a chart origin, while queries remain subject to physical support.

Appending a new normalized observation row [a,(a*c-y)]/sigma followed by QR
retains the same factor. Adjacent blocks with different centers compose after
translating the second to the first center and QR-stacking. This implementation
is for linear-in-coefficient residuals, with known independent observation
noise; it is not automatic closure of the nonlinear battery likelihood.
The original fixed-eta nine-amplitude battery quadratic is a valid instance.

Existing representation error E2 (squared norm of normalized residual defects)
and source ownership are unchanged by re-centering. Disjoint same-target blocks
add E2; no physical-state elimination is performed by this generic linear
factor. Numerical error remains unresolved in float64, including after repeated
translations. A finite rounding comparison is not a ten-year certificate.

## 2. Two ways to use a quantized center

An implicit codebook maps a coefficient to a shared uniform grid with spacing
Delta=(upper-lower)/(2^b-1), rounding to the nearest index. Its decoded center
is c_q. If R is translated from c to c_q before storage, the factor still
represents the same likelihood: quantization changes the chart, not theta or
the physical curve. Center codes can replace floating center values without
deleting their offset from the factor. The residual factor stays floating point.
This does **not** compress its uncertainty/cross terms or guarantee numerical
precision of the translated last column.

If instead the decoded coefficients replace the physical trajectory or are
reported as a centroid approximation, their error must be bounded. These two
uses must not be confused. Quantizing factor entries, dropping residuals, or
merging different curve supports would be additional approximations.

## 3. Monotonicity-preserving curve families

The first family is a degree-one spline through four sites t0<t1<t2<t3.
Its hat basis is nonnegative and sums to one; ordered values give a monotone
curve. A slope is (c_(i+1)-c_i)/(t_(i+1)-t_i), so the sign follows directly.

The second family is a single cubic Bernstein segment on s in [0,1],

    m(s)=sum_(j=0)^3 C(3,j) s^j (1-s)^(3-j) c_j.

It has four **control coefficients**, not four interpolation knots. The basis
is nonnegative and sums to one. Its derivative is
3*sum_(j=0)^2 B_(j,2)(s)*(c_(j+1)-c_j), so ordered coefficients are sufficient
for monotonicity. This is a useful small curved-family comparator; it does not
assert that all monotone aging paths are cubics. Natural-cubic interpolation
through ordered knot values is not relied on for monotonicity.

The common monotone rounding map preserves coefficient order, possibly merging
small increments into ties. No sorting, isotonic projection or clipping is used
to repair invalid supplied coefficients: invalid order or out-of-grid values
reject. The 0.5–1.5 relative codebook envelope is a design range, not calibrated
battery support. Positive reference quantities and their uncertainty still need
to be defined; the original R support touching zero cannot silently become a
positive ratio baseline.

## 4. Uniform decoded-curve error and temperature composition

For either positive partition-of-unity basis, coefficient error <=Delta/2
implies |m_q(t)-m(t)|<=Delta/2, independent of the number of evaluations.
This bounds quantization of a curve in the chosen family, not its error against
an arbitrary physical aging trajectory. The between-knot/control-point model
remainder is still a separate term; monotonicity supplies no rate/curvature bound.

Use different descriptors and coefficients for age a(t), measured temperature
T(t), and reversible health dependence g(T). Temperature need not be monotone
in time. Define the reversible term by

    g(T)=sum_j [b_j(T)-b_j(T_ref)] theta_j,  T_ref=25 C in the fixture.

It is exactly zero at the reference temperature. Since sum_j(b_j(T)-b_j(T_ref))=0,
one coefficient is redundant; fix theta_3=0 and retain three coordinates. This
removes the constant age/temperature offset ambiguity but not general age-
temperature confounding. If temperature is constant or tightly linked to age,
directions remain unexcited; the factor must preserve their ambiguity.

The anchored thermal function has coefficient-quantization error <=Delta_g,
because the difference of two positive basis vectors has l1 norm <=2.
For polyline g, L_g=max_j |theta_(j+1)-theta_j|/(T_(j+1)-T_j) is a Lipschitz
bound. For the cubic, L_g=3*max_j |theta_(j+1)-theta_j|/(T_max-T_min) is valid.
Thus for the illustrative additive reference-coordinate decomposition
h(t,T)=a(t)+g(T),

    |h_q(t,T_q)-h(t,T)| <= Delta_a/2 + Delta_g + L_g*Delta_T/2.

All evaluations must remain in the same temperature domain. Model/curve
remainders, sensor-temperature uncertainty, hysteresis and age-dependent
temperature response add separate obligations. Additive separability is an
explicit algebraic prototype assumption, not a calibrated battery law. A joint
g(age,T) can be necessary and costs more. Nothing here changes the original
25 C battery model or identifies its temperature dependence from data.

Temperature history can use a low-knot representation on a declared interval;
four knots are not assumed to encode ten years of thermal cycling. Consumed
temperatures must eventually be absorbed into owned history operators with
their error accounted for. Retaining an ever-growing archive of curve segments
would violate the memory goal. Knot changes, shared dictionary changes and
time normalization require versioned conversion or a bounded approximation.

## 5. Monotone support and joint uncertainty

The likelihood remains a quadratic over the full coefficient vector. Monotone
support is an external order cone intersected with declared bounds; after
re-centering, test c+u, not u, against it. Temperature and residual coefficients
remain coupled through off-diagonal factor terms. Neither zeroing them nor
declaring independent thermal/aging estimates preserves the likelihood.

An unbounded Gaussian algebra control can verify factor/covariance invariance,
but it is not the posterior under monotonic constraints. Monotone constrained
marginalization and its normalization remain open. No posterior is appended as
new evidence. A learned codebook or independent spline fitted to overlapping
rolling estimates would need separate ownership and uncertainty analysis.

## 6. Storage accounting

With four age coefficients per each of eight health quantities, an ordinary
float64 center uses256 B. At12 bits per coefficient it uses48 B. Four coefficients
for a temperature path use6 B; three reversible thermal coefficients per health
quantity use36 B. The **three coefficient sets total90 B** at12 bits versus480 B
as doubles. Knot sites, ranges, basis/version descriptors and uncertainty are
additional. This is an implicit product codebook, so a table of2^12 prototype
values need not be stored. It is not a learned vector codebook.

A scalar demonstration with4 age +3 thermal +1 residual coefficient has p=8:
its packed9-by-9 upper factor costs360 B. Floating centers add64 B;12-bit center
codes add12 B, giving **372 B** for factor plus center codes instead of424 B,
before metadata, domains, noise constants, error ledger and workspace.

For eight health quantities with fully coupled4+3+1 coefficients each, p=64.
A dense65-by-65 augmented factor alone uses17160 B; a joint Gaussian mean and
covariance over those64 coordinates uses17152 B. These exceed10KiB even before
other states/workspace. A different justified dependency structure may be
smaller, but center quantization alone does not solve the full uncertainty
storage problem. The implementation remains desktop research, not firmware-ready.
