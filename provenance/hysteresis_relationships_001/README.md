# A specific missing interaction explains the centre hysteresis error

We can now connect a specific basis truncation to a voltage error and then to
SOC/capacity inference. This is more precise than a general instruction to raise
polynomial degree. Four individually reviewed conditional derivations are in
[the proof collection](../../specifications/hysteresis_relationships_001/README.md).
The model and production estimator are unchanged; no candidate is promoted.

## The exact physical relationship

For one fixed-sign segment, let U be absolute charge throughput in Ah,
s=sign(I), and k_s=gamma_s/Q. The declared model gives

    h_out=s+(h_in-s)*exp(-k_s*U).

Consequently log(1-s*h) changes linearly with U away from saturation. This is a
state-coordinate identity, not a transformation of measured-voltage noise.
Reversals compose different affine maps. A plus segment then minus differs from
minus then plus by -2*(1-exp(-kplus*Uplus))*(1-exp(-kminus*Uminus)), even with
identical total directional charge. History order is physically relevant.

The free response is exp(-kplus*Uplus-kminus*Uminus). The forced response is a
chronological sum of exponentials evaluated at suffix-exposure pairs. The free
response is separable; the forced response generally contains interacting rates.
For an exactly repeated word, its endpoint follows an affine fixed point plus an
exponential transient. For a two-direction cycle, total dose and dose imbalance
determine the steady hysteresis midpoint and span. Those are stimulus-dependent
response coordinates, not independent health parameters or posterior weights.

## The concrete basis defect

The existing quadratic hysteresis field uses a 3x3 collocation grid but retains
only six total-degree 2 terms. It drops (1,2),(2,1),(2,2). At the public centre,
T1(0)=0 and T2(0)=-1, so only the last omitted term changes the response value:

    approximate response - exact response = -c22.

This is exact for the ideal central collocation node. For forced/free responses
u,E and B=H*h0,

    hysteresis voltage error e = -H*c22(u)-B*c22(E).

c22 is the grid's mixed finite difference: four corners minus twice the four
edge midpoints plus four times the centre, divided by 9. It is a physical-rate
interaction encoded by the chosen collocation basis. A one-direction history
has no dependence on the unused rate and hence no such mixed coefficient.
After exactly two sign runs,

    e=(H*s_first-B)*c2(Eplus)*c2(Eminus).

This explains why the centre can look exact in one-direction use, then develop
an error after reversal. It does not imply all centre derivatives are exact:
the omitted (1,2)/(2,1) terms change derivatives relative to the full interpolant,
which itself may have derivative error relative to the physical response.
Raising the total degree to 3 on a different 4x4 grid does not simply restore the
missing(2,2) interaction, which is total degree 4.

The numerical witness confirms the centre-voltage identity against independent
C to at most 2.09e-14 V across the three saved streams through one hour. The
corresponding forced/free coefficient gap is at most 1.74e-12. A 100 random-grid
check of the projection identity closes to 1.12e-15. Embedded's two-run endpoint
product predicts its voltage defect within 1.47e-14 V. These are finite arithmetic
checks at the public centre, not accuracy certificates over the parameter box.
See [mixed_term_checks.json](mixed_term_checks.json).

## How this reaches SOC and capacity

Use q=1/Q and linear OCV slope m, with signed charge A_i. At fixed independent
rates k and other amplitudes, the z0,q voltage columns are m and -m*A_i. Therefore
an H-only voltage defect e_i changes their likelihood gradients by

    delta_g_z0 = m*sum(w_i*e_i),
    delta_g_q  = -m*sum(w_i*A_i*e_i),  w_i=1/sigma_i^2.

For the two unconstrained conditional quadratic fits, with all nuisance values
fixed and no added prior, the exact displacement is

    delta_q  = Cov_w(A,e)/(m*Var_w(A)),
    delta_z0 = -mean_w(e)/m + mean_w(A)*delta_q.

Thus a constant e shifts SOC but not q in this conditional fit, whereas e
proportional to signed charge is indistinguishable from a capacity change.
When signed charge does not vary, the joint z0/q fit is rank-deficient: rest
cannot justify a new capacity estimate. Full joint fitting, priors, constraints,
nonlinear OCV or aging require the additional terms and qualifications in H3.
The source-to-result chain at the centre is now explicit: missing mixed coefficient
-> voltage-response defect -> weighted charge moments -> conditional fit shift.

On the saved streams, the gradient identities agree with the chained C Jacobian
to 8.47e-16 relative and the independent QR conditional-fit displacement to 4.24e-16
absolute in the displayed (z0,q) coordinates. All rest cases correctly report zero
charge variation as unresolved. The reported conditional-fit comparisons are not
full-estimator SOC/Q accuracy measurements. See [charge_moment_checks_v2.json](charge_moment_checks_v2.json).

Independent controls review found a reporting defect: earlier prefix records
referenced a gradient array that later prefixes updated in place. The calculations
were correct, but four saved vectors were not. The original runner and report are
preserved under `versions/`, and the original `charge_moment_checks.json` remains
unchanged as a negative control. The runner now snapshots the array with `g.copy()`;
a separate `check002` rerun supplies the corrected receipt above. The
[serialization regression](serialization_regression.json) rejects the original
receipt and verifies all nine corrected prefix records. See the original
[review findings](controls_review_r1.json). These controls use synthetic measured
streams; the public-centre voltage witness has B=0, with the free response checked
separately. General near-rank-deficient fits need explicit numerical rank handling.

## Why the previous coordinate results differ

Physical-rate polynomials reproduce the low-throughput Taylor terms, explaining
the earlier short weak-exposure result. That asymptotic keeps a finite word fixed
while its exposure shrinks. It is not uniform in duration, repetitions or dose.
At the public centre the current one-hour multiscale/embedded total doses are
about 5.26/2.98, with 96/2 sign runs respectively. Recent suffix doses also matter;
these totals alone cannot attribute the error or guarantee a coordinate ranking.
The current mixed-term identity identifies a concrete defect without claiming
that the small-exposure theorem predicts every finite-dose interpolation error.

A simple repeated-word endpoint still does not give exact fixed-basis likelihood
storage: measured-data cross terms can contain sum y_n*E^n, whose polynomial
space grows with the number of measurements. Approximate compression remains
possible; bounded-memory accuracy has not been proved here. Physical state
relaxation does not erase old likelihood evidence or authorize statistical decay.

## What this suggests next

Test specific mixed-term completion, preserving the single joint square-root
factor and unchanged continuous support:

| H representation, RC degree 2 | Packed likelihood factor | Factor + response + domain/scalar subtotal |
|---|---:|---:|
| Current total-degree 2 | 4760B | 5168B |
| Add(2,2) for forced/free H | 5328B | 5736B |
| Full quadratic H tensor | 6560B | 6968B |
| Previous total-degree3 | 7224B | 7744B |

The c22-only option adds 568 factor bytes and removes this specific centre-value
truncation, but leaves other mixed-term and derivative errors. The full quadratic
tensor adds 1800 factor bytes and removes those three tensor-truncation terms,
but still has interpolation error. Neither is an implemented/promoted repair.
All subtotals exclude tables/calibration, metadata, prior, optimizer, transactions,
scratch, stacks/ISR and other overhead; no full 10 KiB qualification follows.

The next experiment should compare these two precise interventions against the
existing controls, including off-centre derivatives and fitted/application queries.
That is a better-informed next question than adding another global degree without
knowing which interaction is missing. Preserve every regression and the known
domain-exit refusal. Aging, physical coverage, uniform error, migration and decade
resource/availability claims remain open.
