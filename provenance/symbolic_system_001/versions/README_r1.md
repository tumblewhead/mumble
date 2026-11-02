# Symbolic analysis now covers all four development tracks

The [working plan](../../specifications/symbolic_system_001/README.md) now has a
first conditional proof packet and finite controls for RC response, joint
uncertainty, history/aging, and optimization. This extends the hysteresis work.
It changes neither the production estimator nor a campaign default. It does not
close the physical/model, full-domain approximation or target-resource premises.
The [discovery register](discoveries.json) records findings and how they change
the next experiment; original failed claims and review findings remain preserved.

## RC: value accuracy and sensitivity accuracy are different

[R1](../../specifications/symbolic_system_001/R1.md) derives chronological affine
RC response, exact log-time-constant sensitivity, the quadratic interpolation
error mechanism, and constant-load voltage sensitivities. For a fixed boundary
state, a branch contributes

    v(L)=R*I+(v(0)-R*I)*exp(-L/tau).

Its log-tau sensitivity contains (L/tau)*exp(-L/tau), maximal at L/tau=1.
Consequently proposed-load horizon is relevant to the value of improving a pole;
the complete query must still include uncertain boundary state, other parameters,
SOC, hysteresis and their correlations. A small individual RC error is not the
only useful measure, and a poorly identified pole is not automatically disposable.

The experimental degree-2 RC basis already contains its full univariate quadratic.
Unlike H2 hysteresis, it has no omitted quadratic mixed-response term to restore.
It reproduces the central value, while its central slope is a finite difference
across collocation nodes rather than the exact physical derivative. This points
toward derivative-aware representation tests, not adding artificial cross-pole
response terms. The joint likelihood must retain its cross terms in either case.

A 600-sample public fixture (157.29 seconds, exact irregular intervals, signed
current/rest, 25 C) exercises seven public pole queries with deliberately specified
nonzero boundary RC voltages. It uses no hidden plant state or fitted centering.
At the centre, per-branch voltage defects are below 1.1e-18 V, while maximum
log-tau derivative defects are 0.111, 0.173 and 0.256 mV. Off-centre probes have
voltage defects up to 0.091 mV. These are finite value/sensitivity diagnostics,
not estimated parameter errors or domain-wide bounds. The native RC value and
sensitivity identities agree within 3.89e-16 in their respective units.

Five diagnostic load horizons (0.02, 0.07, 0.7, 6 and 60 seconds) agree with the
native forecast identities to 4.45e-16 in the checked quantities. They are not
user-specified brownout horizons or voltage safety tests. This test concerns the
architecture study's degree-2 RC field; the campaign H7 configuration uses a
different RC degree and its long-run performance is not requalified here.

## Joint uncertainty: retain nuisance coupling and weak directions

[U1](../../specifications/symbolic_system_001/U1.md) generalizes the previous
fixed-nuisance charge formula. With whitened target columns X, nuisance columns Z,
and M the orthogonal projection away from Z, an additive response defect e shifts
the unrestricted conditional target fit by

    delta_p=-(X^T*M*X)^-1 * X^T*M*e.

The inverse requires full target rank after nuisance removal. For a changed design
A+D, value and derivative defects both enter the gradient. The controlling
precision metric is ||D*(A^T*A)^-1/2||, which exposes weakly observed directions.
These are linear/quadratic or explicitly local statements, not nonlinear posterior
coverage proofs. The controls include a value-exact but derivative-wrong fit and
a 1e-6 absolute design change that is order one in a weak direction.

Twenty-four correlated-design controls close the exact displacement and nuisance
projection formulas within 2.50e-15 and 1.02e-15, respectively. The reviewed
repetition subcase is explicitly prior-free: coherent fit bias can remain while
formal widths shrink. An unchanged nonzero prior prevents exact multiplication
of the whole objective by repetition count; the original overbroad wording and
review counterexample are preserved.

## History and aging: state contraction does not bound evidence bias

[A1](../../specifications/symbolic_system_001/A1.md) separates contraction-weighted
physical-state error from cumulative likelihood error. Positive transition-evidence
kernels with uniform multiplicative error bounds compose with a sum of log-error
ranges. State-independent normalization errors cancel from the normalized posterior;
state-dependent errors generally do not. Different deterministic state maps may
have singular kernels, so small voltage-state error does not automatically supply
a multiplicative likelihood bound.

A two-label counterexample starts with exact probability 0.5 and equally likely
fresh observations. A coherent artificial log-likelihood-ratio error of 0.01 per
observation drives the approximate probability to 0.99995 after 1000 observations.
The example illustrates a failure mechanism, not a measured bias in this estimator.
Forty affine-state steps and twelve positive-kernel steps satisfy their respective
finite bounds. Equal-final-tau paths produce different endpoints, and increasing R
with decreasing C permits either increasing or decreasing tau.

The aging state convention remains a prerequisite: preserving branch voltage
and preserving C*v are different laws when C changes. No aging rate, covariance
inflation, forgetting factor, temperature spline or process-noise law is selected.
Ten-year useful accuracy still requires a qualified evolution law and cumulative
representation-error argument.

## Optimization: preserve equilibrium and bound the action of encoding error

[O1](../../specifications/symbolic_system_001/O1.md) shows why quantizing a decay
and its complementary forcing coefficient as unrelated numbers can shift the
physical equilibrium. In an artificial stable recurrence with a=0.999 and
ahat=0.99901, leaving the forcing coefficient unchanged shifts a 0.1 V equilibrium
by about 1.01 mV. A paired complement preserves that equilibrium in real arithmetic.
This is not an instruction to replace the native exp/expm1 pair: cancellation and
arithmetic rounding need their own implementation bounds.

Exact coefficient reuse depends on dt, rate, temperature and calibration identity;
state/evidence still advance for each sample. Joint-factor encoding keeps PSD but
can lose rank. A useful codebook metric bounds its action on admitted feature and
derivative sets, then on information-normalized application queries. One hundred
factor-query controls check the cost/gradient identities and feature enclosure;
a negative control demonstrates rank loss despite PSD. No cache or quantizer is
implemented and no resource savings are claimed.

## Review and next intervention

Each proof is individually reviewed. Initial review requested an explicit smoothness
premise and order convention in R1, and found the retained-prior exception in U1.
Those original versions and findings are preserved under `versions/`; revised
packets receive fresh-context review. Numerical integration and this interpretation
receive a separate review. See the final receipt for exact reviewed versions.

The next bounded experiment should test the existing c22-only/full-H-tensor
candidates with value, derivative, full joint fit and proposed-load readouts. Use
the RC derivative diagnostic to decide whether a separate RC interpolation change
has application value; do not globally increase degree by default. Rank-deficient
queries remain unresolved. A characterized aging law and complete memory/timing
budget are independent work items before deployment or optimization promotion.

Persistent estimator memory is unchanged: H2 study factor 4760 B, lower numeric
subtotal 5168 B. Previously proposed H additions cost 568 B or 1800 B in the packed
factor. None includes all tables, metadata, priors, optimizer, scratch or stacks;
there is no complete 10 KiB claim. Compact evidence and source only are tracked;
raw diagnostic binaries remain local. See [finite controls](checks.json) and
[commands](../../experiments/symbolic_system_001/README.md).
