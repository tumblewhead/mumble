#ifndef MUMBLE_LIVE_ANCHOR_SUPPORT_STEP_H
#define MUMBLE_LIVE_ANCHOR_SUPPORT_STEP_H

/* Experimental proposal primitive only: no likelihood, prior, observations,
 * posterior covariance, model propagation, heap, or accepted-state mutation.
 * Original x order matches compact_history.h. The caller supplies the complete
 * joint gradient and a GN + kernel-precision metric in that original chart.
 */
#include <stddef.h>
#include <stdint.h>

#define SS_DIM 16
#define SS_PACKED 136
#define SS_PLANES 6

enum { SS_OK=0, SS_UNRESOLVED=1, SS_ERR_ARGUMENT=-1,
       SS_ERR_NONFINITE=-2, SS_ERR_DOMAIN=-3, SS_ERR_METRIC=-4,
       SS_ERR_ALIAS=-5 };
enum { SS_REASON_NONE=0, SS_REASON_NO_DIRECTION=1,
       SS_REASON_ROUNDING=2, SS_REASON_ARITHMETIC=3,
       SS_REASON_NONFINITE=4, SS_REASON_METRIC=5 };

/* Exactly the existing 1600-byte query phase; no new persistent arrays.
 * packed and gradient are inputs. packed is destructively replaced with the
 * signed scaled metric and then its unmodified Cholesky factor. gradient stays
 * in original x units. point is the returned original-x proposal; direction
 * is its reciprocal-coordinate proposal displacement, not an x displacement.
 */
typedef struct {
    double packed[SS_PACKED], gradient[SS_DIM], point[SS_DIM];
    double majorizer[SS_DIM], direction[SS_DIM];
} ss_workspace;

/* Existing bank/flash arrays, not copied or retained. The charge extrema must
 * include zero. None of these arrays, input itself, workspace, or result may
 * overlap a writable output object. The four read-only arrays may alias each
 * other. Caller owns and counts this 48-byte configuration view.
 */
typedef struct {
    const double *anchor, *sd, *lower, *upper;
    double charge_min_Ah, charge_max_Ah;
} ss_input;

/* Fits the existing 120-byte result phase. These are computed-operand
 * resolution diagnostics, never nonlinear remainder or libm error bounds.
 * The reciprocal quadratic metric is a local optimization construction; the
 * nonlinear coordinate change does not make it a global prior majorizer.
 */
typedef struct {
    double original_slope, original_slope_allowance;
    double tangent_model_decrease, tangent_model_allowance;
    double diagonal_model_decrease, diagonal_model_allowance;
    double min_support_slack, min_step_slack, min_polygon_slack;
    double minimum_majorizer;
    int32_t status, reason;
    uint32_t edges_considered, plane_tests, candidates_considered;
    uint32_t selected_candidate, cholesky_entries, cholesky_products;
    uint32_t dot_products, quadratic_products;
} ss_result;

size_t ss_workspace_bytes(void);
size_t ss_input_bytes(void);
size_t ss_result_bytes(void);

/* At most six edge segments plus the unconstrained polygon minimizer and
 * zero baseline. The original one-SD logQ interval is transformed to reciprocal
 * capacity; it is not replaced by |t5|<=1. q=exp(-x5), t5=(q-q0)/(q0*SD5).
 * J=diag(SD), except J55=-SD5. Objective/prior density remains in original x;
 * there is no change of probability base measure and no density Jacobian.
 *
 * Prevalidation errors return a negative status without modifying workspace
 * or result. Later errors may destroy packed and update diagnostics. Only an
 * SS_OK return makes point usable. Finite unresolved outcomes include strict
 * original-support/trust-box rounding rejection; no post-proposal clipping or
 * numerical covariance/metric repair is performed. A successful proposal is
 * not an accepted nonlinear step and makes no stationarity claim.
 */
int ss_propose(const ss_input *, ss_workspace *, ss_result *);

#endif
