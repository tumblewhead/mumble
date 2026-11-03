# Full joint refits at unchanged public centres and support

Base 0f02271, branch experiment/conditional-architecture-001. This follows the
reviewed H5/H6 kernel and saved-anchor comparison. No physical model, prior,
centre, shape support, observation ownership or production default changes.

Use both frozen prefixes (21008 and 126000 records) and all three recipes: rest,
multiscale and embedded. Refit all 16 coordinates jointly for five arms:
direct, TaylorRC_H2, TaylorRC_TaylorH2, TaylorRC_H7 and the separate R5_H7 reference.
All principal H comparisons use identical Taylor RC. Each fit uses the same two
public starts (zero and alternating +/-0.05 in prior-whitened coordinates), the
unchanged prior once, and the existing 60-round GN solver/stopping rules. Retain
every attempt, numerical stop and support failure. An unresolved reference prevents
fit-to-fit qualification; an available anchor can still have labeled local readouts.

Reuse the reviewed fit_prefix engine, with its internal R2_H2 gate key explicitly
aliased to the TaylorRC_H2 field and renamed in the output. This key is routing only:
its field supplies the original log-rate box and physical-path support, not an
R2 interpolation fit. Verify unchanged direct/TaylorRC_H2/R5_H7 selected fits
against the frozen pilot/full studies. Old results and identities remain untouched.

Keep the solver and its legacy readouts unchanged for reproducibility. Separately
compute QR-root covariance readouts at every selected fit to avoid normal-matrix
roundoff in weak directions. At every compressed fit apply M1/P3 to RC-only,
H-only and combined defects; retain actual joint spectra as well as sufficient
epsilon tests. Use full coordinate chains and the complete joint prior/covariance.

Report fitted Q, origin/end SOC and physical parameter shifts relative to the
direct fit; rate offsets from the ORIGINAL centres and remaining box margin;
direct-likelihood cost and gradient defects; Q and SOC widths at the same anchor
and relative to the direct fitted reference; sampled rest60 and 120mA10s/rest30
forecasts under direct and compressed state transport. QR readouts must distinguish
same-anchor inference distortion from fit-to-fit displacement. No truth-based
initialization, centering, selection or state correction is allowed.

Tests cover the explicit arm-key routing, shared starts/domain, convergence gating,
QR dense uncertainty, and native short-prefix diagnostic consistency. Obtain an
independent implementation review and a result/reproduction review. Use the full
registered sweep once; any additional search or repair gets a separate record.
No new kernel or numerical solver change is planned. Previous off-centre and RC
rest failures stay visible even if refits improve the active cases.

Save source identities, commands, fit statuses and compact summaries; generated
fits/factors remain local ignored artifacts. This desktop reference holds a finite
prefix for replay (up to 5,040,000 B observation array), not firmware workspace.
Candidate packed factor remains 4760 B and partial numeric subtotal 5168 B. Matched
TaylorRC_H7 factor 35720 B and R5_H7 factor 50624 B are reference controls. Complete
SRAM/timing, calibrated coverage, aging and indefinite-history fidelity remain open.
