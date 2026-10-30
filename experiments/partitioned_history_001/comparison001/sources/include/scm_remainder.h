#ifndef SCM_REMAINDER_H
#define SCM_REMAINDER_H

/* Sparse full-joint Taylor remainder envelope for the smooth illustrative
 * OCV only. The mathematics bounds the real-arithmetic model on one immutable
 * rectangular chart. This C double/libm evaluation does NOT use validated
 * outward rounding and is not a formal machine certificate. It does not
 * supply a posterior, calibrated coverage, or a relinearization mechanism.
 */
#include "scm_evidence.h"
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_REMAINDER_MAX_PAIRS (3*SCM_MAX_MODES+10)
enum {
    SCM_REMAINDER_OK=0,
    SCM_REMAINDER_ERR_ARGUMENT=-30,
    SCM_REMAINDER_ERR_UNSUPPORTED=-31,
    SCM_REMAINDER_ERR_SOURCE=-32,
    SCM_REMAINDER_ERR_ORDER=-33,
    SCM_REMAINDER_ERR_NONFINITE=-34,
    SCM_REMAINDER_ERR_DOMAIN=-35,
    SCM_REMAINDER_ERR_OVERFLOW=-36,
    SCM_REMAINDER_ERR_MISMATCH=-37
};
typedef enum {
    SCM_REMAINDER_UNAVAILABLE=0,
    SCM_REMAINDER_OUTSIDE_DOMAIN=1,
    SCM_REMAINDER_EXCEEDS_BUDGET=2,
    SCM_REMAINDER_WITHIN_ANALYTIC_BUDGET=3
} scm_remainder_status;

typedef struct {
    scm_evidence_config config;
    /* Nonempty query eligibility requires exclusive paired ancestry with this
     * exact evidence object. No rebinding or shallow-copy continuation after
     * ingestion; caller-owned public structs must not be mutated externally.
     */
    const scm_evidence *bound_evidence;
    int paired_ancestry;
    uint64_t next_index;
    int dim, pair_count;
    unsigned char pair_row[SCM_REMAINDER_MAX_PAIRS];
    unsigned char pair_column[SCM_REMAINDER_MAX_PAIRS];
    /* C is RSS across observations of whitened, scaled Hessian bounds.
     * last_bound is the last observation's bound, for numerical audits.
     */
    double coefficient[SCM_REMAINDER_MAX_PAIRS];
    double last_bound[SCM_REMAINDER_MAX_PAIRS];
    double tau_lo[SCM_MAX_MODES],tau_hi[SCM_MAX_MODES];
    double gamma_lo[2],gamma_hi[2],Q_lo;
    double R_abs_max[SCM_MAX_MODES],v_abs_max[SCM_MAX_MODES];
    double H_abs_max,u_abs_max;
    double f_lo[SCM_MAX_MODES],f_hi[SCM_MAX_MODES];
    double f_first[SCM_MAX_MODES],f_second[SCM_MAX_MODES];
    double hb_lo,hb_hi,hb_first[2],hb_second[3];
    double throughput_Ah[2];
    double elapsed,charge_Ah,charge_min_Ah,charge_max_Ah;
} scm_remainder;

typedef struct { scm_remainder staged; } scm_remainder_workspace;

typedef struct {
    scm_remainder_status status;
    int arithmetic_validated; /* Always 0 for this implementation. */
    int domain_code;
    double affine_nll;
    double whitened_prediction_error_bound;
    double nll_error_bound,budget;
} scm_remainder_result;

int scm_remainder_init(scm_remainder*,const scm_evidence_config*);
/* Atomic independently, for envelope audits only. Any successful independent
 * push permanently invalidates query eligibility until this bank is reinit'd.
 * Callers constructing inference evidence must use the paired helper.
 * Voltage is checked for finiteness but never used to construct the bound.
 */
int scm_remainder_push(scm_remainder*,
                       const unsigned char source_id[SCM_EVIDENCE_SOURCE_BYTES],
                       uint64_t sample_index,const scm_sample*,
                       scm_remainder_workspace*);
/* Stage remainder, then advance atomic evidence, then commit remainder. Both
 * banks stay unchanged on any failure. The first success binds two empty
 * banks; subsequent updates require the same evidence object and exclusively
 * paired ancestry as well as matching config/count/time/charge. Source identity
 * must denote immutable ordered content. Distinct bank/workspace objects are
 * required. No evidence gets added twice. Do not shallow-copy or rebind banks
 * to continue ingestion after the binding has been established.
 */
int scm_remainder_evidence_push(scm_evidence*,scm_remainder*,
                               const unsigned char source_id[SCM_EVIDENCE_SOURCE_BYTES],
                               uint64_t sample_index,const scm_sample*,
                               scm_evidence_workspace*,scm_remainder_workspace*);

/* Uses the matched bank's disjoint history/event factors directly, preserving
 * the whole residual constant without an untagged factor or new snapshot.
 * A nonnegative budget is an external engineering restriction. Each query
 * refers to the SAME original chart; substeps do not renew its bound/budget.
 * Valid outside-domain/over-budget evaluations return OK with explicit status.
 * Argument/mismatch/nonfinite errors return negative with status unavailable.
 */
int scm_remainder_query(const scm_remainder*,const scm_evidence*,
                        const double *delta_scaled,double budget,
                        scm_remainder_result*);
const char *scm_remainder_status_name(scm_remainder_status);

#ifdef __cplusplus
}
#endif
#endif
