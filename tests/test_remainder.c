#include "scm_remainder.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define NS 180
static int failures;
#define CHECK(c,m) do { if(!(c)) { fprintf(stderr,"FAIL remainder: %s\n",m); failures++; } } while(0)

static scm_evidence_config configuration(int modes,uint64_t cap)
{
    scm_evidence_config c;
    const double tau[3]={.05,.5,5};
    int i,nt=scm_model_ntheta(modes),na=scm_model_nalpha(modes);
    memset(&c,0,sizeof(c));c.modes=modes;c.sigma=.001;c.max_event_samples=cap;
    c.residual_rms_limit_sigma=4;c.source_id[0]=28;c.source_id[31]=92;
    for(i=0;i<modes;i++)c.theta[i]=log(modes==3?tau[i]:(i?5.:.05));
    c.theta[modes]=log(150.);c.theta[modes+1]=log(300.);
    c.theta[modes+2]=.68;c.theta[modes+3]=log(.06);
    c.alpha[0]=.12;c.alpha[modes+1]=.025;c.alpha[2+2*modes]=.005;
    for(i=0;i<modes;i++){c.alpha[1+i]=.2;c.alpha[modes+2+i]=.002*(i+1);}
    for(i=0;i<nt;i++)c.scale[i]=i==modes+2?.1:1.;
    for(i=0;i<na;i++)c.scale[nt+i]=i<=modes?.2:.03;
    for(i=0;i<nt+na;i++)c.radius[i]=.2;
    return c;
}

static void make_history(const scm_evidence_config *c,scm_sample *samples)
{
    const double intervals[7]={0,.02,.05,.13,.5,2,10};
    scm_model_state state;scm_model_row row;
    int k;
    CHECK(scm_model_init(&state,c->modes,c->theta)==0,"history model init");
    for(k=0;k<NS;k++) {
        double mu;
        samples[k].dt=intervals[k%7];
        samples[k].current=k<90?(k%5? .06:0):(k%4?-.04:.03);
        CHECK(scm_model_step(&state,NULL,samples[k].dt,samples[k].current,&row)==0,"history model step");
        CHECK(scm_model_predict(&row,c->modes,c->alpha,&mu,NULL)==0,"history prediction");
        samples[k].voltage=mu+c->sigma*(sin(.71*k)+.1*cos(.17*k));
    }
}

static int prediction(const scm_evidence_config *c,const scm_sample *samples,
                      int count,const double *delta,double *mu,double *jac_scaled)
{
    double theta[SCM_MAX_THETA],alpha[SCM_MAX_ALPHA],jac[SCM_MAX_THETA];
    scm_model_state state;scm_model_row row;
    int i,k,n=c->modes,nt=scm_model_ntheta(n),na=scm_model_nalpha(n),status;
    for(i=0;i<nt;i++)theta[i]=c->theta[i]+c->scale[i]*delta[i];
    for(i=0;i<na;i++)alpha[i]=c->alpha[i]+c->scale[nt+i]*delta[nt+i];
    status=scm_model_init(&state,n,theta);if(status)return status;
    for(k=0;k<count;k++) {
        status=scm_model_step(&state,NULL,samples[k].dt,samples[k].current,&row);if(status)return status;
    }
    status=scm_model_predict(&row,n,alpha,mu,jac);if(status)return status;
    if(jac_scaled) {
        for(i=0;i<nt;i++)jac_scaled[i]=jac[i]*c->scale[i];
        for(i=0;i<na;i++)jac_scaled[nt+i]=row.X[i]*c->scale[nt+i];
    }
    return 0;
}

static void coverage(int modes)
{
    scm_evidence_config c=configuration(modes,17),other_c=configuration(modes,1);
    scm_evidence e,other_e;
    scm_evidence_workspace ew,other_ew;
    scm_remainder r,other_r;
    scm_remainder_workspace rw,other_rw;
    scm_remainder_result result;
    scm_sample samples[NS];
    double delta[SCM_EVIDENCE_DIM]={0},zero[SCM_EVIDENCE_DIM]={0};
    int k,i,candidate,nt=scm_model_ntheta(modes),d=nt+scm_model_nalpha(modes);
    make_history(&c,samples);
    CHECK(scm_evidence_init(&e,&c)==0 && scm_remainder_init(&r,&c)==0,"coverage paired init");
    CHECK(scm_evidence_init(&other_e,&other_c)==0 && scm_remainder_init(&other_r,&other_c)==0,"alternate event init");
    CHECK(r.pair_count==3*modes+10,"complete sparse pair count");
    for(k=0;k<NS;k++) {
        CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,(uint64_t)k,&samples[k],&ew,&rw)==0,"coverage paired sample");
        CHECK(scm_remainder_evidence_push(&other_e,&other_r,other_c.source_id,(uint64_t)k,&samples[k],&other_ew,&other_rw)==0,"alternate event paired sample");
        if(k==89)for(i=0;i<r.pair_count;i++)if(r.pair_row[i]==modes+1 || r.pair_column[i]==modes+1)
            CHECK(r.coefficient[i]==0 && r.last_bound[i]==0,"no missing-sign curvature invented");
        if(k==90) {
            scm_remainder saved=r;
            CHECK(scm_evidence_seal(&e,&ew)==0,"explicit event seal");
            CHECK(memcmp(&saved,&r,sizeof(r))==0,"event seal leaves bound untouched");
        }
    }
    for(i=0;i<r.pair_count;i++)CHECK(r.coefficient[i]==other_r.coefficient[i],"bound independent of event partition");
    for(candidate=0;candidate<6;candidate++) {
        double norm_error=0,raw_nll=0,raw_affine=0;
        memset(delta,0,sizeof(delta));
        for(i=0;i<d;i++) {
            if(candidate==0)delta[i]=.06*sin(i+.3);
            if(candidate==1)delta[i]=i%2?.19:-.19;
            if(candidate==2 && i>=nt)delta[i]=.12*cos(i);
        }
        if(candidate==3)delta[nt]=.1;
        if(candidate==4)delta[modes+3]=.1;
        for(k=0;k<NS;k++) {
            double anchor_mu,mu,linear,jac[SCM_EVIDENCE_DIM],difference;
            CHECK(prediction(&c,samples,k+1,zero,&anchor_mu,jac)==0,"independent anchor replay");
            CHECK(prediction(&c,samples,k+1,delta,&mu,NULL)==0,"independent candidate replay");
            linear=anchor_mu;
            for(i=0;i<d;i++)linear+=jac[i]*delta[i];
            difference=(mu-linear)/c.sigma;norm_error=hypot(norm_error,difference);
            raw_nll+=.5*pow((samples[k].voltage-mu)/c.sigma,2);
            raw_affine+=.5*pow((samples[k].voltage-linear)/c.sigma,2);
        }
        CHECK(scm_remainder_query(&r,&e,delta,.1,&result)==0,"bound query");
        CHECK(result.status==SCM_REMAINDER_WITHIN_ANALYTIC_BUDGET || result.status==SCM_REMAINDER_EXCEEDS_BUDGET,"candidate stays in declared physical chart");
        CHECK(!result.arithmetic_validated,"no false outward-rounding claim");
        CHECK(norm_error<=result.whitened_prediction_error_bound+1e-9,"full joint nonlinear prediction remainder covered");
        CHECK(fabs(raw_nll-result.affine_nll)<=result.nll_error_bound+3e-8,"whole nonlinear NLL disagreement covered");
        CHECK(fabs(raw_affine-result.affine_nll)<3e-8,"bound uses entire affine objective");
        if(candidate==2 || candidate==3 || candidate==5)
            CHECK(result.whitened_prediction_error_bound==0 && result.nll_error_bound==0,"amplitude-only or zero move has zero analytic remainder");
    }
    if(modes==3) {
        double step=1e-5,mu;
        for(i=0;i<d;i++)delta[i]=.1*sin(i+.7);
        for(k=0;k<r.pair_count;k++) {
            double plus[16],minus[16],jp[16],jm[16],h;
            int a=r.pair_row[k],b=r.pair_column[k];
            memcpy(plus,delta,sizeof(plus));memcpy(minus,delta,sizeof(minus));
            plus[b]+=step;minus[b]-=step;
            CHECK(prediction(&c,samples,NS,plus,&mu,jp)==0,"Hessian positive difference");
            CHECK(prediction(&c,samples,NS,minus,&mu,jm)==0,"Hessian negative difference");
            h=(jp[a]-jm[a])/(2*step*c.sigma);
            CHECK(fabs(h)<=r.last_bound[k]*(1+2e-6)+1e-7,"sparse Hessian entry bound covers finite difference");
        }
    }
}

static void errors_and_zero_dt(void)
{
    scm_evidence_config c=configuration(3,8),bad;
    scm_evidence e,saved_e;
    scm_evidence_workspace ew;
    scm_remainder r,saved_r;
    scm_remainder_workspace rw;
    scm_remainder_result out;
    scm_sample sample={0,.04,3.8};
    unsigned char other[SCM_EVIDENCE_SOURCE_BYTES]={0};
    double delta[16]={0},z[2]={0,1},u[2]={3,4};
    int i,status;
    CHECK(scm_evidence_init(&e,&c)==0 && scm_remainder_init(&r,&c)==0,"errors paired init");
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,0,&sample,&ew,&rw)==0,"zero interval positive current");
    sample.current=-.04;
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,1,&sample,&ew,&rw)==0,"zero interval negative current");
    CHECK(r.elapsed==0 && r.charge_Ah==0 && r.throughput_Ah[0]==0 && r.throughput_Ah[1]==0,"zero dt freezes all transported states");
    for(i=0;i<r.pair_count;i++)if(r.pair_row[i]!=5 || r.pair_column[i]!=5)
        CHECK(r.coefficient[i]==0,"zero dt leaves only initial SOC curvature");
    saved_e=e;saved_r=r;sample.dt=1./35.;
    status=scm_remainder_evidence_push(&e,&r,c.source_id,1,&sample,&ew,&rw);
    CHECK(status==SCM_REMAINDER_ERR_ORDER,"duplicate rejected");
    CHECK(memcmp(&e,&saved_e,sizeof(e))==0 && memcmp(&r,&saved_r,sizeof(r))==0,"duplicate pair atomic");
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,3,&sample,&ew,&rw)==SCM_REMAINDER_ERR_ORDER,"gap rejected");
    CHECK(scm_remainder_evidence_push(&e,&r,other,2,&sample,&ew,&rw)==SCM_REMAINDER_ERR_SOURCE,"wrong source rejected");
    CHECK(memcmp(&e,&saved_e,sizeof(e))==0 && memcmp(&r,&saved_r,sizeof(r))==0,"source and gap atomic");
    sample.voltage=NAN;
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,2,&sample,&ew,&rw)==SCM_REMAINDER_ERR_NONFINITE,"nonfinite rejected");
    sample.voltage=DBL_MAX;
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,2,&sample,&ew,&rw)==SCM_EVIDENCE_ERR_NONFINITE,"failed evidence update after valid remainder staging");
    CHECK(memcmp(&e,&saved_e,sizeof(e))==0 && memcmp(&r,&saved_r,sizeof(r))==0,"late evidence failure pair atomic");
    sample.voltage=3.8;
    CHECK(scm_evidence_push(&e,c.source_id,2,&sample,&ew)==0,"advance evidence alone for mismatch canary");
    CHECK(scm_remainder_query(&r,&e,delta,.1,&out)==SCM_REMAINDER_ERR_MISMATCH && out.status==SCM_REMAINDER_UNAVAILABLE,"count mismatch query fails closed");
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,3,&sample,&ew,&rw)==SCM_REMAINDER_ERR_MISMATCH,"pair mismatch rejected");
    e=saved_e;e.config.scale[0]*=2;
    CHECK(scm_remainder_query(&r,&e,delta,.1,&out)==SCM_REMAINDER_ERR_MISMATCH,"chart mismatch query fails closed");
    e=saved_e;delta[0]=.201;
    CHECK(scm_remainder_query(&r,&e,delta,.1,&out)==0 && out.status==SCM_REMAINDER_OUTSIDE_DOMAIN,"outside radius explicit");
    delta[0]=0;delta[5]=.1;
    CHECK(scm_remainder_query(&r,&e,delta,0,&out)==0 && out.status==SCM_REMAINDER_EXCEEDS_BUDGET,"nonzero bound exceeds zero budget");
    CHECK(scm_remainder_query(&r,&e,delta,-1,&out)==SCM_REMAINDER_ERR_ARGUMENT && out.status==SCM_REMAINDER_UNAVAILABLE,"negative budget unavailable");
    delta[5]=NAN;
    CHECK(scm_remainder_query(&r,&e,delta,.1,&out)==SCM_REMAINDER_ERR_NONFINITE,"nonfinite candidate unavailable");
    bad=c;bad.ocv.n=2;bad.ocv.z=z;bad.ocv.u=u;
    CHECK(scm_remainder_init(&r,&bad)==SCM_REMAINDER_ERR_UNSUPPORTED,"PWL explicitly unsupported");
    CHECK(memcmp(&r,&saved_r,sizeof(r))==0,"unsupported init atomic");
    bad=c;bad.radius[0]=1e308;
    CHECK(scm_remainder_init(&r,&bad)==SCM_REMAINDER_ERR_NONFINITE,"overflowing rectangle unavailable");
    CHECK(memcmp(&r,&saved_r,sizeof(r))==0,"nonfinite rectangle init atomic");
}

static void chronology_binding(void)
{
    scm_evidence_config c=configuration(3,8);
    scm_evidence e,other,saved_e;
    scm_evidence_workspace ew,other_ew;
    scm_remainder r,saved_r;
    scm_remainder_workspace rw;
    scm_remainder_result out;
    scm_sample sample={1,.1,3.8};
    double zero[16]={0};
    CHECK(scm_evidence_init(&e,&c)==0 && scm_remainder_init(&r,&c)==0,"independent chronology init");
    CHECK(scm_evidence_push(&e,c.source_id,0,&sample,&ew)==0,"independent first evidence current");
    sample.current=.2;
    CHECK(scm_remainder_push(&r,c.source_id,0,&sample,&rw)==0,"independent reversed first envelope current");
    CHECK(scm_evidence_push(&e,c.source_id,1,&sample,&ew)==0,"independent second evidence current");
    sample.current=.1;
    CHECK(scm_remainder_push(&r,c.source_id,1,&sample,&rw)==0,"independent reversed second envelope current");
    CHECK(e.next_index==r.next_index && e.model.elapsed==r.elapsed && e.model.charge_Ah==r.charge_Ah &&
          e.charge_max_Ah==r.charge_max_Ah && e.charge_min_Ah==r.charge_min_Ah,"reordered streams share aggregate metadata");
    CHECK(scm_remainder_query(&r,&e,zero,.1,&out)==SCM_REMAINDER_ERR_MISMATCH &&
          out.status==SCM_REMAINDER_UNAVAILABLE,"independent reordered histories cannot certify each other");
    saved_e=e;saved_r=r;
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,2,&sample,&ew,&rw)==SCM_REMAINDER_ERR_MISMATCH,"independent ancestry cannot rejoin by matching aggregates");
    CHECK(memcmp(&e,&saved_e,sizeof(e))==0 && memcmp(&r,&saved_r,sizeof(r))==0,"failed rejoin atomic");
    CHECK(scm_evidence_init(&e,&c)==0 && scm_remainder_init(&r,&c)==0 &&
          scm_evidence_init(&other,&c)==0,"fresh paired ancestry init");
    CHECK(scm_remainder_query(&r,&e,zero,.1,&out)==0 && out.status==SCM_REMAINDER_WITHIN_ANALYTIC_BUDGET,"empty pair permits zero objective query");
    CHECK(scm_remainder_evidence_push(&e,&r,c.source_id,0,&sample,&ew,&rw)==0,"fresh paired chronology");
    CHECK(scm_evidence_push(&other,c.source_id,0,&sample,&other_ew)==0,"same contents in another evidence object");
    CHECK(scm_remainder_query(&r,&e,zero,.1,&out)==0 && out.status==SCM_REMAINDER_WITHIN_ANALYTIC_BUDGET,"bound evidence object query accepted");
    CHECK(scm_remainder_query(&r,&other,zero,.1,&out)==SCM_REMAINDER_ERR_MISMATCH,"equivalent foreign evidence object rejected");
    saved_e=other;saved_r=r;
    CHECK(scm_remainder_evidence_push(&other,&r,c.source_id,1,&sample,&other_ew,&rw)==SCM_REMAINDER_ERR_MISMATCH,"foreign evidence rebinding rejected");
    CHECK(memcmp(&other,&saved_e,sizeof(other))==0 && memcmp(&r,&saved_r,sizeof(r))==0,"foreign rebind atomic");
}

int main(void)
{
    int n;
    for(n=1;n<=3;n++)coverage(n);
    errors_and_zero_dt();
    chronology_binding();
    if(failures){fprintf(stderr,"%d remainder checks failed\n",failures);return 1;}
    printf("remainder checks passed; bank=%zu workspace=%zu result=%zu bytes; arithmetic_validated=false\n",
           sizeof(scm_remainder),sizeof(scm_remainder_workspace),sizeof(scm_remainder_result));
    return 0;
}
