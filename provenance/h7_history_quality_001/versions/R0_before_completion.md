# R0: validated response coefficients for a restricted stationary family

Status: candidate proof, pending independent review. This packet concerns the
new desktop interval implementation, not binary libm or target hardware.

Assume stationary reference-condition parameters, exact measured current and
actual interval duration, current held constant on each supplied interval,
constant25C equal to the exact public reference298.15K,
and exact public linear OCV V0+s*z with s>0. There is no aging or calibration error
in this family. Current and durations are the exact rational values of supplied
finite binary64 observations. Other interpretations need their own input bounds.

Use amplitude a=(z0,v10,v20,v30,q,R0,R1,R2,R3,H,B), q=1/Q>0, B=H*h0,
with |B|<=H. The five stationary shape quantities are
(tau1,tau2,tau3,kplus,kminus), where kdir=gammadir/Q. A fixed shape therefore
couples gamma to Q; it is not knowledge of gamma independently of unknown Q.
Positive ordered tau and positive k have declared fixed values or public intervals.

## Arithmetic lemma

An interval stores integers (l,u) and denotes [l/S,u/S], S=2^80. Converting a
rational number uses floor(S*x),ceil(S*x). Addition and negation are exact on
the grid. Multiplication takes all four integer endpoint products and rounds
min/S downward and max/S upward. Division takes all endpoint ratios with the
appropriate scale, rounded outward, and rejects denominators containing zero.
Monotonicity on each denominator sign and the endpoint product extrema prove
each resulting interval contains every pointwise real operation. Python arbitrary
integers and Fraction implement these integer/rational operations exactly under
the usual runtime arithmetic premise; their memory/time is not target-bounded.

## Exponential lemma

For a nonnegative rational x choose m>=0 with r=x/2^m<=1. In the alternating
series for exp(-r), term magnitudes r^n/n! decrease to zero. The alternating
remainder theorem yields S33<=exp(-r)<=S32, with each partial sum evaluated as
an exact rational. Both endpoints are positive for r in[0,1]. Outward grid
conversion and m interval squarings therefore enclose exp(-x). For interval
x=[l,u], monotonicity gives exp(-x) in[exp(-u),exp(-l)]. The implementation uses
the lower enclosure endpoint at u and upper endpoint at l.

The bounded cache is keyed by the complete immutable integer interval. Precision,
series order and arithmetic semantics are fixed by this module revision. The
function has no observation/configuration dependencies beyond that argument.
Thus a hit returns exactly the same immutable result as recomputation; eviction
changes cost only. No approximate keys, cross-version persistence or mutable
returned objects are admitted. This is the limited K3 premise for this cache.

## Response lemma

For each RC branch define E0=1,u0=0 and e=exp(-dt/tau):

    E_next=e*E; u_next=I+e*(u-I).

Then v_i(t)=E_i*v_i0+u_i*R_i by induction in the Foster recurrence. Define
Eh0=1,uh0=0. For nonzero current let sign=sign(I) and
eh=exp(-kdir*|I|*dt/3600); set Eh_next=eh*Eh and uh_next=sign+eh*(uh-sign).
At zero current retain Eh,uh. Then H*h(t)=Eh*B+uh*H. The identity also includes
H=0 if B=0; the pilot public box has H>0. All voltage samples are endpoint samples.

Accumulate A=sum I*dt/3600 exactly as a rational. The SOC identity is z=z0-A*q.
Consequently V=V0+beta*a, with

    beta=(s,-E1,-E2,-E3,-s*A,-I,-u1,-u2,-u3,uh,Eh).

Apply the arithmetic/exponential lemmas inductively to the recurrences. For any
one stationary shape in the declared box, the true coefficients remain inside
the computed intervals at every processed prefix. Repeated interval occurrences
may widen the result but cannot remove that fixed physical trajectory. Every
actual interval is propagated, including those whose voltage is not retained.
No contraction, posterior-mass preservation, or independence of coefficients is
assumed. A_min/A_max also give exact SOC path extrema because q>0.

This establishes coefficient containment under the stated mathematical/runtime
premises. It does not establish that a real battery satisfies the shape/voltage
envelope, or that interval widths remain useful for a long run. Constant reference
temperature is essential to this implementation; time-varying Arrhenius factors,
sensor error in I/dt/T, and physical-model discrepancy are not silently included.
