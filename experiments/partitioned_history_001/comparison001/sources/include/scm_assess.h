#ifndef SCM_ASSESS_H
#define SCM_ASSESS_H
/* Allocation-free local likelihood reporting, C99 double precision.
 * No posterior, confidence-coverage certificate, prior precision, or optimizer
 * update is produced. Unavailable target directions retain declared support.
 * The caller owns both output and workspace. Explicit physical bounds below
 * match the current reconstructed estimator, not an arbitrary future version.
 */
#include "scm_estimator.h"
#include <stddef.h>
#define SCM_ASSESS_MAX_TARGETS (SCM_MAX_PARAMETERS+2)

typedef enum {
    SCM_ASSESS_UNRESOLVED=0,
    SCM_ASSESS_UNEXCITED=1,
    SCM_ASSESS_PROVISIONAL=2
} scm_assess_status;

enum {
    SCM_ASSESS_REASON_HYSTERESIS=1u<<0,
    SCM_ASSESS_REASON_INDEFINITE=1u<<1,
    SCM_ASSESS_REASON_ASYMMETRIC=1u<<2,
    SCM_ASSESS_REASON_UNEXCITED=1u<<3,
    SCM_ASSESS_REASON_NULL_SPACE=1u<<4,
    SCM_ASSESS_REASON_NUMERICAL_RANGE=1u<<5,
    SCM_ASSESS_REASON_PRECISION=1u<<6,
    SCM_ASSESS_REASON_OPTIMIZER=1u<<7,
    SCM_ASSESS_REASON_ACTIVE_CONSTRAINT=1u<<8,
    SCM_ASSESS_REASON_CONDITIONED=1u<<9,
    SCM_ASSESS_REASON_SUPPORT_CROSSING=1u<<10,
    SCM_ASSESS_REASON_EIGEN_NONCONVERGENCE=1u<<11,
    SCM_ASSESS_REASON_LINKED_CHART=1u<<12
};

typedef struct {
    double relative_halfwidth;       /* default .10 */
    double soc_halfwidth;            /* default .05 SOC fraction */
    double eigen_rtol;               /* default 1e-10 */
    double null_projection_tol;      /* default 1e-8 */
    double sigma_multiplier;         /* default 2 */
    double hysteresis_amplitude_floor_V; /* default 1e-8 */
    int conditioned_fit;             /* supplied fixed coordinates disclosed */
    int linked_current_soc_chart;    /* all target ranges unresolved */
} scm_assess_options;

typedef struct {
    const char *name;
    const char *units;
    double point, lower, upper;
    double support_lower, support_upper;
    double null_projection;
    double local_standard_deviation, local_halfwidth, relative_halfwidth;
    scm_assess_status status;
    unsigned reasons;
    int point_available;
    int has_local_range;
    int has_relative_halfwidth;
    int passes_local_precision;      /* -1: no target threshold; 0: no; 1: yes */
    int eligible_for_profile_check;
    int active_constraints_present;
    int conditioned_fit;
} scm_assess_target;

typedef struct {
    int modes, joint_dimension, target_count, numerical_rank;
    int matrix_invalid, eigen_converged, coordinate_chart_supported;
    int optimizer_status, active_constraints;
    double eigenvalues[SCM_MAX_PARAMETERS];
    double eigen_cutoff, matrix_relative_asymmetry;
    scm_assess_target targets[SCM_ASSESS_MAX_TARGETS];
} scm_assessment;

typedef struct {
    double matrix[SCM_MAX_PARAMETERS*SCM_MAX_PARAMETERS];
    double vectors[SCM_MAX_PARAMETERS*SCM_MAX_PARAMETERS];
    double gradient[SCM_MAX_PARAMETERS];
} scm_assess_workspace;

void scm_assess_options_default(scm_assess_options *options);
const char *scm_assess_status_name(scm_assess_status status);
/* Packed np*np Gram matrix, np=3*modes+7, in fit->joint_normal; scales obey
 * physical/transformed x = x_hat + scale*delta. The Gram is already whitened.
 * Target order: physical theta coordinates, physical alpha coordinates,
 * current_soc, h0. No local interval is clipped to its physical support.
 *
 * options==NULL selects defaults. linked_current_soc_chart must be set for
 * fits using --fixed-current-soc: that Gram is in a different coordinate chart
 * and cannot be reinterpreted as unrestricted SOC covariance.
 * Returns0 on completed assessment, including untrusted matrices/optimizer
 * results, or -1 for invalid arguments/nonfinite input. No heap allocation.
 */
int scm_assess(const scm_fit_result *fit,int modes,const scm_assess_options *options,
               scm_assessment *output,scm_assess_workspace *workspace);
#endif
