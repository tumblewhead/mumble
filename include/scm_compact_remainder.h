#ifndef SCM_COMPACT_REMAINDER_H
#define SCM_COMPACT_REMAINDER_H

/* Compact adaptation of scm_remainder: one immutable caller-owned config
 * is shared with the paired evidence bank. Config and OCV storage must outlive
 * both banks and remain unchanged. Pointers are not checkpoint encodings.
 * All coefficients, audit fields and chronology are retained.
 *
 * Sparse full-joint Taylor remainder envelope for the smooth illustrative
 * OCV only. The mathematics bounds the real-arithmetic model on one immutable
 * rectangular chart. This C double/libm evaluation does NOT use validated
 * outward rounding and is not a formal machine certificate. It does not
 * supply a posterior, calibrated coverage, or a relinearization mechanism.
 */
#include "scm_compact_evidence.h"
#include "scm_remainder.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const scm_evidence_config *config;
    /* Nonempty query eligibility requires exclusive paired ancestry with this
     * exact evidence object. No rebinding or shallow-copy continuation after
     * ingestion; caller-owned public structs must not be mutated externally.
     */
    const scm_compact_evidence *bound_evidence;
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
} scm_compact_remainder;

typedef struct { scm_compact_remainder staged; } scm_compact_remainder_workspace;

int scm_compact_remainder_init(scm_compact_remainder*,const scm_evidence_config*);
/* Atomic independently, for envelope audits only. Any successful independent
 * push permanently invalidates query eligibility until this bank is reinit'd.
 * Callers constructing inference evidence must use the paired helper.
 * Voltage is checked for finiteness but never used to construct the bound.
 */
int scm_compact_remainder_push(scm_compact_remainder*,
                       const unsigned char source_id[SCM_EVIDENCE_SOURCE_BYTES],
                       uint64_t sample_index,const scm_sample*,
                       scm_compact_remainder_workspace*);
/* Stage remainder, then advance atomic evidence, then commit remainder. Both
 * banks stay unchanged on any failure. The first success binds two empty
 * banks; subsequent updates require the same evidence object and exclusively
 * paired ancestry as well as matching config/count/time/charge. Source identity
 * must denote immutable ordered content. Distinct bank/workspace objects are
 * required. No evidence gets added twice. Do not shallow-copy or rebind banks
 * to continue ingestion after the binding has been established.
 */
int scm_compact_remainder_evidence_push(scm_compact_evidence*,scm_compact_remainder*,
                               const unsigned char source_id[SCM_EVIDENCE_SOURCE_BYTES],
                               uint64_t sample_index,const scm_sample*,
                               scm_compact_evidence_workspace*,scm_compact_remainder_workspace*);

/* Uses the matched bank's disjoint history/event factors directly, preserving
 * the whole residual constant without an untagged factor or new snapshot.
 * A nonnegative budget is an external engineering restriction. Each query
 * refers to the SAME original chart; substeps do not renew its bound/budget.
 * Valid outside-domain/over-budget evaluations return OK with explicit status.
 * Argument/mismatch/nonfinite errors return negative with status unavailable.
 */
int scm_compact_remainder_query(const scm_compact_remainder*,const scm_compact_evidence*,
                        const double *delta_scaled,double budget,
                        scm_remainder_result*);

#ifdef __cplusplus
}
#endif
#endif
