#ifndef SCM_COMPACT_ASSESS_H
#define SCM_COMPACT_ASSESS_H

/* Two-target local diagnostics of the complete joint fixed-chart likelihood.
 * Every nuisance/entering-state direction is retained in the eigensystem;
 * only current SOC and capacity are reported. Other targets are unassessed.
 * This API does not produce a joint update, posterior, validated coverage or
 * a nonlinear convergence result. A caller must supply optimizer_status != 0
 * when no nonlinear fit was performed, as in the original bounded probe.
 */
#include "scm_assess.h"
#include "scm_compact_evidence.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int modes, joint_dimension, numerical_rank;
    int matrix_invalid, eigen_converged, coordinate_chart_supported;
    int optimizer_status, active_constraints;
    double eigen_cutoff;
    scm_assess_target current_soc, capacity_Q_Ah;
} scm_compact_assessment;

typedef struct {
    union {
        scm_evidence_factor snapshot;
        double matrix[SCM_MAX_PARAMETERS*SCM_MAX_PARAMETERS];
    } factor_matrix;
    union {
        double qrrow[SCM_EVIDENCE_AUG];
        double target_projection[2*SCM_MAX_PARAMETERS];
    } row_projection;
    /* Sorted eigenvalues remain available until this workspace is reused. */
    double eigenvalues[SCM_MAX_PARAMETERS];
} scm_compact_assess_workspace;

/* All arguments and backing configuration must be disjoint. The bank is
 * read-only. The workspace is scratch and can share storage with ingestion
 * workspace only when the phases do not overlap. On a negative return the
 * output/workspace must not be interpreted as an assessment.
 *
 * options == NULL selects scm_assess defaults. The caller supplies the sum of
 * active linear/outer constraints; no optimization is performed here. Target
 * ranges use the original unlinked entering-state chart, and linked-chart or
 * unconverged inputs retain their explicit unresolved qualification. The Gram
 * is symmetric by construction; its eigensystem uses all 3*modes+7 coordinates.
 * Returns 0 on a completed assessment (including unresolved/invalid results),
 * or -1 on invalid/nonfinite input or snapshot failure. No heap allocation.
 */
int scm_compact_assess(const scm_compact_evidence *bank,int optimizer_status,
    int active_constraints,const scm_assess_options *options,
    scm_compact_assessment *output,scm_compact_assess_workspace *workspace);

#ifdef __cplusplus
}
#endif
#endif
