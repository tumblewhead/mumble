#ifndef MUMBLE_ROLLING_MODEL_H
#define MUMBLE_ROLLING_MODEL_H

#include "../live_anchor_bootstrap_001/live_layout.h"
#include "features.h"

/* Rolling-model kernels, not an estimator transaction or uncertainty law.
 * Original entering x order and public support are those of compact_history.
 * Forced-response f/hb transport uses second-order log-rate jets. The full arm
 * computes a/ha attenuation analytically; dda[0:2] own charge magnitudes.
 * The control arm retains the inherited a/ha jets. Transport uses RAW log-rate
 * differences; factor translation uses the structured normalized coordinates.
 *
 * Read-only arrays must be disjoint from writable scratch. rm_transport permits
 * exactly out==boundary; partial overlap is unsupported. Other objects must be
 * disjoint. Numerical/domain failure may leave supplied scratch partly changed;
 * the owner must reject it or latch its transaction unavailable. None of these
 * kernels advances evidence ownership/cursors or evaluates a prior.
 */
int rm_init_jet(ch_jet *out, const double x[CH_DIM]);

/* Recenter forced-response basis values/tangents; retain their second jets.
 * Full arm recomputes initial attenuation and derivatives from time/charge.
 * Preserve charge/time and rebuild rates/Q/z0. Forced response is approximate.
 */
int rm_transport(const ch_jet *boundary, const double old_origin[CH_DIM],
                 const double point[CH_DIM], ch_jet *out);

/* Query state is exactly the existing224-byte phase object. Its basis values
 * and tangents start from the transported boundary polynomial, then evolve
 * nonlinearly over the retained block. The caller must keep point unchanged
 * between init and all steps/derivative queries for that evaluation.
 * inverse_Q stores1/exp(point[5]) for the capacity Jacobian only; SOC always
 * uses charge/exp(point[5]) in the original model's division order.
 * Initial mu is the zero-current boundary prediction; only a successful step
 * makes mu the prediction for the supplied observation interval/current.
 */
int rm_query_init(lab_query_state *out, const ch_jet *boundary,
                  const double old_origin[CH_DIM], const double point[CH_DIM]);
int rm_query_step(lab_query_state *state, const double point[CH_DIM],
                  const adc12_reading *reading);

/* Unwhitened voltage derivative in original x coordinates. Requires the state
 * after a successful step with this point/reading. No full row/vector is
 * allocated. Invalid index/pointer or a nonfinite result returns NAN.
 */
double rm_query_derivative(const lab_query_state *state,
                           const double point[CH_DIM],
                           const adc12_reading *reading, unsigned coordinate);

/* Advance forced-response jets and emit structured37 coefficients. Full arm
 * uses analytic initial attenuation and dda[0:2] as charge integrals; see features.h.
 * Query/support/prior coordinates remain the original16 x. */
int rm_merge_step(ch_jet *state, const double origin[CH_DIM],
                  const scm_sample *sample, double sigma_V, double row[CH_AUG]);

#endif
