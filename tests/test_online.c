#include "scm_online.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define D SCM_ONLINE_DIM
#define AT(i,j) ((i)*D+(j))
static int checks,failures;
static double max_prediction_error,max_factor_derivative_error,max_joseph_error;
#define CHECK(c,m) do{checks++;if(!(c)){fprintf(stderr,"FAIL %s (line %d)\n",m,__LINE__);failures++;}}while(0)

static scm_online_config config(void)
{
    scm_online_config c;unsigned i;scm_online_config_default(&c);
    for(i=0;i<SCM_ONLINE_SOURCE_BYTES;i++)c.source_id[i]=(unsigned char)(19+3*i);
    return c;
}

static void prior(scm_online *s)
{
    scm_online_config c=config();CHECK(scm_online_init(s,&c)==0,"initialize public prior");
}

/* Independent physical transition reuses the preserved original model, not
 * the online implementation or its analytic Jacobian. */
static int physical(const double x[D],double dt,double current,double result[D],double *voltage)
{
    scm_physical p={0};scm_physical_state st={0};int i,rc;
    p.modes=3;p.gamma_plus=exp(x[3]);p.gamma_minus=exp(x[4]);p.Q=exp(x[5]);
    p.R0=x[6];p.H=x[10];st.z=x[11];st.h=x[15];
    for(i=0;i<3;i++){p.tau[i]=exp(x[i]);p.R[i]=x[7+i];st.v[i]=x[12+i];}
    rc=scm_physical_step(&p,&st,NULL,dt,current,voltage);if(rc)return rc;
    memcpy(result,x,D*sizeof(double));result[11]=st.z;result[15]=st.h;
    for(i=0;i<3;i++)result[12+i]=st.v[i];
    return 0;
}

static void prediction_and_derivatives(void)
{
    const double currents[]={.073,-.041,0};const double intervals[]={.0341,.123,0};
    scm_online original,s;scm_online_workspace w;double expected[D],plus[D],minus[D],x[D],J[D*D];
    int case_id,i,j,k;
    for(case_id=0;case_id<3;case_id++) {
        double voltage,dt=intervals[case_id],current=currents[case_id];
        scm_sample input={dt,current,NAN};prior(&original);
        original.mean[12]=.011;original.mean[13]=-.007;original.mean[14]=.004;original.mean[15]=.31;
        for(i=0;i<D;i++)for(j=0;j<i;j++)
            original.factor[AT(i,j)]=.017*original.factor[AT(i,i)]*sin((double)((i+1)*(j+3)));
        CHECK(physical(original.mean,dt,current,expected,&voltage)==0,"independent physical prediction");
        s=original;CHECK(scm_online_ingest(&s,s.config.source_id,0,&input,0,&w)==0,"prediction-only ingest");
        for(i=0;i<D;i++) {
            double err=fabs(s.mean[i]-expected[i]);max_prediction_error=fmax(max_prediction_error,err);
            CHECK(err<3e-15,"online mean agrees with original physical dynamics");
        }
        CHECK(fabs(s.last_prediction_V-voltage)<3e-15,"predicted voltage agrees with original physical model");
        for(k=0;k<D;k++) {
            const double h=1e-6;
            memcpy(x,original.mean,sizeof(x));x[k]+=h;
            CHECK(physical(x,dt,current,plus,&voltage)==0,"positive finite-difference point");
            x[k]-=2*h;CHECK(physical(x,dt,current,minus,&voltage)==0,"negative finite-difference point");
            for(i=0;i<D;i++)J[AT(i,k)]=(plus[i]-minus[i])/(2*h);
        }
        for(i=0;i<D;i++)for(j=0;j<D;j++) {
            double value=0,err;
            for(k=0;k<D;k++)value+=J[AT(i,k)]*original.factor[AT(k,j)];
            err=fabs(value-s.factor[AT(i,j)]);max_factor_derivative_error=fmax(max_factor_derivative_error,err);
            CHECK(err<2e-8,"square-factor propagation matches independent finite-difference Jacobian");
        }
        CHECK(scm_online_validate(&s)==0,"predicted state validates");
        for(i=0;i<D;i++)for(j=i+1;j<D;j++)
            CHECK(s.factor[AT(i,j)]==0,"sparse prediction preserves exact lower shape");
    }
}

static void covariance(const double *factor,double *P)
{
    int i,j,k;for(i=0;i<D;i++)for(j=0;j<D;j++) {
        P[AT(i,j)]=0;for(k=0;k<D;k++)P[AT(i,j)]+=factor[AT(i,k)]*factor[AT(j,k)];
    }
}

/* The oracle forms P, a dense Jacobian gain, and (I-KH)P(I-KH)^T+K R K^T.
 * It does not use either orthogonal factor pass or output diagnostic gains. */
static void joseph_case(int kind)
{
    scm_online before,after;scm_online_workspace workspace;
    double P[D*D],A[D*D],AP[D*D],expected[D*D],actual[D*D];
    double H[D]={0},K[D]={0},selected[D],scales[D],lo[D],hi[D];
    double mu,physical_mean[D],u,slope,variance,residual,minimum=1.,maximum=0.;
    scm_sample sample={0,.04,0};int i,j,k,active=0,any_gain=0;
    unsigned limited=0,blocked=0;
    prior(&before);
    for(i=0;i<D;i++)for(j=0;j<i;j++)
        before.factor[AT(i,j)]=.013*before.factor[AT(i,i)]*cos((double)((i+3)*(j+1)));
    if(kind==2) {
        for(i=0;i<D;i++)for(j=0;j<i;j++)before.factor[AT(i,j)]=0.;
        before.factor[AT(11,5)]=.04;before.mean[6]=0.;
        /* R0's outward update is blocked; SOC and logQ remain admissible. */
    }
    if(kind==3||kind==9)for(i=0;i<D;i++)for(j=0;j<D;j++)
        if(j%2==0)before.factor[AT(i,j)]=0;
    if(kind==4) {
        memset(before.factor,0,sizeof(before.factor));
        before.factor[AT(0,0)]=.5;before.factor[AT(1,1)]=.4;
        before.factor[AT(1,0)]=-0.;before.mean[10]=-0.;
        /* Uncertainty entirely in directions absent from this observation. */
    }
    if(kind==5) {
        for(i=0;i<D;i++)for(j=0;j<i;j++)before.factor[AT(i,j)]=0.;
        before.mean[6]=0.;before.mean[10]=.1;before.mean[11]=1.;before.mean[15]=-1.;
        for(i=12;i<=14;i++)before.mean[i]=-.25;
        /* Every observation-sensitive coordinate lies at its outward bound. */
    }
    if(kind==7)before.factor[AT(0,0)]=0.; /* Nonzero entries remain below it. */
    if(kind==8) {
        memset(before.factor,0,sizeof(before.factor));
        before.factor[AT(6,6)]=.2;before.factor[AT(11,6)]=.1;before.mean[6]=1.;
        /* A rank-one prior and a blocked R0 component require a rank-two
         * Joseph covariance; the ascending pass must handle a zero pivot. */
    }
    CHECK(scm_online_validate(&before)==0,"oracle fixture obeys lower-factor contract");
    CHECK(physical(before.mean,0,sample.current,physical_mean,&mu)==0,"independent measurement point");
    CHECK(scm_ocv_eval(NULL,before.mean[11],&u,&slope)==0,"independent voltage gradient");
    H[6]=-sample.current;H[10]=-before.mean[15];H[11]=slope;
    H[12]=H[13]=H[14]=-1;H[15]=-before.mean[10];
    residual=(kind==1||kind==9)?10.:kind==6?0.:(kind==2||kind==5||kind==8)?.001:1e-5;
    sample.voltage=mu+residual;
    residual=sample.voltage-mu;
    covariance(before.factor,P);variance=before.config.sigma_V*before.config.sigma_V;
    for(i=0;i<D;i++){for(j=0;j<D;j++)K[i]+=P[AT(i,j)]*H[j];variance+=H[i]*K[i];}
    for(i=0;i<D;i++)K[i]/=variance;
    scm_online_bounds(lo,hi);
    for(i=0;i<D;i++) {
        double delta=K[i]*residual,scale=1.;
        if(delta>hi[i]-before.mean[i])scale=(hi[i]-before.mean[i])/delta;
        else if(delta<lo[i]-before.mean[i])scale=(lo[i]-before.mean[i])/delta;
        if(scale<1.)scale*=1.-1e-9;
        scales[i]=scale;selected[i]=scale*K[i];
        if(K[i]!=0) {
            active=1;minimum=fmin(minimum,scale);maximum=fmax(maximum,scale);
            if(scale<1.)limited|=1u<<i;
            if(selected[i]==0)blocked|=1u<<i;
        }
        if(selected[i]!=0)any_gain=1;
    }
    if(!active)maximum=1.;
    after=before;
    CHECK(scm_online_ingest(&after,after.config.source_id,0,&sample,1,&workspace)==0,"scalar measurement accepted");
    CHECK(after.rejected_voltage_count==0,"oracle fixture is not numerically rejected");
    CHECK(fabs(after.last_gain_scale-minimum)<2e-13&&fabs(after.last_max_gain_scale-maximum)<2e-13,
          "component multiplier extrema agree with independent oracle");
    CHECK(after.last_limited_mask==limited&&after.last_blocked_mask==blocked,
          "component limiter masks agree with independent oracle");
    CHECK(after.zero_gain_count==(uint64_t)!any_gain&&after.limited_gain_count==(uint64_t)(limited!=0),
          "zero-gain and limited-update counters follow distinct definitions");
    CHECK(after.has_voltage==any_gain&&after.evidence_next_index==(uint64_t)any_gain,
          "evidence follows actual selected gain, not minimum multiplier");
    for(i=0;i<D;i++)for(j=0;j<D;j++)A[AT(i,j)]=(i==j?1.:0.)-selected[i]*H[j];
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        AP[AT(i,j)]=0;for(k=0;k<D;k++)AP[AT(i,j)]+=A[AT(i,k)]*P[AT(k,j)];
    }
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        expected[AT(i,j)]=selected[i]*selected[j]*before.config.sigma_V*before.config.sigma_V;
        for(k=0;k<D;k++)expected[AT(i,j)]+=AP[AT(i,k)]*A[AT(j,k)];
    }
    covariance(after.factor,actual);
    for(i=0;i<D;i++) {
        double point=before.mean[i]+selected[i]*residual;
        CHECK(fabs(after.mean[i]-point)<2e-13,"mean uses the same gain as covariance");
        for(j=0;j<D;j++) {
            double error=fabs(actual[AT(i,j)]-expected[AT(i,j)]);
            max_joseph_error=fmax(max_joseph_error,error);
            CHECK(error<3e-13*fmax(1.,fabs(expected[AT(i,j)])),"square factor matches independently formed dense Joseph covariance");
            if(j>i)CHECK(after.factor[AT(i,j)]==0,"correction preserves exact lower shape");
        }
        CHECK(after.factor[AT(i,i)]>=0,"lower factor has nonnegative diagonal");
    }
    if(kind==2) {
        CHECK(after.last_gain_scale==0&&after.last_max_gain_scale==1&&after.last_blocked_mask==(1u<<6),
              "one nuisance coordinate is blocked while others retain full gain");
        CHECK(after.mean[6]==before.mean[6]&&after.mean[11]!=before.mean[11]&&after.mean[5]!=before.mean[5],
              "boundary nuisance cannot suppress feasible SOC and capacity learning");
        CHECK(fabs(actual[AT(6,6)]-P[AT(6,6)])<1e-14,
              "blocked coordinate does not receive an inconsistent variance reduction");
    }
    if(kind==1||kind==9) {
        CHECK(after.last_gain_scale>0&&after.last_gain_scale<1&&after.last_max_gain_scale>after.last_gain_scale,
              "independent partial multipliers differ");
        CHECK(scales[11]<1.,"large innovation exercises SOC feasibility limit");
    }
    if(kind==4||kind==5) {
        CHECK(!memcmp(before.mean,after.mean,sizeof(before.mean)),"all-zero selected gain keeps mean bit-exact");
        CHECK(!memcmp(before.factor,after.factor,sizeof(before.factor)),"all-zero selected gain keeps factor bit-exact");
        CHECK(!after.has_voltage&&after.evidence_next_index==0,"zero gain cannot create belief availability");
    }
    if(kind==4)CHECK(after.last_gain_scale==1&&after.last_max_gain_scale==1&&
        !after.last_limited_mask&&!after.last_blocked_mask&&after.zero_gain_count==1,
        "empty sensitivity has unit multiplier diagnostics and zero actual gain");
    if(kind==6) {
        CHECK(!memcmp(before.mean,after.mean,sizeof(before.mean)),"zero innovation leaves mean unchanged");
        CHECK(actual[AT(11,11)]<P[AT(11,11)]&&after.has_voltage,"zero innovation still learns covariance");
    }
    if(kind==8) {
        double determinant=actual[AT(6,6)]*actual[AT(11,11)]-actual[AT(6,11)]*actual[AT(11,6)];
        CHECK(after.factor[AT(11,11)]>0&&determinant>1e-10,
              "component limiting can increase factor rank through a zero pivot");
    }
    CHECK(scm_online_validate(&after)==0,"corrected state validates");
}

static void staged_failure(void)
{
    scm_online before,predicted,after;scm_online_workspace w;
    scm_sample input={.031,.04,3.8};
    prior(&before);before.factor[AT(11,0)]=1e200;
    CHECK(scm_online_validate(&before)==0,"large finite lower factor is valid input state");
    predicted=before;
    CHECK(scm_online_ingest(&predicted,predicted.config.source_id,0,&input,0,&w)==0,
          "large-factor independent prediction is valid");
    after=before;
    CHECK(scm_online_ingest(&after,after.config.source_id,0,&input,1,&w)==0,
          "staged correction failure retains accepted known interval");
    CHECK(after.rejected_voltage_count==1&&(after.flags&SCM_ONLINE_FLAG_UPDATE_REJECTED),
          "overflowing innovation variance is explicitly rejected");
    CHECK(!memcmp(after.mean,predicted.mean,sizeof(after.mean))&&
          !memcmp(after.factor,predicted.factor,sizeof(after.factor)),
          "live belief retains exact prediction after a partially mutated trial factor");
    CHECK(memcmp(w.candidate.factor,predicted.factor,sizeof(predicted.factor))!=0,
          "failure fixture reaches trial-factor mutation before rejection");
    CHECK(after.next_index==1&&after.prediction_count==1&&after.voltage_count==1&&
          after.elapsed_s==input.dt&&after.evidence_next_index==0&&!after.has_voltage,
          "staged failure advances physical ledger but does not fabricate evidence");
    CHECK(scm_online_validate(&after)==0,"retained prediction remains checkpoint-valid");
}

static void reject_atomic(scm_online *s,const unsigned char *id,uint64_t index,
    scm_sample input,int present,int wanted,const char *label)
{
    scm_online before=*s;scm_online_workspace w;
    CHECK(scm_online_ingest(s,id,index,&input,present,&w)==wanted,label);
    CHECK(!memcmp(&before,s,sizeof(before)),"rejected input is byte-atomic");
}

static void lifecycle(void)
{
    scm_online s,initial,before;scm_online_workspace w;scm_online_query_result q;
    scm_online_config c=config(),bad=c;scm_sample input={.027,.04,3.8};unsigned char wrong[32]={0};
    uint64_t count,index;double elapsed;
    prior(&s);initial=s;
    CHECK(scm_online_query(&s,&q)==0&&!q.point_available&&!q.capacity_available&&!q.local_ranges_available,
          "initial public prior is explicitly unavailable");
    bad.sigma_V=0;before=s;
    CHECK(scm_online_init(&s,&bad)==SCM_ONLINE_ERR_ARGUMENT&&!memcmp(&s,&before,sizeof(s)),"invalid init is atomic");
    reject_atomic(&s,wrong,0,input,1,SCM_ONLINE_ERR_SOURCE,"wrong source rejected");
    reject_atomic(&s,c.source_id,1,input,1,SCM_ONLINE_ERR_ORDER,"out of order rejected");
    input.dt=-1;reject_atomic(&s,c.source_id,0,input,1,SCM_ONLINE_ERR_DOMAIN,"negative dt rejected");
    input.dt=1.01;reject_atomic(&s,c.source_id,0,input,1,SCM_ONLINE_ERR_DOMAIN,"unsupported dt rejected");
    input.dt=.027;input.current=.251;reject_atomic(&s,c.source_id,0,input,1,SCM_ONLINE_ERR_DOMAIN,"unsupported current rejected");
    input.current=NAN;reject_atomic(&s,c.source_id,0,input,1,SCM_ONLINE_ERR_NONFINITE,"nonfinite current rejected");
    input.current=.04;input.voltage=NAN;
    reject_atomic(&s,c.source_id,0,input,1,SCM_ONLINE_ERR_NONFINITE,"present NaN voltage rejected");
    CHECK(scm_online_ingest(&s,c.source_id,0,&input,0,&w)==0,"missing V retains known prediction");
    CHECK(s.next_index==1&&s.prediction_count==1&&s.missing_voltage_count==1&&s.elapsed_s==input.dt,
          "known interval chronology and missing voltage count retained");
    CHECK(scm_online_query(&s,&q)==0&&!q.point_available,"missing voltage alone does not invent learned point");
    input.voltage=s.last_prediction_V;
    CHECK(scm_online_ingest(&s,c.source_id,1,&input,1,&w)==0,"voltage update creates local belief");
    CHECK(scm_online_query(&s,&q)==0&&q.point_available&&q.capacity_available&&q.local_ranges_available,
          "query exposes conditioned belief and ranges separately");
    reject_atomic(&s,c.source_id,1,input,1,SCM_ONLINE_ERR_ORDER,"duplicate input rejected");
    before=s;input.dt=0;input.current=0;input.voltage=DBL_MAX;
    CHECK(scm_online_ingest(&s,c.source_id,s.next_index,&input,1,&w)==0,"unusable finite voltage preserves prediction");
    CHECK(!memcmp(before.mean,s.mean,sizeof(s.mean))&&!memcmp(before.factor,s.factor,sizeof(s.factor)),
          "numerical voltage rejection does not shrink or move prediction-only belief");
    CHECK(s.rejected_voltage_count==before.rejected_voltage_count+1&&
          (s.flags&SCM_ONLINE_FLAG_UPDATE_REJECTED)&&s.evidence_next_index==before.evidence_next_index,
          "rejected correction leaves evidence position and exposes cause");
    CHECK(scm_online_mark_unknown_gap(&s)==SCM_ONLINE_ERR_RECOVERY_REQUIRED,"unknown gap latches recovery");
    CHECK(scm_online_query(&s,&q)==0&&!q.point_available&&!q.capacity_available&&!q.local_ranges_available,
          "recovery latch withholds current estimates");
    input.voltage=3.8;reject_atomic(&s,c.source_id,s.next_index,input,1,SCM_ONLINE_ERR_RECOVERY_REQUIRED,"gap blocks ingestion");
    index=s.next_index;elapsed=s.elapsed_s;count=s.voltage_count;
    CHECK(scm_online_cold_reset(&s)==0,"explicit cold reset");
    CHECK(s.next_index==index&&s.epoch_begin==index&&s.elapsed_s==elapsed&&s.epoch_elapsed_s==0&&s.voltage_count==count,
          "cold reset preserves known absolute ledger and cumulative counters");
    CHECK(!memcmp(s.mean,initial.mean,sizeof(s.mean))&&!memcmp(s.factor,initial.factor,sizeof(s.factor))&&
          s.flags==SCM_ONLINE_FLAG_HISTORY_LOST&&!s.has_voltage,"cold reset contains only public prior");
    CHECK(s.last_gain_scale==1&&s.last_max_gain_scale==1&&s.minimum_gain_scale==1&&
          !s.last_limited_mask&&!s.last_blocked_mask,"cold reset clears component gain diagnostics");
    CHECK(scm_online_query(&s,&q)==0&&!q.point_available,"reset reports unavailable point");
    CHECK(scm_online_validate(&s)==0,"cold state validates");

    prior(&s);s.mean[11]=0;before=s;input.dt=1;input.current=.25;input.voltage=3.;
    CHECK(scm_online_ingest(&s,c.source_id,0,&input,1,&w)==SCM_ONLINE_ACCEPTED_RECOVERY,"prediction domain exit consumes known interval explicitly");
    CHECK(s.next_index==1&&s.elapsed_s==1&&s.rejected_voltage_count==1&&
          (s.flags&SCM_ONLINE_FLAG_MODEL_UNAVAILABLE)&&!s.prediction_valid,
          "domain exit advances ledger and marks model unavailable");
    CHECK(!memcmp(s.mean,before.mean,sizeof(s.mean))&&!memcmp(s.factor,before.factor,sizeof(s.factor)),
          "last valid belief retained without claiming it as current");
    CHECK(scm_online_query(&s,&q)==0&&!q.point_available&&scm_online_validate(&s)==0,"unavailable propagated state remains valid checkpoint content");

    prior(&s);s.next_index=s.prediction_count=s.missing_voltage_count=s.epoch_begin=s.evidence_next_index=UINT64_MAX;
    reject_atomic(&s,c.source_id,UINT64_MAX,input,0,SCM_ONLINE_ERR_OVERFLOW,"sequence counter cannot wrap");
    prior(&s);s.elapsed_s=s.epoch_elapsed_s=1e300;
    reject_atomic(&s,c.source_id,0,input,0,SCM_ONLINE_ERR_OVERFLOW,"nonadvancing floating clock rejects explicitly");
    prior(&s);s.cold_resets=UINT64_MAX;s.flags=SCM_ONLINE_FLAG_HISTORY_LOST;before=s;
    CHECK(scm_online_cold_reset(&s)==SCM_ONLINE_ERR_OVERFLOW&&!memcmp(&before,&s,sizeof(s)),"reset counter cannot wrap");
    prior(&s);s.factor[3]=INFINITY;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"nonfinite decoded factor rejected");
    prior(&s);s.factor[AT(0,1)]=1e-10;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"nonlower decoded factor rejected");
    prior(&s);s.factor[AT(0,0)]=-.1;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"negative diagonal rejected");
    prior(&s);s.last_limited_mask=1u<<D;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"out-of-range diagnostic mask rejected");
    prior(&s);s.last_blocked_mask=1;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"blocked mask without limited component rejected");
    prior(&s);s.last_max_gain_scale=.5;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"reversed multiplier extrema rejected");
    prior(&s);s.evidence_next_index=1;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"future evidence position rejected");
    prior(&s);s.prediction_count=1;CHECK(scm_online_validate(&s)==SCM_ONLINE_ERR_STATE,"inconsistent decoded ledger rejected");
}

int main(void)
{
    int kind;prediction_and_derivatives();for(kind=0;kind<10;kind++)joseph_case(kind);
    staged_failure();lifecycle();
    printf("{\"test\":\"bounded_online_core\",\"checks\":%d,\"failures\":%d,"
        "\"max_prediction_error\":%.17g,\"max_factor_derivative_error\":%.17g,\"max_dense_Joseph_error\":%.17g,"
        "\"state_bytes\":%zu,\"workspace_bytes\":%zu,\"query_bytes\":%zu,\"config_bytes\":%zu,"
        "\"optimizer_calls\":0,\"primary_streams\":0}\n",checks,failures,max_prediction_error,max_factor_derivative_error,
        max_joseph_error,sizeof(scm_online),sizeof(scm_online_workspace),sizeof(scm_online_query_result),sizeof(scm_online_config));
    return failures?1:0;
}
