#ifndef SCM_EVIDENCE_H
#define SCM_EVIDENCE_H

/* Fixed-chart local likelihood evidence, not a nonlinear posterior.
 * No heap, variable-length arrays, raw history, explicit Q basis or reanchor.
 * All theta/alpha coordinates refer to the ORIGINAL entering-state chart.
 * The caller must keep the OCV arrays unchanged for the bank's lifetime.
 * Source identity/order checks are an in-process contract, not a durable
 * exactly-once or cryptographic authenticity mechanism.
 */
#include "scm_model.h"
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_EVIDENCE_DIM (SCM_MAX_THETA+SCM_MAX_ALPHA)
#define SCM_EVIDENCE_AUG (SCM_EVIDENCE_DIM+1)
#define SCM_EVIDENCE_PACKED (SCM_EVIDENCE_AUG*(SCM_EVIDENCE_AUG+1)/2)
#define SCM_EVIDENCE_SOURCE_BYTES 32
enum {
    SCM_EVIDENCE_OK=0,
    SCM_EVIDENCE_ERR_ARGUMENT=-10,
    SCM_EVIDENCE_ERR_SOURCE=-11,
    SCM_EVIDENCE_ERR_ORDER=-12,
    SCM_EVIDENCE_ERR_NONFINITE=-13,
    SCM_EVIDENCE_ERR_DOMAIN=-14,
    SCM_EVIDENCE_ERR_RADIUS=-15,
    SCM_EVIDENCE_ERR_OVERFLOW=-16
};

typedef struct {
    /* Always packed with max augmented dimension 17, even for fewer modes.
     * Only rows/columns 0..dim are meaningful. Last column is y-mu.
     * cost(delta) = 0.5 * ||upper * [delta,-1]||^2.
     */
    double upper[SCM_EVIDENCE_PACKED];
    uint64_t samples;
    int dim;
} scm_evidence_factor;

typedef struct {
    int modes;
    double theta[SCM_MAX_THETA], alpha[SCM_MAX_ALPHA];
    double scale[SCM_EVIDENCE_DIM], radius[SCM_EVIDENCE_DIM];
    double sigma;
    double residual_rms_limit_sigma;
    uint64_t max_event_samples;
    unsigned char source_id[SCM_EVIDENCE_SOURCE_BYTES];
    scm_ocv ocv;
} scm_evidence_config;

typedef struct {
    scm_evidence_config config;
    scm_model_state model;
    scm_evidence_factor history, event;
    uint64_t first_index, next_index, active_begin, events_completed;
    /* Positive/negative throughput excitation, respectively, bits 0/1.
     * A nonzero current with dt=0 does not excite its hysteresis rate.
     */
    unsigned excitation;
    int has_last;
    double last_current, last_dt;
    /* Exact sufficient metadata to screen SOC-domain feasibility for every
     * historical sample at any candidate with positive constant Q.
     */
    double charge_min_Ah, charge_max_Ah;
    /* Raw, whitened anchor-residual monitor. These are flags, not an error
     * attribution, variance inflation or a certificate for old nonlinear data.
     * A flagged event is still retained once in the likelihood.
     */
    uint64_t last_event_samples, residual_flagged_events;
    double last_event_anchor_rms_sigma, max_event_anchor_rms_sigma;
} scm_evidence;

typedef struct {
    scm_evidence staged;
    scm_model_row model_row;
    double row[SCM_EVIDENCE_AUG], jac_theta[SCM_MAX_THETA];
} scm_evidence_workspace;

/* row<=column<17. Return SIZE_MAX for invalid indices. */
size_t scm_evidence_packed_index(size_t row,size_t column);

/* Inputs must use the reference's declared parameter supports. Numerical
 * physical-bound tolerance is 1e-12 in the stored parameter units; no clipping.
 * scale must be positive, radius nonnegative, sigma/residual limit positive,
 * event cap > 0.
 * Init starts at sample_index=0. Failure leaves the destination unchanged.
 */
int scm_evidence_init(scm_evidence*,const scm_evidence_config*);

/* Each observation is consumed once; current and actual dt are propagated
 * before its endpoint voltage is used. Workspace must not alias any argument.
 * A failed push or seal leaves the bank byte-for-byte unchanged.
 */
int scm_evidence_push(scm_evidence*,
                     const unsigned char source_id[SCM_EVIDENCE_SOURCE_BYTES],
                     uint64_t sample_index,const scm_sample*,
                     scm_evidence_workspace*);
int scm_evidence_seal(scm_evidence*,scm_evidence_workspace*);

/* Read-only combined history+current-event snapshot. Output/workspace must
 * not alias the bank or each other. Does not create an additional prior.
 */
int scm_evidence_snapshot(const scm_evidence*,scm_evidence_factor*,
                         scm_evidence_workspace*);

double scm_evidence_factor_cost(const scm_evidence_factor*,const double *delta_scaled);
/* Anchor residual RMS in sigma units, including orthogonal residuals.
 * An empty factor returns zero; the sample count distinguishes no evidence.
 * Apply to bank.event to inspect the as-yet-unsealed partial event.
 */
double scm_evidence_factor_rms_sigma(const scm_evidence_factor*);
/* Row-major dim*dim normal matrix, gradient at delta=0 and constant objective.
 * These are undamped affine-likelihood terms, not nonlinear Hessian/covariance.
 */
int scm_evidence_factor_normal(const scm_evidence_factor*,double *normal,
                              double *gradient,double *cost_at_zero);

/* Radius is only an operating restriction; passing is NOT a nonlinear
 * remainder, likelihood coverage or identification certificate. Checks the
 * original physical supports and SOC domain over the entire carried path.
 * No candidate is silently clipped or adopted as a new chart.
 */
int scm_evidence_check_candidate(const scm_evidence*,const double *delta_scaled);

#ifdef __cplusplus
}
#endif
#endif
