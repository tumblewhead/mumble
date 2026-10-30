#ifndef SCM_ESTIMATOR_H
#define SCM_ESTIMATOR_H
#include "scm_model.h"
#define SCM_MAX_PARAMETERS (SCM_MAX_THETA+SCM_MAX_ALPHA)
typedef enum {SCM_FULL=0,SCM_TANGENT=1,SCM_HYBRID=2} scm_method;
typedef struct scm_problem scm_problem;
typedef struct {
    int starts,max_iterations,has_initial;
    double initial_theta[SCM_MAX_THETA];
    unsigned fixed_mask;
    double fixed_theta[SCM_MAX_THETA];
    unsigned fixed_alpha_mask;
    double fixed_alpha[SCM_MAX_ALPHA];
    int has_current_soc;
    double current_soc;
} scm_fit_options;
typedef struct {
    double theta[SCM_MAX_THETA],alpha[SCM_MAX_ALPHA];
    double objective,objective_full,voltage_rmse,elapsed_cpu_s;
    double projected_gradient,max_inner_kkt;
    int status,termination_reason,iterations,evaluations,converged_starts,starts;
    int active_linear_constraints,active_outer_bounds;
    size_t samples,features,blocks,data_bytes,basis_bytes,payload_bytes,workspace_bytes;
    size_t retained_bytes,setup_peak_bytes;
    double basis_seconds,basis_max_orthogonality,max_discarded_column_norm;
    /* Diagnostic likelihood Jacobian Gram matrix, before damping or Schur
       reduction. Coordinates: scaled theta, scaled alpha. Not a posterior. */
    double joint_normal[SCM_MAX_PARAMETERS*SCM_MAX_PARAMETERS];
    double coordinate_scales[SCM_MAX_PARAMETERS];
    unsigned unexcited_theta_mask;
    double elapsed_physical_s,charge_Ah;
} scm_fit_result;
scm_problem *scm_problem_create(const scm_sample*,size_t,int,double,const scm_ocv*,scm_method);
void scm_problem_destroy(scm_problem*);
void scm_fit_options_default(scm_fit_options*);
int scm_fit(scm_problem*,const scm_fit_options*,scm_fit_result*);
const char *scm_method_name(scm_method);
void scm_default_theta(int,int,double*);
void scm_theta_bounds(int,double*,double*);
#endif
