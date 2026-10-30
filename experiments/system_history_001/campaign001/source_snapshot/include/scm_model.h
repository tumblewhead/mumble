#ifndef SCM_MODEL_H
#define SCM_MODEL_H

/* Reconstructed and extended research core, not asserted byte-identical to the
 * lost implementation. C99, allocation-free, fixed 25 C reference temperature.
 * Units: A, s, Ah, ohm, V. Positive I discharges. Point voltage is observed at
 * the END of each piecewise-constant current interval; dt=0 is permitted.
 */
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

#define SCM_MAX_MODES 3
#define SCM_MAX_THETA 7
#define SCM_MAX_ALPHA 9
enum { SCM_OK=0, SCM_ERR_ARGUMENT=-1, SCM_ERR_DOMAIN=-2, SCM_ERR_NONFINITE=-3 };
typedef struct { double dt, current, voltage; } scm_sample;

/* NULL or n=0 selects illustrative (NOT measured) U=3+1.15*z+
 * .08*tanh(8*(z-.5)). Otherwise the caller owns a monotone PWL table. Validate
 * once before use. Queries must be covered by both [0,1] and the table;
 * no clipping or extrapolation. At interior knots the right slope is used.
 */
typedef struct { size_t n; const double *z, *u; } scm_ocv;

/* theta = log(tau_i),log(gamma_plus),log(gamma_minus),z0,log(Q_Ah).
 * alpha = R0,R_i,H,v_i0,u0=H*h0.
 * Indices: R0=0; R_i=1+i; H=1+n; v_i0=2+n+i; u0=2+2*n.
 * The solver must enforce R0,R_i,H>=0, |u0|<=H and its stated v_i0 support.
 * A candidate's parameters and entering states are shared over its full path.
 */
typedef struct {
    int modes;
    double theta[SCM_MAX_THETA];
    double tau[SCM_MAX_MODES], gamma[2], Q, z0;
    double charge_Ah, elapsed;
    double f[SCM_MAX_MODES], a[SCM_MAX_MODES];
    double df[SCM_MAX_MODES], da[SCM_MAX_MODES];
    double hb, ha, dhb[2], dha[2];
} scm_model_state;
typedef struct {
    double ocv, z;
    double X[SCM_MAX_ALPHA];
    double docv[SCM_MAX_THETA];
    double dX[SCM_MAX_THETA][SCM_MAX_ALPHA];
} scm_model_row;

int scm_model_ntheta(int modes);
int scm_model_nalpha(int modes);
int scm_ocv_validate(const scm_ocv *curve);
int scm_ocv_eval(const scm_ocv *curve,double z,double *value,double *slope);
int scm_model_init(scm_model_state *state,int modes,const double *theta);
/* Failure leaves the carried state unchanged. */
int scm_model_step(scm_model_state *state,const scm_ocv *curve,
                   double dt,double current,scm_model_row *row);
int scm_model_predict(const scm_model_row *row,int modes,const double *alpha,
                      double *mu,double *jac_theta);

typedef struct {
    int modes;
    double R0, R[SCM_MAX_MODES], tau[SCM_MAX_MODES];
    double H, gamma_plus, gamma_minus, Q;
} scm_physical;
typedef struct { double z, v[SCM_MAX_MODES], h; } scm_physical_state;
int scm_physical_step(const scm_physical *p,scm_physical_state *state,
                      const scm_ocv *curve,double dt,double current,
                      double *voltage);
#ifdef __cplusplus
}
#endif
#endif
