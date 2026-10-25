/* Restricted frozen SCM_FULL comparison. The selected R/tau remain unknown.
 * Public unit transform s=2: dt'=dt/s, I'=sI, R'=R/s, tau'=tau/s.
 * Charge, attenuation, forcing and voltage predictions are unchanged.
 * Frozen solver support becomes broader than the certificate support; it is
 * not an equal-feasible-set optimizer. No generator truth enters this probe.
 */
#include "scm_estimator.h"
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_KNOTS 17
#define MAX_SAMPLES 200000

typedef struct {
    unsigned ticks_hz,soc_one,modes,knots,unknown,unit_scale;
    unsigned r0,rlo[3],rhi[3],taulo[3],tauhi[3];
    int initial_rc_nV[3];
    double z[MAX_KNOTS],v[MAX_KNOTS];
} public_model;

static int read_model(const char *path,public_model *m)
{
    FILE *f=fopen(path,"r");unsigned j;int ok=1;
    if(!f)return -1;
    memset(m,0,sizeof(*m));
    if(fscanf(f,"%u %u %u %u %u %u",&m->ticks_hz,&m->soc_one,&m->modes,
              &m->knots,&m->unknown,&m->unit_scale)!=6 || !m->ticks_hz ||
       !m->soc_one || m->modes!=3 || m->knots<2 || m->knots>MAX_KNOTS ||
       m->unknown!=2 || m->unit_scale!=2)ok=0;
    if(ok && fscanf(f,"%u",&m->r0)!=1)ok=0;
    for(j=0;ok && j<3;j++) {
        if(fscanf(f,"%u %u %u %u",&m->rlo[j],&m->rhi[j],
                  &m->taulo[j],&m->tauhi[j])!=4 || m->rlo[j]>m->rhi[j] ||
           !m->taulo[j] || m->taulo[j]>m->tauhi[j])ok=0;
        if(j!=m->unknown && (m->rlo[j]!=m->rhi[j] || m->taulo[j]!=m->tauhi[j]))ok=0;
    }
    if(ok && fscanf(f,"%d %d %d",&m->initial_rc_nV[0],&m->initial_rc_nV[1],
                    &m->initial_rc_nV[2])!=3)ok=0;
    for(j=0;ok && j<m->knots;j++) {
        int32_t z;int64_t v;
        if(fscanf(f,"%" SCNd32 " %" SCNd64,&z,&v)!=2)ok=0;
        else {m->z[j]=(double)z/m->soc_one;m->v[j]=(double)v*1e-9;}
    }
    fclose(f);return ok?0:-1;
}

static scm_sample *read_samples(const char *path,const public_model *m,size_t *count)
{
    FILE *f=fopen(path,"r");scm_sample *s=NULL;size_t n=0,k;
    if(!f)return NULL;
    if(fscanf(f,"%zu",&n)!=1 || !n || n>MAX_SAMPLES)goto done;
    s=calloc(n,sizeof(*s));if(!s)goto done;
    for(k=0;k<n;k++) {
        uint32_t ticks;int32_t current;int64_t voltage;
        if(fscanf(f,"%" SCNu32 " %" SCNd32 " %" SCNd64,&ticks,&current,&voltage)!=3) {
            free(s);s=NULL;goto done;
        }
        s[k].dt=(double)ticks/(m->ticks_hz*(double)m->unit_scale);
        s[k].current=(double)current*1e-6*m->unit_scale;
        s[k].voltage=(double)voltage*1e-9;
    }
    *count=n;
done:
    fclose(f);return s;
}

int main(int argc,char **argv)
{
    public_model model;scm_ocv ocv;scm_sample *samples;
    scm_fit_options options;size_t samples_n=0,previous=0;int arg,j,failed=0;
    double theta_lo[SCM_MAX_THETA],theta_hi[SCM_MAX_THETA];
    const int coordinates[4]={2,5,6,SCM_MAX_THETA+3};
    if(argc<4 || read_model(argv[1],&model)) {
        fputs("usage: provider_box_reference_probe PUBLIC_MODEL OBSERVATIONS PREFIX...\n",stderr);
        return 2;
    }
    ocv.n=model.knots;ocv.z=model.z;ocv.u=model.v;
    if(scm_ocv_validate(&ocv))return 2;
    samples=read_samples(argv[2],&model,&samples_n);if(!samples)return 2;
    scm_fit_options_default(&options);
    options.starts=3;options.max_iterations=80;
    options.fixed_mask=27u;options.fixed_alpha_mask=503u;
    for(j=0;j<3;j++) {
        if((unsigned)j!=model.unknown) {
            options.fixed_theta[j]=log((double)model.taulo[j]/model.ticks_hz/model.unit_scale);
            options.fixed_alpha[1+j]=(double)model.rlo[j]*.001/model.unit_scale;
        }
        options.fixed_alpha[5+j]=(double)model.initial_rc_nV[j]*1e-9;
    }
    options.fixed_theta[3]=options.fixed_theta[4]=log(100.);
    options.fixed_alpha[0]=(double)model.r0*.001/model.unit_scale;
    options.fixed_alpha[4]=options.fixed_alpha[8]=0.;
    scm_theta_bounds(3,theta_lo,theta_hi);
    printf("{\"schema\":\"mumble_box_retained_reference_v1\",\"method\":\"SCM_FULL\","
           "\"sigma_scale_V\":0.001,\"starts\":3,\"max_iterations\":80,"
           "\"fixed_theta_mask\":27,\"fixed_alpha_mask\":503,\"truth_supplied\":false,"
           "\"has_supplied_initial_guess\":false,\"unit_scale\":%u,"
           "\"Gaussian_coverage_claim\":false,\"equal_feasible_sets\":false,"
           "\"reference_internal_tau_support_s\":[%.17g,%.17g],"
           "\"reference_physical_tau_support_s\":[%.17g,%.17g],"
           "\"reference_internal_R_support_ohm\":[0,1],"
           "\"reference_physical_R_support_ohm\":[0,%u],"
           "\"raw_Gram_coordinates\":[\"internal_logtau_slow\",\"SOC0\",\"logQ\",\"internal_R_slow\"],"
           "\"caller_input_sample_bytes\":%zu,\"caller_model_bytes\":%zu,"
           "\"caller_options_bytes\":%zu,\"caller_result_bytes\":%zu,\"fits\":[",
           model.unit_scale,exp(theta_lo[2]),exp(theta_hi[2]),
           model.unit_scale*exp(theta_lo[2]),model.unit_scale*exp(theta_hi[2]),
           model.unit_scale,samples_n*sizeof(*samples),sizeof(model),sizeof(options),
           sizeof(scm_fit_result));
    for(arg=3;arg<argc;arg++) {
        char *end=NULL;unsigned long long parsed=strtoull(argv[arg],&end,10);
        size_t n=(size_t)parsed;scm_problem *problem;scm_fit_result result;int rc,k;
        if(!end || *end || (unsigned long long)n!=parsed || !n || n>samples_n || n<=previous) {
            failed=1;break;
        }
        if(arg>3)putchar(',');
        previous=n;
        problem=scm_problem_create(samples,n,3,.001,&ocv,SCM_FULL);
        if(!problem){printf("{\"samples\":%zu,\"return_code\":-100}",n);failed=1;continue;}
        rc=scm_fit(problem,&options,&result);
        printf("{\"samples\":%zu,\"return_code\":%d",n,rc);
        if(rc)failed=1;
        else {
            const double q=exp(result.theta[6]);
            const double z=result.theta[5]-result.charge_Ah/q;
            const int d=SCM_MAX_PARAMETERS;
            printf(",\"status\":%d,\"termination_reason\":%d,\"converged_starts\":%d,"
                   "\"initial_SOC\":%.17g,\"current_SOC\":%.17g,\"capacity_Ah\":%.17g,"
                   "\"selected_internal_R_ohm\":%.17g,\"selected_physical_R_mOhm\":%.17g,"
                   "\"selected_internal_tau_s\":%.17g,\"selected_physical_tau_s\":%.17g,"
                   "\"objective\":%.17g,\"objective_full\":%.17g,\"voltage_rmse_V\":%.17g,"
                   "\"projected_gradient\":%.17g,\"iterations\":%d,\"evaluations\":%d,"
                   "\"elapsed_internal_s\":%.17g,\"elapsed_physical_s\":%.17g,"
                   "\"charge_Ah\":%.17g,\"elapsed_cpu_s\":%.17g,"
                   "\"data_bytes\":%zu,\"payload_bytes\":%zu,\"workspace_bytes\":%zu,"
                   "\"retained_bytes\":%zu,\"setup_peak_bytes\":%zu,"
                   "\"active_outer_bounds_all_theta\":%d,\"active_linear_constraints\":%d,"
                   "\"conditional_raw_Gram_scaled_free4\":[",
                   result.status,result.termination_reason,result.converged_starts,
                   result.theta[5],z,q,result.alpha[3],result.alpha[3]*model.unit_scale*1000.,
                   exp(result.theta[2]),exp(result.theta[2])*model.unit_scale,
                   result.objective,result.objective_full,result.voltage_rmse,
                   result.projected_gradient,result.iterations,result.evaluations,
                   result.elapsed_physical_s,result.elapsed_physical_s*model.unit_scale,
                   result.charge_Ah,result.elapsed_cpu_s,result.data_bytes,result.payload_bytes,
                   result.workspace_bytes,result.retained_bytes,result.setup_peak_bytes,
                   result.active_outer_bounds,result.active_linear_constraints);
            for(j=0;j<4;j++)for(k=0;k<4;k++) {
                if(j || k)putchar(',');
                printf("%.17g",result.joint_normal[coordinates[j]*d+coordinates[k]]);
            }
            fputs("],\"raw_Gram_coordinate_scales_internal\":[",stdout);
            for(j=0;j<4;j++){if(j)putchar(',');printf("%.17g",result.coordinate_scales[coordinates[j]]);}
            fputs("],\"raw_Gram_coordinate_scales_physical\":[",stdout);
            for(j=0;j<4;j++){if(j)putchar(',');printf("%.17g",result.coordinate_scales[coordinates[j]]*(j==3?model.unit_scale:1));}
            putchar(']');
        }
        putchar('}');scm_problem_destroy(problem);
    }
    printf("],\"completed\":%s}\n",failed?"false":"true");
    free(samples);return failed?1:0;
}
