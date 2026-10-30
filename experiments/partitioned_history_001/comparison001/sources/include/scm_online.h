#ifndef SCM_ONLINE_API_H
#define SCM_ONLINE_API_H

/* Fixed-storage, joint square-root EKF candidate for the matched static 3RC
 * model. P=L*L^T; the full square array stores a lower-triangular factor with
 * nonnegative diagonal. Entries above it must be exact numeric zero; rank
 * deficiency is allowed. There is no variance floor or rank threshold.
 * The belief is a local, prior-conditioned Gaussian approximation. It is not
 * the exact retained likelihood, a hard error envelope or validated coverage.
 * Every known physical interval is advanced and each voltage is used once.
 * Public structs are for explicit checkpoint codecs and inspection; use the
 * API for live mutations. Caller objects/workspace must be disjoint.
 */
#include "scm_model.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SCM_ONLINE_DIM 16
#define SCM_ONLINE_SOURCE_BYTES 32
#define SCM_ONLINE_MODEL_VERSION 2u
enum {
    SCM_ONLINE_LOG_TAU1=0, SCM_ONLINE_LOG_TAU2=1, SCM_ONLINE_LOG_TAU3=2,
    SCM_ONLINE_LOG_GAMMA_PLUS=3, SCM_ONLINE_LOG_GAMMA_MINUS=4,
    SCM_ONLINE_LOG_Q=5, SCM_ONLINE_R0=6, SCM_ONLINE_R1=7,
    SCM_ONLINE_R2=8, SCM_ONLINE_R3=9, SCM_ONLINE_H=10,
    SCM_ONLINE_Z=11, SCM_ONLINE_V1=12, SCM_ONLINE_V2=13,
    SCM_ONLINE_V3=14, SCM_ONLINE_HYST=15
};
enum {
    SCM_ONLINE_OK=0,
    /* Known input was consumed, but propagation became unavailable. The last
     * valid belief is retained and is no longer reported as a current point.
     * Further ingestion requires explicit recovery/reset. */
    SCM_ONLINE_ACCEPTED_RECOVERY=1,
    SCM_ONLINE_ERR_ARGUMENT=-100, SCM_ONLINE_ERR_ORDER=-101,
    SCM_ONLINE_ERR_SOURCE=-102, SCM_ONLINE_ERR_NONFINITE=-103,
    SCM_ONLINE_ERR_DOMAIN=-104, SCM_ONLINE_ERR_OVERFLOW=-105,
    SCM_ONLINE_ERR_RECOVERY_REQUIRED=-106, SCM_ONLINE_ERR_STATE=-107
};
enum {
    SCM_ONLINE_FLAG_HISTORY_LOST=1u<<0,
    SCM_ONLINE_FLAG_RECOVERY_REQUIRED=1u<<1,
    SCM_ONLINE_FLAG_MODEL_UNAVAILABLE=1u<<2,
    SCM_ONLINE_FLAG_MISSING_VOLTAGE=1u<<3,
    SCM_ONLINE_FLAG_UPDATE_REJECTED=1u<<4,
    SCM_ONLINE_FLAG_GAIN_LIMITED=1u<<5
};
typedef enum {
    SCM_ONLINE_UNKNOWN=0, SCM_ONLINE_UNEXCITED=1,
    SCM_ONLINE_UNRESOLVED=2, SCM_ONLINE_PROVISIONAL=3
} scm_online_status;

typedef struct {
    unsigned char source_id[SCM_ONLINE_SOURCE_BYTES];
    double sigma_V, max_dt_s, max_abs_current_A;
} scm_online_config;

typedef struct {
    scm_online_config config;
    double mean[SCM_ONLINE_DIM];
    double factor[SCM_ONLINE_DIM*SCM_ONLINE_DIM];
    uint64_t epoch_begin, next_index, evidence_next_index;
    uint64_t prediction_count, voltage_count, missing_voltage_count;
    uint64_t rejected_voltage_count, limited_gain_count, zero_gain_count;
    uint64_t cold_resets;
    double elapsed_s, epoch_elapsed_s;
    double last_current_A, last_prediction_V, last_innovation_V;
    double last_innovation_variance_V2, last_gain_scale, minimum_gain_scale;
    /* Min/max multipliers over active normalized gain components; both 1 if
     * none. Masks use bit i: limited lambda_i<1, blocked actual t_i==0.
     * zero_gain_count counts all t_i==0, including zero sensitivity, and need
     * not be bounded by limited_gain_count. Counters survive cold reset. */
    double last_max_gain_scale;
    unsigned last_limited_mask, last_blocked_mask;
    /* Bounded EWMA of normalized squared innovation, clamped to 1e12 before
     * averaging. Diagnostic only; never changes gain, noise or evidence. */
    double innovation_ewma;
    unsigned flags, excitation;
    int initialized, has_voltage, prediction_valid;
} scm_online;

typedef struct {
    scm_online candidate;
    double observation_gradient[SCM_ONLINE_DIM];
    double projected_gradient[SCM_ONLINE_DIM];
    double covariance_gradient[SCM_ONLINE_DIM];
    double correction[SCM_ONLINE_DIM];
} scm_online_workspace;

typedef struct {
    scm_online_status soc_status, capacity_status;
    unsigned flags, excitation;
    uint64_t epoch_begin, next_index, evidence_next_index, evidence_age_samples;
    uint64_t prediction_count, voltage_count, missing_voltage_count;
    uint64_t rejected_voltage_count, limited_gain_count, zero_gain_count, cold_resets;
    double elapsed_s, epoch_elapsed_s;
    double mean[SCM_ONLINE_DIM], coordinate_sd[SCM_ONLINE_DIM];
    double current_soc, capacity_Ah, predicted_voltage_V;
    double soc_local_lower, soc_local_upper;
    double capacity_local_lower_Ah, capacity_local_upper_Ah;
    double last_innovation_V, last_innovation_variance_V2, last_gain_scale, minimum_gain_scale, innovation_ewma;
    double last_max_gain_scale;
    unsigned last_limited_mask, last_blocked_mask;
    int point_available, capacity_available, prediction_available, local_ranges_available;
    int soc_local_precision_hard, capacity_local_precision_hard;
    int soc_local_precision_preferred, capacity_local_precision_preferred;
    size_t state_bytes, workspace_bytes;
} scm_online_query_result;

void scm_online_config_default(scm_online_config*);
int scm_online_config_valid(const scm_online_config*);
int scm_online_config_equal(const scm_online_config*,const scm_online_config*);
int scm_online_init(scm_online*,const scm_online_config*);
/* Checkpoint validation is read-only and does not re-run inference. */
int scm_online_validate(const scm_online*);
void scm_online_bounds(double lower[SCM_ONLINE_DIM],double upper[SCM_ONLINE_DIM]);

/* Negative return: no live state change. Positive ACCEPTED_RECOVERY: retain
 * the known clock/index, mark the belief unavailable, and require recovery.
 * Missing V ignores its payload; successful physical prediction is retained.
 * Numerically unusable voltage correction retains predicted belief, increments
 * rejected_voltage_count and sets UPDATE_REJECTED; return is still OK.
 * Domain-limited correction independently scales each gain coordinate and uses
 * the corresponding full Joseph covariance. This is feasible coordinatewise
 * limiting, not an optimal constrained posterior. No mean-only clipping.
 * A valid physical prediction is committed before a staged correction, whose
 * failure cannot corrupt that prediction. All-zero selected gain preserves
 * the predicted mean/factor bytes exactly; zero residual can still learn.
 */
int scm_online_ingest(scm_online*,const unsigned char source_id[SCM_ONLINE_SOURCE_BYTES],
    uint64_t sample_index,const scm_sample*,int voltage_present,scm_online_workspace*);
int scm_online_query(const scm_online*,scm_online_query_result*);
int scm_online_mark_unknown_gap(scm_online*);
int scm_online_cold_reset(scm_online*);
const char *scm_online_status_name(scm_online_status);

#ifdef __cplusplus
}
#endif
#endif
