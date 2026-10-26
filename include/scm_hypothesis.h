#ifndef SCM_HYPOTHESIS_H
#define SCM_HYPOTHESIS_H

/* Two retained local Gaussian alternatives. Each component has its own full
 * joint covariance and nonlinear current state. This is not an exact retained
 * nonlinear likelihood, physical support or validated uncertainty coverage.
 * All APIs are serialized; live, workspace, input and output must be disjoint.
 * The acquisition ISR owns a separate input ring and cannot read this bank
 * during a commit. No function allocates memory or retains raw observations.
 */
#include "scm_online.h" /* Existing coordinate, status and configuration types. */

#ifdef __cplusplus
extern "C" {
#endif

#define SCM_HYPOTHESIS_DIM SCM_ONLINE_DIM
#define SCM_HYPOTHESIS_COMPONENTS 2u
#define SCM_HYPOTHESIS_FACTOR_ENTRIES 136u
#define SCM_HYPOTHESIS_MODEL_VERSION 1u
#define SCM_HYPOTHESIS_AGGREGATE (-1)
#define SCM_HYPOTHESIS_NO_COMPONENT UINT32_MAX
#define SCM_HYPOTHESIS_FACTOR_INDEX(i,j) ((size_t)(i)*((size_t)(i)+1u)/2u+(size_t)(j))
#define SCM_HYPOTHESIS_ACCURACY_QUALIFICATION "unresolved"
#define SCM_HYPOTHESIS_COVERAGE_QUALIFICATION "unvalidated"

typedef scm_online_config scm_hypothesis_config;
typedef enum {
    SCM_HYPOTHESIS_COINCIDENT=0,
    SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT=1
} scm_hypothesis_mode;
enum {
    SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT=1u<<0,
    SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE=1u<<1
};
typedef enum {
    SCM_HYPOTHESIS_REJECT_NONE=0,
    SCM_HYPOTHESIS_REJECT_PREDICTION=1,
    SCM_HYPOTHESIS_REJECT_OBSERVATION=2,
    SCM_HYPOTHESIS_REJECT_PROJECTION=3,
    SCM_HYPOTHESIS_REJECT_INNOVATION_SD=4,
    SCM_HYPOTHESIS_REJECT_GAIN=5,
    SCM_HYPOTHESIS_REJECT_MEAN=6,
    SCM_HYPOTHESIS_REJECT_COVARIANCE=7,
    SCM_HYPOTHESIS_REJECT_LIKELIHOOD=8,
    SCM_HYPOTHESIS_REJECT_WEIGHTS=9,
    SCM_HYPOTHESIS_REJECT_COMPONENT_VALIDATION=10,
    SCM_HYPOTHESIS_REJECT_BANK_VALIDATION=11,
    SCM_HYPOTHESIS_REJECT_REGENERATION=12
} scm_hypothesis_rejection_stage;

/* Same fields as the preserved scm_online component; only the lower factor
 * is packed by row. Exactly 1464 bytes on the audited binary64 host ABI.
 * Public fields support inspection/codecs, not unvalidated live mutation. */
typedef struct {
    scm_hypothesis_config config;
    double mean[SCM_HYPOTHESIS_DIM];
    double factor[SCM_HYPOTHESIS_FACTOR_ENTRIES];
    uint64_t epoch_begin, next_index, evidence_next_index;
    uint64_t prediction_count, voltage_count, missing_voltage_count;
    uint64_t rejected_voltage_count, limited_gain_count, zero_gain_count;
    uint64_t cold_resets;
    double elapsed_s, epoch_elapsed_s;
    double last_current_A, last_prediction_V, last_innovation_V;
    double last_innovation_variance_V2, last_gain_scale, minimum_gain_scale;
    double last_max_gain_scale;
    unsigned last_limited_mask, last_blocked_mask;
    double innovation_ewma;
    unsigned flags, excitation;
    int initialized, has_voltage, prediction_valid;
} scm_hypothesis_component;

typedef struct {
    uint64_t generation, bank_evidence_next_index;
    uint32_t flags, active_components;
    uint32_t last_rejection_stage, last_rejection_component;
} scm_hypothesis_header;

typedef struct {
    scm_hypothesis_component component[SCM_HYPOTHESIS_COMPONENTS];
    double log_weight[SCM_HYPOTHESIS_COMPONENTS];
    scm_hypothesis_header header;
} scm_hypothesis;

typedef struct {
    scm_hypothesis staged;
    double observation_gradient[SCM_HYPOTHESIS_DIM];
    double projected_gradient[SCM_HYPOTHESIS_DIM];
    double covariance_gradient[SCM_HYPOTHESIS_DIM];
    double correction[SCM_HYPOTHESIS_DIM];
    /* Scratch outputs from the latest attempted correction. Not evidence
     * state; callers may stream these diagnostically after ingest returns. */
    double pre_correction_log_likelihood[SCM_HYPOTHESIS_COMPONENTS];
} scm_hypothesis_workspace;

/* Local status/precision fields remain research diagnostics. Application
 * SOC/Q accuracy is uniformly unresolved (the macro above), independent of
 * these local widths. The aggregate capacity point is exp(weighted logQ),
 * not a physical-space mixture expectation or a mixture median. */
typedef struct {
    uint64_t epoch_begin, next_index, evidence_next_index, evidence_age_samples;
    uint64_t prediction_count, voltage_count, missing_voltage_count;
    uint64_t rejected_voltage_count, cold_resets;
    double elapsed_s, epoch_elapsed_s;
    double mean[SCM_HYPOTHESIS_DIM], coordinate_sd[SCM_HYPOTHESIS_DIM];
    double current_soc, capacity_Ah, predicted_voltage_V;
    double soc_local_lower, soc_local_upper;
    double capacity_local_lower_Ah, capacity_local_upper_Ah;
    int point_available, capacity_available, prediction_available, local_ranges_available;
    unsigned flags, excitation;
    scm_online_status soc_status, capacity_status;
    int soc_local_precision_hard, capacity_local_precision_hard;
    int soc_local_precision_preferred, capacity_local_precision_preferred;
} scm_hypothesis_aggregate_query;

typedef struct {
    union {
        scm_online_query_result component;
        scm_hypothesis_aggregate_query aggregate;
    } view;
    double log_weight[SCM_HYPOTHESIS_COMPONENTS];
    uint32_t component_flags[SCM_HYPOTHESIS_COMPONENTS];
    /* SOC lower, SOC upper, Q lower, Q upper; both components are included
     * regardless of their weights or conditional has_voltage flags. NAN
     * denotes a nonfinite local range. This is not a hard-support hull. */
    double all_component_soc_capacity_hull[4];
} scm_hypothesis_query_result;

/* Return codes and per-component flags retain the SCM_ONLINE_* values.
 * Helpers are implemented here; linking the old online core is unnecessary. */
void scm_hypothesis_config_default(scm_hypothesis_config*);
int scm_hypothesis_config_valid(const scm_hypothesis_config*);
int scm_hypothesis_config_equal(const scm_hypothesis_config*,const scm_hypothesis_config*);
void scm_hypothesis_bounds(double lower[SCM_HYPOTHESIS_DIM],double upper[SCM_HYPOTHESIS_DIM]);
int scm_hypothesis_component_validate(const scm_hypothesis_component*);
int scm_hypothesis_validate(const scm_hypothesis*);
int scm_hypothesis_init(scm_hypothesis*,const scm_hypothesis_config*,scm_hypothesis_mode);

/* Negative return leaves live bytes unchanged. ACCEPTED_RECOVERY consumes the
 * known interval once and retains the old belief, which is no longer current.
 * A rejected voltage commits both valid physical predictions and old weights.
 * Every successful conditional mean uses exactly its full Joseph gain.
 * All-zero gains restore the predicted mean/factor bytes from immutable old
 * arrays through the same prediction operation, without another state object.
 * At most six predictions, two corrections and two likelihoods per delivery.
 */
int scm_hypothesis_ingest(scm_hypothesis*,const unsigned char source_id[SCM_ONLINE_SOURCE_BYTES],
    uint64_t sample_index,const scm_sample*,int voltage_present,scm_hypothesis_workspace*);

/* selector=-1: aggregate; selector=0 or1: conditional legacy-shaped query.
 * One result arena is reused serially; this never changes inference state. */
int scm_hypothesis_query(const scm_hypothesis*,int selector,scm_hypothesis_query_result*);
int scm_hypothesis_mark_unknown_gap(scm_hypothesis*);
int scm_hypothesis_cold_reset(scm_hypothesis*);
const char *scm_hypothesis_status_name(scm_online_status);
const char *scm_hypothesis_rejection_stage_name(uint32_t);

#ifdef __cplusplus
}
#endif
#endif
