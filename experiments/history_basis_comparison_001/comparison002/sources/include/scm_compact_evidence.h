#ifndef SCM_COMPACT_EVIDENCE_H
#define SCM_COMPACT_EVIDENCE_H

/* Compact storage for the same frozen affine chart and two-factor QR grouping
 * as scm_evidence. This remains a host double/libm reference, not a lifetime
 * arithmetic certificate or an autonomous nonlinear learner.
 *
 * The configuration and its OCV arrays are immutable, caller-owned and must
 * outlive every bank and operation. The config pointer is not a checkpoint;
 * durable recovery must serialize content/identity and restore the binding.
 * No bank, workspace, sample, output or configuration object may overlap.
 */
#include "scm_evidence.h"
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_COMPACT_EVIDENCE_METADATA_FIELDS \
    uint64_t first_index, next_index, active_begin, events_completed; \
    unsigned excitation; \
    int has_last; \
    double last_current, last_dt; \
    double charge_min_Ah, charge_max_Ah; \
    uint64_t last_event_samples, residual_flagged_events; \
    double last_event_anchor_rms_sigma, max_event_anchor_rms_sigma

typedef struct {
    SCM_COMPACT_EVIDENCE_METADATA_FIELDS;
} scm_compact_evidence_metadata;

typedef struct {
    const scm_evidence_config *config;
    scm_model_state model;
    scm_evidence_factor history, event;
    SCM_COMPACT_EVIDENCE_METADATA_FIELDS;
} scm_compact_evidence;
#undef SCM_COMPACT_EVIDENCE_METADATA_FIELDS

typedef struct {
    scm_evidence_factor trial;
    scm_model_state model;
    scm_compact_evidence_metadata metadata;
    double row[SCM_EVIDENCE_AUG];
} scm_compact_evidence_workspace;

/* Same domain/order/error semantics as scm_evidence. All failed init, push
 * and seal calls leave the destination bank byte-for-byte unchanged.
 */
int scm_compact_evidence_init(scm_compact_evidence*,const scm_evidence_config*);
int scm_compact_evidence_push(scm_compact_evidence*,
    const unsigned char source_id[SCM_EVIDENCE_SOURCE_BYTES],uint64_t sample_index,
    const scm_sample*,scm_compact_evidence_workspace*);
int scm_compact_evidence_seal(scm_compact_evidence*,scm_compact_evidence_workspace*);
int scm_compact_evidence_snapshot(const scm_compact_evidence*,scm_evidence_factor*,
    scm_compact_evidence_workspace*);
/* Scratch-oriented snapshot for a serialized diagnostic phase. The bank is
 * read-only; unlike snapshot above, output may be changed on failure. Output
 * and the 17-double row are separate and must not alias the bank/config.
 */
int scm_compact_evidence_snapshot_into(const scm_compact_evidence*,
    scm_evidence_factor*,double row[SCM_EVIDENCE_AUG]);
int scm_compact_evidence_check_candidate(const scm_compact_evidence*,const double*);

#ifdef __cplusplus
}
#endif
#endif
