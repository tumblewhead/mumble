# One bounded uncertain RC mode

## Outcome and scope

This checkpoint extends the integer battery provider from known RC parameters
to one fixed but uncertain resistance/time-constant pair. The new C provider
encloses every real parameter pair in a supplied box, carries the resulting RC
state intervals, and preserves the existing capacity-bin and initial-SOC
constraints. It keeps outward current-SOC and capacity queries and the complete
observation transaction.

Six written arguments cover endpoint enclosures, interval forcing, a width
bound valid for every admitted finite prefix, complete-configuration retention,
composed availability and a conditional nominal-control nesting property.
The source and proof drafts have independent mathematical/source-operation
review. Primary experimental outcomes are recorded after the source freeze.

The resistance/time-constant box is supplied before the first observation and
does not contract. Those parameters remain unresolved inside that box. This
milestone propagates uncertainty; it does not claim to learn those parameters.
Known R0, the other two RC pairs, encoded OCV, exact represented current/time,
hard voltage-error intervals and absence of drift/hysteresis remain premises.

Branch: research/indefinite-numerical-stability-004.
Base: 4a990cf923e2e56935a1ffb346215faad05bff66.

| Artifact | Role |
| --- | --- |
| [Contract](../proofs/indefinite_stability_004/contract.json) | Continuous parameter box, units, input/domain assumptions and lifetime claims |
| [Lemma ledger](../proofs/indefinite_stability_004/lemmas.json) | U1-U6 and the reference coordinate identity |
| [C API](../include/scm_certificate_box.h) | Full configuration, state, workspace and status semantics |
| [C source](../src/scm_certificate_box.c) | Box attenuation, interval forcing and integrated provider |
| [Tests](../tests/test_certificate_box.c) | Range, sign, identity, transaction and degenerate-equivalence cases |
| [Audit plan](../experiments/indefinite_stability_004/plan.json) | Predeclared uncertainty, five phase traces, gates and independent comparison |
| [Primary receipt](../experiments/indefinite_stability_004/receipt.json) | Frozen audit outcomes and complete resource measurements |
| [Earlier provider](BATTERY_CERTIFICATE_003.md) | Preserved known-RC provider and inherited SOC/capacity proofs |

## 1. What changes in the model

For the selected mode, the true constants satisfy

\[
R\in[R_l,R_u],\qquad \tau\in[\tau_l,\tau_u],\qquad \tau_l>0.
\]

They remain fixed over the certified episode. Their values can be real between
the encoded integer endpoints; they do not have to lie on a parameter grid.
The state equation is unchanged:

\[
v_{n+1}=a_n v_n+(1-a_n)I_nR,
\qquad a_n=e^{-\Delta t_n/\tau}.
\]

The public API describes all three modes with endpoint pairs, and rejects a
configuration with more than one nondegenerate mode. A mode with both uncertain
R and uncertain tau counts once. All-degenerate configurations remain valid
for comparison with the frozen known-parameter provider.

Current uses microampere codes, resistance endpoints use integer milliohms,
and state/voltage endpoints use nanovolts. Their product gives an exact
nanovolt forcing endpoint. Time uses 35,000 ticks per second; nominal 35 Hz
corresponds to 1,000 ticks, but every actual interval is retained in order.

The bank still has up to 64 immutable capacity bins. Each original bin crosses
the common initial-SOC domain, entering-RC box and the selected R/tau box. Each
bin carries a contracting initial-SOC interval. There is no growing sample
history or lifetime counter.

## 2. U1-U2: a sound interval update

### Attenuation endpoints

For a fixed nonnegative interval, attenuation is nondecreasing in tau:

\[
\frac{\partial}{\partial\tau}e^{-\Delta t/\tau}
=\frac{\Delta t}{\tau^2}e^{-\Delta t/\tau}\ge0.
\]

The lower certificate from the existing integer kernel at tau_l and its upper
certificate at tau_u therefore enclose every attenuation in the continuous
box. This uses monotonicity of the exact exponential. It does not require
rounded output intervals from different kernel calls to be nested.

Write the resulting interval as [A_l,A_u]/D, with D=2^32. Equal tau endpoints
use the frozen kernel once. Zero elapsed time gives exactly [D,D].

### Signed forcing

The forcing interval is

\[
T=[\min(IR_l,IR_u),\max(IR_l,IR_u)].
\]

Negative current reverses the resistance endpoint order. Products are formed
in int64, checked against the state domain, then converted to int32. Config
validation requires the maximum allowed current times R_u to fit that domain,
so every admitted forcing remains inside [-B,B].

### Reusing the proved point-target kernel

For f(a,x,t)=a*x+(1-a)*t, the derivative with respect to t is 1-a>=0.
The minimum over forcing therefore occurs at T_l and the maximum at T_u.
The implementation runs the unchanged point-target enclosure on two copies of
the same entering state, then selects the lower endpoint from the first and
upper endpoint from the second.

Every exact image point is a convex combination of state and forcing inside
[-B,B]. Outward rounding at integer domain endpoints preserves that invariant.
Inherited corner magnitudes are at most D*B<=2^62. No new runtime multiplication
requires a wider integer type.

All inputs, including both forcing endpoints and their order, are validated
before the exact-unity no-write return. Negative statuses preserve the entire
destination. Both endpoint calculations begin with the original interval;
feeding the second calculation from the first would implement a different and
incorrect transition.

## 3. U3: the width theorem

Let W be the entering state width and F the forcing width. For any two points
in the image rectangle,

\[
\begin{aligned}
f(a,x,t)-f(a',x',t')
={}&a(x-x')+(1-a)(t-t')\\
 &+(a-a')(x'-t').
\end{aligned}
\]

Since |x'-t'|<=2B, the image diameter and two outward endpoint roundings obey

\[
W_{n+1}\le
\frac{A_uW_n+(D-A_l)F_n+2B(A_u-A_l)}{D}+2.
\]

The three terms have distinct meanings: carried state uncertainty, uncertain
forcing, and uncertain attenuation. The final two-grid-unit allowance bounds
rounding. When tau is uncertain, the attenuation span includes model ambiguity
as well as numerical enclosure error.

Suppose a declared future input domain certifies

\[
A_u\le D-g,\quad g>0,\qquad
D-A_l\le b,\qquad A_u-A_l\le h,\qquad F_n\le F_{\max}.
\]

Set rho=1-g/D. Geometric induction gives

\[
W_n\le
\min\left(2B,\;
\max\left(W_0,\frac{bF_{\max}+2Bh+2D}{g}\right)\right)
\]

for every finite prefix. Arbitrarily many exact [D,D] identity updates can
intervene because they add no width or rounding. The index in this proof is
mathematical; the runtime stores no corresponding lifetime count.

This theorem bounds the larger rectangle used by the implementation. It does
not assume that the true state, R and tau become independent. Their lost
correlations make the bound conservative. If no positive future contraction
margin is certified, the refined bound is unavailable; the convex-domain
2B bound and containment still hold.

The audit computes the width certificate with arbitrary-precision integers and
rational arithmetic. Its generic numerator can exceed fixed-width ranges even
though every runtime state update remains safe. The C provider does not
evaluate or accumulate that numerator.

## 4. U4-U5: evidence and availability still compose

The compatible set now contains complete static configurations

\[
(R,\tau,z_0,Q,\text{initial RC}).
\]

For any such configuration consistent with the whole prefix, U1-U2 enclose its
RC trajectory. Corrected-voltage addition and the unchanged PWL inverse enclose
its current SOC. The exact charge-ratio bound gives its depletion. Thus its
initial SOC lies both in the previous retained interval and in the new implied
interval for every original capacity cell containing its Q. Intersecting
those intervals cannot exclude it.

This is an every-containing-cell statement, including overlaps and shared
capacity boundaries. The stored outer support may still contain false
positives. In particular, propagating a shared interval can admit trajectories
that effectively choose different nuisance values at different times, even
though the true R and tau are fixed. This is a precision cost; it does not
invalidate containment of every fixed admitted pair.

The outward queries and historical-retention arguments then transfer from
certificate003. Excluded cells stay excluded, active SOC0 intervals contract,
and equal-net-charge queries cannot widen. Changing physical charge can grow
current-SOC width because capacity remains uncertain. A zero-charge prefix
still supplies no capacity discrimination; returning to zero after informative
history retains earlier exclusions.

The staged bank still makes one complete observation a transaction. A negative
status leaves the bank unchanged and does not propagate that sample. A valid
contradiction commits the physical update and empty support. Neither case
silently resets the evidence.

The charge-domain argument is unchanged:

\[
|P_n|=126000000\,Q\,|z_0-z_n|
\le12600000000000<2^{44}
\]

when Q<=100000 microAh and the true SOC trajectory remains in[0,1]. Validated
forcing and convex RC domains supply the remaining arithmetic invariants.
Every admitted update therefore returns OK at every finite prefix under the
complete contract. Age alone causes neither range failure nor loss of true
support. The proof is conditional on the model/error/storage/delivery premises;
it is not a claim about an aging physical cell or the full original estimator.

The parameter box must be immutable. Widening it after historical exclusions
can make formerly rejected configurations compatible with the old observations.
Checking that the new endpoints are well formed would not justify retaining
those exclusions. That operation needs a separate history/transport proof.

## 5. U6: adding uncertainty must not create spurious precision

The experiment includes a public nominal singleton control and the uncertain
box on the same observations. For this comparison, it explicitly certifies
that the nominal computed attenuation interval lies inside the box interval
for every tick in the declared future alphabet, including zero-time identity.
Physical parameter containment alone is insufficient to assert that property
for rounded numerical enclosures.

Given that extra certificate and common priors, scales, R0/OCV, initial states
and admitted inputs, monotonic interval propagation preserves nested RC states.
Voltage inversion, initial-SOC intersection and target projection preserve
the same inclusion. Every active nominal cell and its meaningful SOC0 support
remain inside the uncertain bank's support. Frozen fields of excluded nominal
cells have no support meaning and need not remain nested.

This gives an all-prefix comparison theorem on the certified alphabet and a
useful implementation canary. It requires no positive contraction margin.
The uncertain provider's soundness for the full continuous parameter box is
already established by U1-U5 and does not depend on the nominal comparison.

## 6. Frozen experiment and reference comparison

The public stress box is R=[54,66] milliohm and tau=[27,33] seconds for the slow
mode, an explicit +/-10 percent interval around the previously declared public
60 milliohm/30 second model. It is not a measured calibration result. The box,
trace, cases and usefulness gates are selected before numerical development.

The same 3,675-sample phase shape as003 is used: 5 seconds of unexcited rest,
35 seconds of charging, 30 seconds of quiet rest and 35 seconds of renewed
charging. The actual tick pattern is retained. Five complete cases exercise
the public midpoint and all four R/tau corners. A separate fractional-parameter
case checks continuous interior values, and other small canaries cover signed
charge, shared capacity boundaries, entering-state uncertainty and errors.

Truth remains in generation/scoring. Every full case uses the same public
uncertain configuration. The generator supplies observations, and an independent
positive-series rational exponential oracle checks the exact modeled state.
The voltage admission interval remains a declared hard +/-1 mV assumption.

Each full case must retain truth and prior evidence, leave capacity unresolved
at zero charge, and preserve quiet-use queries. Strict capacity/evidence
narrowing after each informative phase is the same usefulness gate used in003.
A failure remains recorded; it does not authorize changing the uncertainty box
or a gate to obtain a pass. Useful precision and soundness are separate outcomes.

### Keeping the original C reference

The frozen three-mode solver's slow-tau support ends at30 seconds, which would
exclude part of the chosen box in its original coordinates. The new harness
uses a public exact unit transformation while retaining the old solver source:

\[
\Delta t'=\Delta t/2,\quad I'=2I,\quad
R'=R/2,\quad \tau'=\tau/2.
\]

Capacity, SOC, voltage and initial RC voltages are unchanged. The identities
I'*dt'=I*dt, dt'/tau'=dt/tau and I'*R'=I*R preserve the exact trajectory and
objective. Known fast time constants map to0.025 and0.25 seconds, inside the
frozen solver bounds. The free slow-tau support maps back to physical[3,60]
seconds and the free resistance support to[0,2]ohm. These cover the complete
certificate box but remain broader supports, so this is not an equal-domain
likelihood comparison.

The selected R/tau, SOC0 and capacity are free in this comparison. No synthetic
unknown parameter is supplied as a fixed value or start. The three public
solver-coordinate starts are unchanged; their physical tau values change with
the unit map. Reported tau, R and physical time are converted back by two;
charge, SOC, capacity, objective and CPU time are not scaled.

The raw four-coordinate Gram uses the solver's stated scales. In particular,
R'/.2 corresponds to physicalR/.4. It is a local diagnostic at the returned fit,
not a coverage claim or marginal SOC/capacity precision while nuisance values
are free. Exact model invariance also does not imply bitwise floating-point
identity between different evaluation paths.

Detailed primary outcomes and host object/stack accounting are added after the
source freeze. Physical validation and complete Cortex-M23 qualification remain
outside this checkpoint.

## 7. Remaining gates

The immediate question after this experiment is how much useful SOC/capacity
precision survives the declared nuisance uncertainty, and whether the shared
interval representation's discarded correlations are the main cost. Any next
representation must retain the actual static parameter semantics and prior
constraints while keeping complete storage bounded.

Measured bounds, uncertain current/time and OCV, other unknown dynamics,
hysteresis, temperature/aging, box transport, delivery, persistence/recovery
and target resources still need separate arguments and evidence. A small
successful trace cannot substitute for either physical validation or the
all-prefix proof.
