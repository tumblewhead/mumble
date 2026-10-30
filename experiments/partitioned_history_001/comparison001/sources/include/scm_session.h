#ifndef SCM_SESSION_H
#define SCM_SESSION_H

/* Desktop retained-history lifecycle around the preserved SCM_FULL reference.
 * Dynamic history and replay work are intentional. This is not the compact
 * backend, a coverage certificate, or qualified Cortex-M23 firmware.
 * Public structs describe persistence state, but callers must use the API to
 * mutate live sessions. Initialize fresh/zero storage; destroy before reuse.
 */
#include "scm_assess.h"
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_SESSION_SOURCE_BYTES 32
#define SCM_SESSION_MAX_CHECKPOINTS 8
#define SCM_SESSION_MODEL_VERSION 1u
enum {
    SCM_SESSION_OK=0,
    SCM_SESSION_ERR_ARGUMENT=-60, SCM_SESSION_ERR_ORDER=-61,
    SCM_SESSION_ERR_SOURCE=-62, SCM_SESSION_ERR_NONFINITE=-63,
    SCM_SESSION_ERR_OVERFLOW=-64, SCM_SESSION_ERR_ALLOCATION=-65,
    SCM_SESSION_ERR_RECOVERY_REQUIRED=-66, SCM_SESSION_ERR_NOT_DUE=-67,
    SCM_SESSION_ERR_MISSING_VOLTAGE=-68, SCM_SESSION_ERR_FIT=-69,
    SCM_SESSION_ERR_STATE=-70, SCM_SESSION_ERR_UNSUPPORTED=-71
};
enum {
    SCM_SESSION_FLAG_HISTORY_LOST=1u<<0,
    SCM_SESSION_FLAG_MISSING_VOLTAGE=1u<<1,
    SCM_SESSION_FLAG_RECOVERY_REQUIRED=1u<<2,
    SCM_SESSION_FLAG_FIT_FAILED=1u<<3,
    SCM_SESSION_FLAG_MODEL_UNAVAILABLE=1u<<4
};
typedef enum {
    SCM_SESSION_COLLECTING=0, SCM_SESSION_TRACKING=1,
    SCM_SESSION_RECOVERY_REQUIRED=2, SCM_SESSION_POINT_UNAVAILABLE=3
} scm_session_status;

typedef struct {
    unsigned char source_id[SCM_SESSION_SOURCE_BYTES];
    int modes, starts, max_iterations;
    double sigma;
    uint64_t max_history_samples;
    unsigned schedule_count;
    uint64_t fit_checkpoints[SCM_SESSION_MAX_CHECKPOINTS];
} scm_session_config;

typedef struct {
    scm_session_config config;
    scm_sample *samples;
    unsigned char *voltage_present;
    size_t count, capacity;
    uint64_t epoch_begin, next_index, cold_resets;
    uint64_t fit_attempts, fit_results, last_fit_next_index, last_fit_attempt_index;
    unsigned schedule_cursor, flags;
    int initialized, has_fit, model_valid, last_fit_code, prediction_valid;
    double epoch_start_elapsed_s, elapsed_total_s, epoch_elapsed_s, epoch_charge_Ah;
    scm_fit_result fit;
    scm_model_state model;
    double predicted_voltage_V;
    /* Requested storage counters, preserved with capacity by checkpoint v1.
     * peak_owned includes old+new buffers during journal growth. Successful
     * fit peaks add the full problem's auxiliary heap once; failed-fit heap,
     * allocator overhead, fixed stack and caller/runtime costs are excluded. */
    size_t peak_owned_bytes, last_problem_auxiliary_bytes, peak_fit_owned_bytes;
} scm_session;

typedef struct {
    scm_session_status status;
    unsigned flags;
    uint64_t epoch_begin, next_index, evidence_next_index, evidence_age_samples;
    uint64_t cold_resets, fit_attempts, fit_results, last_fit_attempt_index;
    double elapsed_s, epoch_elapsed_s, epoch_charge_Ah;
    double current_soc, capacity_Ah, predicted_voltage_V;
    int point_available, capacity_available, voltage_prediction_available;
    int assessment_available, optimizer_status, last_fit_code;
    int fit_due, fitting_available, evidence_current;
    size_t history_samples, history_capacity, owned_bytes;
    size_t peak_owned_bytes, last_problem_auxiliary_bytes, peak_fit_owned_bytes;
} scm_session_query_result;

void scm_session_config_default(scm_session_config*);
int scm_session_config_valid(const scm_session_config*);
int scm_session_config_equal(const scm_session_config*,const scm_session_config*);
int scm_session_init(scm_session*,const scm_session_config*);
void scm_session_destroy(scm_session*);

/* A rejected ingest leaves the session and its existing journal unchanged.
 * Source identity denotes immutable ordered observations. Missing V is
 * represented by voltage_present=0 (the supplied voltage is ignored and
 * stored as 0). Known dt/current are always retained and propagated. The
 * unmodified full-history fitter cannot mask missing V: fitting is then
 * explicitly unavailable for this epoch, without deleting prior information.
 * At an unconsumed scheduled count, ingest returns ERR_NOT_DUE until fit is
 * called. This prevents silently stepping past the declared evidence point.
 */
int scm_session_ingest(scm_session*,const unsigned char source_id[SCM_SESSION_SOURCE_BYTES],
    uint64_t sample_index,const scm_sample*,int voltage_present);
int scm_session_advance(scm_session*,const unsigned char source_id[SCM_SESSION_SOURCE_BYTES],
    uint64_t sample_index,double dt,double current);

/* fit_due returns 1 only at the exact next scheduled sample count; a missed
 * checkpoint is not silently reinterpreted. fit consumes a due checkpoint,
 * executes one scm_fit call with three public starts by default, and retains
 * the previous theta only as an initialization. No posterior prior is added.
 * Operational fit failure is recorded and leaves any previous fit intact.
 * Optimizer nonconvergence remains a completed result with fit.status!=0.
 * fit_attempts counts consumed due requests, including pre-solver failures;
 * fit_results counts completed numerical results, including nonconvergence.
 * Both are cumulative across cold resets. No failed request is retried at a
 * later sample count under the name of the earlier checkpoint.
 */
int scm_session_fit_due(const scm_session*);
int scm_session_fit(scm_session*);

/* Read-only query. assessment/workspace must either both be NULL or both be
 * supplied and disjoint from the session/output. If present, assessment uses
 * the latest fitted full joint Gram and the CURRENT known charge to transport
 * the SOC target gradient. Its evidence position/age remains explicit. No
 * voltage evidence after the last fit is claimed assimilated. Before a fit,
 * after cold reset, or during recovery, local assessment is unavailable.
 * Unsupported EOD/temperature targets are not supplied by this API.
 */
int scm_session_query(const scm_session*,scm_session_query_result*,
    scm_assessment*,scm_assess_workspace*);
const char *scm_session_status_name(scm_session_status);

/* An explicitly unknown current/time gap latches recovery_required. No
 * invented input is advanced. Recovery requires a complete valid checkpoint
 * plus known replay, or an explicit cold reset at the current known position.
 */
int scm_session_mark_unknown_gap(scm_session*);
int scm_session_cold_reset(scm_session*);

/* Persistence helper: validate a prospective decoded session and reconstruct
 * the model from its complete current-epoch journal and saved last fit, with
 * no optimization. It checks journal order implied by epoch_begin/count,
 * recorded time/charge and last-fit position. Pointer/capacity ownership must
 * already be valid. It may change the prospective model; do not apply it to
 * the live destination until checkpoint validation has completed.
 */
int scm_session_rebuild(scm_session*);
size_t scm_session_owned_bytes(const scm_session*);

#ifdef __cplusplus
}
#endif
#endif
