#include "scm_evidence.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(c,m) do { if(!(c)) { fprintf(stderr,"FAIL evidence: %s\n",m); failures++; } } while(0)

static scm_evidence_config configuration(int modes,uint64_t cap)
{
    scm_evidence_config c;
    const double taus[3]={.05,.5,5};
    int i,nt=scm_model_ntheta(modes),na=scm_model_nalpha(modes);
    memset(&c,0,sizeof(c));c.modes=modes;c.sigma=.001;c.max_event_samples=cap;
    c.residual_rms_limit_sigma=4;
    c.source_id[0]=41;c.source_id[31]=19;
    for(i=0;i<modes;i++)c.theta[i]=log(modes==3?taus[i]:(i?5.:.05));
    c.theta[modes]=log(150.);c.theta[modes+1]=log(300.);
    c.theta[modes+2]=.68;c.theta[modes+3]=log(.06);
    c.alpha[0]=.12;
    for(i=0;i<modes;i++){c.alpha[i+1]=.2;c.alpha[modes+2+i]=.002*(i+1);}
    c.alpha[modes+1]=.025;c.alpha[2+2*modes]=.005;
    for(i=0;i<nt;i++)c.scale[i]=i==modes+2?.1:1.;
    for(i=0;i<na;i++)c.scale[nt+i]=i<=modes?.2:.03;
    for(i=0;i<nt+na;i++)c.radius[i]=1.;
    return c;
}

static int near(double a,double b,double relative)
{
    return fabs(a-b)<=relative*fmax(1.,fmax(fabs(a),fabs(b)));
}

static void check_affine_and_partition(int modes)
{
    scm_evidence_config ca=configuration(modes,37),cb=configuration(modes,1);
    scm_evidence a,b,saved;
    scm_evidence_workspace wa,wb;
    scm_evidence_factor fa,fb;
    scm_model_state model;
    scm_model_row row;
    double h[SCM_EVIDENCE_DIM*SCM_EVIDENCE_DIM]={0},g[SCM_EVIDENCE_DIM]={0};
    double expected_h[SCM_EVIDENCE_DIM*SCM_EVIDENCE_DIM]={0},expected_g[SCM_EVIDENCE_DIM]={0};
    double j[SCM_EVIDENCE_DIM],jt[SCM_MAX_THETA],delta[SCM_EVIDENCE_DIM];
    double cost=0,expected_cost=0,expected_zero=0;
    int k,i,l,nt=scm_model_ntheta(modes),na=scm_model_nalpha(modes),d=nt+na;
    CHECK(scm_evidence_init(&a,&ca)==0,"initialize first partition");
    CHECK(scm_evidence_init(&b,&cb)==0,"initialize samplewise partition");
    CHECK(scm_model_init(&model,modes,ca.theta)==0,"direct carried model");
    for(i=0;i<d;i++)delta[i]=.003*cos((double)i);
    for(k=0;k<1200;k++) {
        scm_sample sample;
        double mu,r,affine;
        sample.dt=k%17==0?.023:1./35.;
        sample.current=k<80?0.:k<600?((k/50)%2?.025:.075):((k/80)%2?-.04:.02);
        CHECK(scm_model_step(&model,NULL,sample.dt,sample.current,&row)==0,"direct model step");
        CHECK(scm_model_predict(&row,modes,ca.alpha,&mu,jt)==0,"direct prediction");
        sample.voltage=mu+ca.sigma*(sin(.73*k)+.3*cos(.11*k));
        r=(sample.voltage-mu)/ca.sigma;affine=-r;
        for(i=0;i<nt;i++)j[i]=jt[i]*ca.scale[i]/ca.sigma;
        for(i=0;i<na;i++)j[nt+i]=row.X[i]*ca.scale[nt+i]/ca.sigma;
        for(i=0;i<d;i++) {
            affine+=j[i]*delta[i];expected_g[i]-=j[i]*r;
            for(l=0;l<d;l++)expected_h[i*d+l]+=j[i]*j[l];
        }
        expected_cost+=.5*affine*affine;expected_zero+=.5*r*r;
        CHECK(scm_evidence_push(&a,ca.source_id,(uint64_t)k,&sample,&wa)==0,"stream row");
        CHECK(scm_evidence_push(&b,cb.source_id,(uint64_t)k,&sample,&wb)==0,"stream partitioned row");
        CHECK(a.model.elapsed==model.elapsed && a.model.charge_Ah==model.charge_Ah,"actual dt and charge carried");
        if(k==599) {
            CHECK(scm_evidence_snapshot(&a,&fa,&wa)==0,"unexcited prefix snapshot");
            CHECK(scm_evidence_factor_normal(&fa,h,g,&cost)==0,"unexcited prefix normal");
            CHECK(h[(modes+1)*d+modes+1]==0 && g[modes+1]==0,"missing sign remains exact null");
            CHECK(a.excitation==1u,"positive throughput only");
        }
    }
    saved=a;
    CHECK(scm_evidence_snapshot(&a,&fa,&wa)==0,"final factor");
    CHECK(memcmp(&saved,&a,sizeof(a))==0,"snapshot leaves bank unchanged");
    CHECK(scm_evidence_snapshot(&b,&fb,&wb)==0,"partitioned factor");
    CHECK(fa.samples==1200 && fb.samples==1200,"each observation counted once");
    CHECK(scm_evidence_factor_normal(&fa,h,g,&cost)==0,"normal extraction");
    CHECK(near(cost,expected_zero,2e-12),"residual constant preserved");
    CHECK(near(scm_evidence_factor_cost(&fa,delta),expected_cost,2e-12),"whole affine objective preserved");
    CHECK(near(scm_evidence_factor_cost(&fb,delta),expected_cost,2e-12),"event partition leaves objective invariant");
    for(i=0;i<d;i++) {
        CHECK(near(g[i],expected_g[i],2e-10),"gradient matches raw rows");
        for(l=0;l<d;l++)CHECK(near(h[i*d+l],expected_h[i*d+l],2e-11),"normal matches raw rows");
    }
    CHECK(scm_evidence_check_candidate(&a,delta)==0,"nearby candidate passes operating screen");
    CHECK(a.model.ha==b.model.ha && a.model.hb==b.model.hb,"hysteresis not reset by event boundary");
    CHECK(a.model.f[0]==b.model.f[0] && a.model.df[0]==b.model.df[0],"RC state and sensitivities carried");
    CHECK(a.excitation==3u,"both transported signs recognized");
    CHECK(scm_evidence_seal(&a,&wa)==0,"explicit final seal");
    CHECK(a.history.samples==1200 && a.event.samples==0,"seal moves evidence without duplication");
    saved=a;
    CHECK(scm_evidence_seal(&a,&wa)==0 && memcmp(&saved,&a,sizeof(a))==0,"empty seal is idempotent");
}

static void check_errors(void)
{
    scm_evidence_config c=configuration(3,8),invalid;
    scm_evidence e,saved;
    scm_evidence_workspace w;
    scm_sample sample={1./35.,.03,3.8};
    unsigned char other[SCM_EVIDENCE_SOURCE_BYTES]={0};
    double delta[SCM_EVIDENCE_DIM]={0};
    CHECK(scm_evidence_init(&e,&c)==0,"error fixture init");
    CHECK(scm_evidence_push(&e,c.source_id,0,&sample,&w)==0,"error fixture first row");
    saved=e;
    CHECK(scm_evidence_push(&e,c.source_id,0,&sample,&w)==SCM_EVIDENCE_ERR_ORDER,"duplicate rejected");
    CHECK(memcmp(&saved,&e,sizeof(e))==0,"duplicate atomic");
    CHECK(scm_evidence_push(&e,c.source_id,2,&sample,&w)==SCM_EVIDENCE_ERR_ORDER,"gap rejected");
    CHECK(memcmp(&saved,&e,sizeof(e))==0,"gap atomic");
    CHECK(scm_evidence_push(&e,other,1,&sample,&w)==SCM_EVIDENCE_ERR_SOURCE,"wrong source rejected");
    CHECK(memcmp(&saved,&e,sizeof(e))==0,"source error atomic");
    sample.voltage=NAN;
    CHECK(scm_evidence_push(&e,c.source_id,1,&sample,&w)==SCM_EVIDENCE_ERR_NONFINITE,"nonfinite rejected");
    CHECK(memcmp(&saved,&e,sizeof(e))==0,"nonfinite error atomic");
    sample.voltage=3.8;sample.dt=1e7;
    CHECK(scm_evidence_push(&e,c.source_id,1,&sample,&w)==SCM_EVIDENCE_ERR_DOMAIN,"trajectory domain rejected");
    CHECK(memcmp(&saved,&e,sizeof(e))==0,"domain after staged seal atomic");
    sample.dt=1./35.;sample.current=0;
    e.next_index=UINT64_MAX;saved=e;
    CHECK(scm_evidence_push(&e,c.source_id,UINT64_MAX,&sample,&w)==SCM_EVIDENCE_ERR_OVERFLOW,"sample counter overflow rejected");
    CHECK(memcmp(&saved,&e,sizeof(e))==0,"overflow atomic");
    CHECK(scm_evidence_init(&e,&c)==0,"restore valid fixture");
    saved=e;
    invalid=c;invalid.sigma=0;
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_ARGUMENT,"zero sigma rejected");
    CHECK(memcmp(&saved,&e,sizeof(e))==0,"failed init atomic");
    invalid=c;invalid.scale[1]=NAN;
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_ARGUMENT,"nonfinite scale rejected");
    invalid=c;invalid.radius[1]=-.1;
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_ARGUMENT,"negative radius rejected");
    invalid=c;invalid.max_event_samples=0;
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_ARGUMENT,"zero event capacity rejected");
    invalid=c;invalid.residual_rms_limit_sigma=0;
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_ARGUMENT,"zero residual monitor limit rejected");
    invalid=c;invalid.alpha[0]=-1e-3;
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_DOMAIN,"negative resistance rejected");
    invalid=c;invalid.alpha[8]=invalid.alpha[4]+.001;
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_DOMAIN,"invalid coupled amplitude rejected");
    invalid=c;invalid.theta[6]=log(.2);
    CHECK(scm_evidence_init(&e,&invalid)==SCM_EVIDENCE_ERR_DOMAIN,"capacity support enforced");
    delta[0]=1.1;
    CHECK(scm_evidence_check_candidate(&e,delta)==SCM_EVIDENCE_ERR_RADIUS,"outside chart rejected");
    delta[0]=0;delta[7]=-.7;
    CHECK(scm_evidence_check_candidate(&e,delta)==SCM_EVIDENCE_ERR_DOMAIN,"negative candidate resistance rejected");
    delta[7]=0;delta[15]=1.;
    CHECK(scm_evidence_check_candidate(&e,delta)==SCM_EVIDENCE_ERR_DOMAIN,"candidate h support enforced");
    delta[15]=0;delta[1]=NAN;
    CHECK(scm_evidence_check_candidate(&e,delta)==SCM_EVIDENCE_ERR_NONFINITE,"nonfinite candidate rejected");
}

static void check_quiet_and_residual_constant(void)
{
    scm_evidence_config c=configuration(3,10);
    scm_evidence e;
    scm_evidence_workspace w;
    scm_evidence_factor f;
    scm_sample sample={1./35.,0,3.8};
    double h[SCM_EVIDENCE_DIM*SCM_EVIDENCE_DIM],g[SCM_EVIDENCE_DIM],cost,delta[SCM_EVIDENCE_DIM]={0};
    int i;
    CHECK(scm_evidence_init(&e,&c)==0,"quiet init");
    for(i=0;i<500;i++)CHECK(scm_evidence_push(&e,c.source_id,(uint64_t)i,&sample,&w)==0,"quiet repeat");
    CHECK(scm_evidence_snapshot(&e,&f,&w)==0,"quiet factor");
    CHECK(scm_evidence_factor_normal(&f,h,g,&cost)==0,"quiet normal");
    CHECK(h[3*16+3]==0 && h[4*16+4]==0 && h[6*16+6]==0,"quiet cannot create rate or capacity direction");
    CHECK(e.excitation==0 && e.model.charge_Ah==0,"zero current freezes throughput");
    CHECK(e.residual_flagged_events>0 && e.max_event_anchor_rms_sigma>4,"large residual events flagged");
    CHECK(f.samples==500,"residual flag does not discard evidence");
    CHECK(near(scm_evidence_factor_rms_sigma(&f),sqrt(2*cost/500),1e-13),"residual monitor includes full constant");
    memset(&f,0,sizeof(f));f.dim=1;f.samples=2;
    f.upper[scm_evidence_packed_index(0,0)]=2;
    f.upper[scm_evidence_packed_index(0,1)]=3;
    f.upper[scm_evidence_packed_index(1,1)]=4;
    delta[0]=1;
    CHECK(scm_evidence_factor_cost(&f,delta)==8.5,"orthogonal residual retained at nonzero delta");
    CHECK(scm_evidence_factor_normal(&f,h,g,&cost)==0 && h[0]==4 && g[0]==-6 && cost==12.5,"augmented factor sign and residual constant");
    CHECK(scm_evidence_packed_index(0,0)==0 && scm_evidence_packed_index(16,16)==152,"fixed packed addressing");
    CHECK(scm_evidence_packed_index(2,1)==SIZE_MAX,"invalid packed addressing rejected");
}

static void check_soc_path_guard(void)
{
    scm_evidence_config c=configuration(3,100);
    scm_evidence e;
    scm_evidence_workspace w;
    scm_sample sample={1,.05,3.8};
    double delta[SCM_EVIDENCE_DIM]={0};
    int i;
    c.radius[5]=8.;c.radius[6]=2.;
    CHECK(scm_evidence_init(&e,&c)==0,"SOC path init");
    for(i=0;i<1200;i++)CHECK(scm_evidence_push(&e,c.source_id,(uint64_t)i,&sample,&w)==0,"SOC discharge segment");
    sample.current=-.05;
    for(i=1200;i<2400;i++)CHECK(scm_evidence_push(&e,c.source_id,(uint64_t)i,&sample,&w)==0,"SOC recharge segment");
    CHECK(fabs(e.model.charge_Ah)<1e-15 && e.charge_max_Ah>.016,"interior charge extremum retained");
    delta[5]=(.3-c.theta[5])/c.scale[5];delta[6]=log(.03)-c.theta[6];
    CHECK(scm_evidence_check_candidate(&e,delta)==SCM_EVIDENCE_ERR_DOMAIN,"interior SOC violation rejected despite feasible endpoint");
}

static void check_zero_interval_current(void)
{
    scm_evidence_config c=configuration(3,2);
    scm_evidence e;
    scm_evidence_workspace w;
    scm_evidence_factor f;
    scm_sample sample={0,.04,3.8};
    double h[SCM_EVIDENCE_DIM*SCM_EVIDENCE_DIM],g[SCM_EVIDENCE_DIM],cost;
    CHECK(scm_evidence_init(&e,&c)==0,"zero interval init");
    CHECK(scm_evidence_push(&e,c.source_id,0,&sample,&w)==0,"positive current at zero interval");
    sample.current=-.05;
    CHECK(scm_evidence_push(&e,c.source_id,1,&sample,&w)==0,"negative current at zero interval");
    CHECK(scm_evidence_snapshot(&e,&f,&w)==0,"zero interval snapshot");
    CHECK(scm_evidence_factor_normal(&f,h,g,&cost)==0,"zero interval normal");
    CHECK(e.excitation==0 && e.model.charge_Ah==0 && e.model.elapsed==0,"zero interval has no transported charge");
    CHECK(h[3*16+3]==0 && h[4*16+4]==0,"zero interval leaves both hysteresis rates unexcited");
    CHECK(h[7*16+7]>0,"zero interval still observes ohmic current response");
}

int main(void)
{
    int n;
    for(n=1;n<=SCM_MAX_MODES;n++)check_affine_and_partition(n);
    check_errors();check_quiet_and_residual_constant();check_soc_path_guard();
    check_zero_interval_current();
    if(failures){fprintf(stderr,"%d evidence checks failed\n",failures);return 1;}
    printf("evidence checks passed; bank=%zu workspace=%zu factor=%zu packed=%zu bytes\n",
           sizeof(scm_evidence),sizeof(scm_evidence_workspace),sizeof(scm_evidence_factor),
           (size_t)SCM_EVIDENCE_PACKED*sizeof(double));
    return 0;
}
