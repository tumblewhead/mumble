#include "scm_compact_assess.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* Fixed before running: the eigenvalue matrix arithmetic is shared; rotating
 * gradients directly instead of forming V then V^T*g can change roundoff.
 * Categorical decisions must agree exactly on these non-borderline fixtures.
 */
#define EIGEN_ATOL 1e-9
#define EIGEN_RTOL 1e-12
#define TARGET_ATOL 1e-11
#define TARGET_RTOL 1e-9

static int checks,failures;
static double maximum_eigen_error,maximum_target_error;
#define CHECK(c,m) do{checks++;if(!(c)){fprintf(stderr,"FAIL %s\n",m);failures++;}}while(0)

static int close_number(double x,double y,double atol,double rtol,double *maximum)
{
    double error=fabs(x-y);
    if(error>*maximum)*maximum=error;
    return isfinite(x)&&isfinite(y)&&error<=atol+rtol*fmax(fabs(x),fabs(y));
}

static void config_fixture(scm_evidence_config *c,int n)
{
    static const double tau[]={.05,1.,5.};
    int i,nt=n+4,na=2*n+3,d=nt+na;
    memset(c,0,sizeof(*c));c->modes=n;c->sigma=.001;
    c->max_event_samples=8;c->residual_rms_limit_sigma=4.;
    for(i=0;i<SCM_EVIDENCE_SOURCE_BYTES;i++)c->source_id[i]=(unsigned char)(17+i);
    for(i=0;i<n;i++)c->theta[i]=log(tau[i]);
    c->theta[n]=log(150);c->theta[n+1]=log(300);c->theta[n+2]=.68;c->theta[n+3]=log(.06);
    for(i=0;i<=n;i++)c->alpha[i]=.2;
    c->alpha[1+n]=.025;c->alpha[2+2*n]=.005;
    for(i=0;i<nt;i++)c->scale[i]=i==n+2?.1:1.;
    for(i=0;i<na;i++)c->scale[nt+i]=i<=n?.2:.03;
    for(i=0;i<d;i++)c->radius[i]=.01;
}

static void compare_target(const scm_assess_target *actual,const scm_assess_target *reference)
{
#define CHECK_FIELD(f) CHECK(actual->f==reference->f,"target " #f)
#define CHECK_REAL(f) CHECK(close_number(actual->f,reference->f,TARGET_ATOL,TARGET_RTOL,&maximum_target_error),"target " #f)
    CHECK(!strcmp(actual->name,reference->name),"target name");
    CHECK(!strcmp(actual->units,reference->units),"target units");
    CHECK_FIELD(status);CHECK_FIELD(reasons);CHECK_FIELD(point_available);
    CHECK_FIELD(has_local_range);CHECK_FIELD(has_relative_halfwidth);
    CHECK_FIELD(passes_local_precision);CHECK_FIELD(eligible_for_profile_check);
    CHECK_FIELD(active_constraints_present);CHECK_FIELD(conditioned_fit);
    CHECK_REAL(point);CHECK_REAL(lower);CHECK_REAL(upper);CHECK_REAL(support_lower);
    CHECK_REAL(support_upper);CHECK_REAL(null_projection);CHECK_REAL(local_standard_deviation);
    CHECK_REAL(local_halfwidth);CHECK_REAL(relative_halfwidth);
#undef CHECK_REAL
#undef CHECK_FIELD
}

static void compare(const scm_compact_evidence *e,const scm_evidence_factor *snapshot,
    int status,int active,const scm_assess_options *options,scm_compact_assessment *result)
{
    scm_fit_result f;scm_assessment a;scm_assess_workspace w;
    scm_compact_assess_workspace cw;
    scm_compact_evidence before=*e;
    double gradient[SCM_MAX_PARAMETERS],cost;
    int n=e->config->modes,nt=n+4,na=2*n+3,d=nt+na,i;
    memset(&f,0,sizeof(f));memset(&cw,0xa5,sizeof(cw));
    memcpy(f.theta,e->config->theta,(size_t)nt*sizeof(double));
    memcpy(f.alpha,e->config->alpha,(size_t)na*sizeof(double));
    memcpy(f.coordinate_scales,e->config->scale,(size_t)d*sizeof(double));
    f.charge_Ah=e->model.charge_Ah;f.status=status;f.active_linear_constraints=active;
    CHECK(scm_evidence_factor_normal(snapshot,f.joint_normal,gradient,&cost)==0,"reference normal");
    CHECK(scm_assess(&f,n,options,&a,&w)==0,"reference assessment");
    CHECK(scm_compact_assess(e,status,active,options,result,&cw)==0,"compact assessment");
    CHECK(!memcmp(&before,e,sizeof(before)),"query leaves evidence byte-identical");
    CHECK(result->modes==a.modes&&result->joint_dimension==a.joint_dimension,"report dimensions");
    CHECK(result->numerical_rank==a.numerical_rank,"full joint numerical rank");
    CHECK(result->matrix_invalid==a.matrix_invalid,"matrix validity");
    CHECK(result->eigen_converged==a.eigen_converged,"eigen convergence");
    CHECK(result->coordinate_chart_supported==a.coordinate_chart_supported,"coordinate chart");
    CHECK(result->optimizer_status==a.optimizer_status&&result->active_constraints==a.active_constraints,"caller qualifications");
    CHECK(close_number(result->eigen_cutoff,a.eigen_cutoff,EIGEN_ATOL,EIGEN_RTOL,&maximum_eigen_error),"eigen cutoff");
    for(i=0;i<d;i++)CHECK(close_number(cw.eigenvalues[i],a.eigenvalues[i],EIGEN_ATOL,EIGEN_RTOL,&maximum_eigen_error),"eigenvalue");
    compare_target(&result->current_soc,&a.targets[d]);
    compare_target(&result->capacity_Q_Ah,&a.targets[n+3]);
}

/* Deliberately constructed factors isolate the diagnostic mathematics, not
 * physical-history reachability or optimizer performance. */
static void factor_tests(void)
{
    scm_evidence_config c;scm_compact_evidence e;
    scm_compact_assessment result;scm_assess_options o;
    int n,nt,d,i,j,q,z;
    for(n=1;n<=3;n++) {
        config_fixture(&c,n);CHECK(scm_compact_evidence_init(&e,&c)==0,"fixture init");
        nt=n+4;d=3*n+7;q=n+3;z=n+2;e.model.charge_Ah=.006;
        e.history.samples=32;e.next_index=32;e.active_begin=32;
        for(i=0;i<d;i++)e.history.upper[scm_evidence_packed_index((size_t)i,(size_t)i)]=1000.;
        e.history.upper[scm_evidence_packed_index((size_t)d,(size_t)d)]=3.;
        compare(&e,&e.history,0,0,NULL,&result);
        CHECK(result.current_soc.status==SCM_ASSESS_PROVISIONAL&&result.capacity_Q_Ah.status==SCM_ASSESS_PROVISIONAL,"diagonal target precision");
        for(i=0;i<d;i++)for(j=i+1;j<=d;j++)
            e.history.upper[scm_evidence_packed_index((size_t)i,(size_t)j)]=(double)((i*17+j*31)%19-9)*5.;
        compare(&e,&e.history,0,2,NULL,&result);
        compare(&e,&e.history,1,0,NULL,&result);
        CHECK(!result.current_soc.has_local_range&&!result.capacity_Q_Ah.has_local_range,"unperformed optimizer keeps support");
        scm_assess_options_default(&o);o.conditioned_fit=1;
        compare(&e,&e.history,0,0,&o,&result);
        o.linked_current_soc_chart=1;compare(&e,&e.history,0,0,&o,&result);
        CHECK(!result.coordinate_chart_supported&&!result.current_soc.has_local_range,"linked chart withheld");
        memset(e.history.upper,0,sizeof(e.history.upper));
        compare(&e,&e.history,0,0,NULL,&result);
        CHECK(result.numerical_rank==0&&result.capacity_Q_Ah.lower==.03&&result.capacity_Q_Ah.upper==.1,"empty information preserves full Q support");
        for(i=0;i<d;i++)e.history.upper[scm_evidence_packed_index((size_t)i,(size_t)i)]=1000.;
        e.history.upper[scm_evidence_packed_index((size_t)z,(size_t)q)]=1000.;
        e.history.upper[scm_evidence_packed_index((size_t)q,(size_t)q)]=0.;
        compare(&e,&e.history,0,0,NULL,&result);
        CHECK(result.current_soc.status==SCM_ASSESS_PROVISIONAL&&result.capacity_Q_Ah.status==SCM_ASSESS_UNRESOLVED,"observable SOC combination preserves unresolved Q");
        e.history.upper[scm_evidence_packed_index((size_t)z,(size_t)q)]=0.;
        e.history.upper[scm_evidence_packed_index((size_t)q,(size_t)q)]=1000.;
        e.history.upper[scm_evidence_packed_index((size_t)q,(size_t)nt)]=1000.;
        e.history.upper[scm_evidence_packed_index((size_t)nt,(size_t)nt)]=0.;
        compare(&e,&e.history,0,0,NULL,&result);
        CHECK(result.capacity_Q_Ah.status==SCM_ASSESS_UNRESOLVED,"nuisance null direction is not conditioned away");
        e.history.upper[scm_evidence_packed_index((size_t)q,(size_t)nt)]=0.;
        e.history.upper[scm_evidence_packed_index((size_t)nt,(size_t)nt)]=1000.;
        e.history.upper[scm_evidence_packed_index((size_t)q,(size_t)q)]=sqrt(1e-4*.5);
        compare(&e,&e.history,0,0,NULL,&result);
        CHECK(result.numerical_rank==d-1,"rank cutoff below");
        e.history.upper[scm_evidence_packed_index((size_t)q,(size_t)q)]=sqrt(1e-4*2.);
        compare(&e,&e.history,0,0,NULL,&result);
        CHECK(result.numerical_rank==d,"rank cutoff above");
    }
}

static void stream_tests(void)
{
    scm_evidence_config c;scm_evidence original;
    scm_evidence_workspace original_work;scm_evidence_factor snapshot;
    scm_compact_evidence compact;scm_compact_evidence_workspace compact_work;
    scm_compact_assessment result;
    int n,k;
    for(n=1;n<=3;n++) {
        config_fixture(&c,n);
        CHECK(scm_evidence_init(&original,&c)==0,"original stream init");
        CHECK(scm_compact_evidence_init(&compact,&c)==0,"compact stream init");
        for(k=0;k<120;k++) {
            scm_sample sample={k%19?1./35.:0.,k<45?.12:(k<80?-.08:0.),3.8+.0001*(k%7)};
            CHECK(scm_evidence_push(&original,c.source_id,(uint64_t)k,&sample,&original_work)==0,"original stream push");
            CHECK(scm_compact_evidence_push(&compact,c.source_id,(uint64_t)k,&sample,&compact_work)==0,"compact stream push");
            if(k==0||k==8||k==31||k==119) {
                CHECK(scm_evidence_snapshot(&original,&snapshot,&original_work)==0,"original stream snapshot");
                compare(&compact,&snapshot,1,0,NULL,&result);
            }
        }
    }
}

static void rejected_input_tests(void)
{
    scm_evidence_config c;scm_compact_evidence e,before;
    scm_compact_assessment result;scm_compact_assess_workspace w;
    scm_assess_options o;int d;
    config_fixture(&c,3);CHECK(scm_compact_evidence_init(&e,&c)==0,"error fixture init");
    d=e.history.dim;
    CHECK(scm_compact_assess(NULL,0,0,NULL,&result,&w)==-1,"null bank rejected");
    scm_assess_options_default(&o);o.eigen_rtol=0;
    CHECK(scm_compact_assess(&e,0,0,&o,&result,&w)==-1,"invalid cutoff rejected");
    e.history.upper[scm_evidence_packed_index(0,0)]=NAN;before=e;
    CHECK(scm_compact_assess(&e,0,0,NULL,&result,&w)==-1,"nonfinite factor rejected");
    CHECK(!memcmp(&e,&before,sizeof(e)),"nonfinite failure leaves bank");
    e.history.upper[scm_evidence_packed_index(0,0)]=DBL_MAX;before=e;
    CHECK(scm_compact_assess(&e,0,0,NULL,&result,&w)==-1,"Gram overflow rejected");
    CHECK(!memcmp(&e,&before,sizeof(e)),"Gram overflow leaves bank");
    memset(e.history.upper,0,sizeof(e.history.upper));
    e.history.upper[scm_evidence_packed_index((size_t)d,(size_t)d)]=DBL_MAX;before=e;
    CHECK(scm_compact_assess(&e,0,0,NULL,&result,&w)==-1,"residual cost overflow rejected");
    CHECK(!memcmp(&e,&before,sizeof(e)),"cost overflow leaves bank");
    memset(e.history.upper,0,sizeof(e.history.upper));
    e.history.upper[scm_evidence_packed_index(0,0)]=1e100;
    e.history.upper[scm_evidence_packed_index(0,(size_t)d)]=1e250;before=e;
    CHECK(scm_compact_assess(&e,0,0,NULL,&result,&w)==-1,"cross-residual gradient overflow rejected");
    CHECK(!memcmp(&e,&before,sizeof(e)),"gradient overflow leaves bank");
}

int main(void)
{
    factor_tests();stream_tests();rejected_input_tests();
    printf("{\"test\":\"scm_compact_assess\",\"checks\":%d,\"failures\":%d,\"workspace_bytes\":%zu,\"output_bytes\":%zu,\"options_bytes\":%zu,\"max_eigen_abs_error\":%.17g,\"max_target_abs_error\":%.17g,\"tolerances\":{\"eigen_atol\":%.17g,\"eigen_rtol\":%.17g,\"target_atol\":%.17g,\"target_rtol\":%.17g}}\n",
           checks,failures,sizeof(scm_compact_assess_workspace),sizeof(scm_compact_assessment),sizeof(scm_assess_options),maximum_eigen_error,maximum_target_error,EIGEN_ATOL,EIGEN_RTOL,TARGET_ATOL,TARGET_RTOL);
    return failures?1:0;
}
