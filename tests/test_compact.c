#include "../tools/compact_compare.h"
#include <float.h>
#include <inttypes.h>
#include <stdio.h>

static int failures;
static uint64_t checks;
static compact_comparison comparison;
#define CHECK(c,m) do { checks++;if(!(c)){fprintf(stderr,"FAIL compact: %s\n",m);failures++;} } while(0)

/* Host-only comparison and saved failure witnesses, excluded from compact
 * subsystem accounting. Ingestion itself needs no history or extra bank. */
static scm_evidence old_e,saved_old_e;
static scm_compact_evidence new_e,saved_new_e;
static scm_remainder old_r,saved_old_r;
static scm_compact_remainder new_r,saved_new_r;
static scm_evidence_workspace old_ew;
static scm_compact_evidence_workspace new_ew;
static scm_remainder_workspace old_rw;
static scm_compact_remainder_workspace new_rw;
static scm_evidence_factor old_snapshot,new_snapshot;

static scm_evidence_config configuration(int modes,uint64_t cap)
{
    scm_evidence_config c;const double tau[3]={.05,.5,5};
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
static void init_pair(const scm_evidence_config *c)
{
    CHECK(scm_evidence_init(&old_e,c)==0,"reference init");
    CHECK(scm_compact_evidence_init(&new_e,c)==0,"compact init");
    CHECK(scm_remainder_init(&old_r,c)==0,"reference remainder init");
    CHECK(scm_compact_remainder_init(&new_r,c)==0,"compact remainder init");
    CHECK(new_e.config==c && new_r.config==c,"one shared configuration");
}
static void compare_pair(void)
{
    compact_compare_evidence(&comparison,&old_e,&new_e);
    compact_compare_remainder(&comparison,&old_r,&new_r,&old_e,&new_e);
}
static void saved_pair(void)
{
    saved_old_e=old_e;saved_new_e=new_e;saved_old_r=old_r;saved_new_r=new_r;
}
static void unchanged_pair(void)
{
    CHECK(!memcmp(&old_e,&saved_old_e,sizeof(old_e)),"reference evidence failure atomic");
    CHECK(!memcmp(&new_e,&saved_new_e,sizeof(new_e)),"compact evidence failure atomic");
    CHECK(!memcmp(&old_r,&saved_old_r,sizeof(old_r)),"reference remainder failure atomic");
    CHECK(!memcmp(&new_r,&saved_new_r,sizeof(new_r)),"compact remainder failure atomic");
}
static void rejected_pair(const unsigned char *id,uint64_t index,const scm_sample *s,int expected)
{
    int a,b;saved_pair();
    a=scm_remainder_evidence_push(&old_e,&old_r,id,index,s,&old_ew,&old_rw);
    b=scm_compact_remainder_evidence_push(&new_e,&new_r,id,index,s,&new_ew,&new_rw);
    if(a!=expected || b!=expected)fprintf(stderr,"rejected pair index=%" PRIu64 " expected=%d reference=%d compact=%d dt=%g voltage=%g\n",index,expected,a,b,s->dt,s->voltage);
    CHECK(a==expected && b==expected,"paired rejection/error precedence");unchanged_pair();
}
static void snapshot_pair(void)
{
    saved_pair();
    CHECK(scm_evidence_snapshot(&old_e,&old_snapshot,&old_ew)==0,"reference snapshot");
    CHECK(scm_compact_evidence_snapshot(&new_e,&new_snapshot,&new_ew)==0,"compact snapshot");
    compact_compare_factor(&comparison,&old_snapshot,&new_snapshot);unchanged_pair();
    CHECK(scm_compact_evidence_snapshot_into(&new_e,&new_snapshot,new_ew.row)==0,"scratch snapshot");
    compact_compare_factor(&comparison,&old_snapshot,&new_snapshot);unchanged_pair();
}
static void query_pair(const double *delta,double budget)
{
    scm_remainder_result a,b;int rc1,rc2;
    rc1=scm_remainder_query(&old_r,&old_e,delta,budget,&a);
    rc2=scm_compact_remainder_query(&new_r,&new_e,delta,budget,&b);
    CHECK(rc1==rc2,"query result status parity");
    compact_compare_result(&comparison,&a,&b);
    CHECK(scm_evidence_check_candidate(&old_e,delta)==scm_compact_evidence_check_candidate(&new_e,delta),
          "candidate support and radius parity");
}
static void chronology(int modes)
{
    scm_evidence_config c=configuration(modes,17);
    scm_model_state generator;scm_model_row row;
    const double dt[7]={0,.02,.05,.13,.5,2,10};
    double delta[16]={0};int k;
    init_pair(&c);compare_pair();CHECK(scm_model_init(&generator,modes,c.theta)==0,"fixture generator");
    for(k=0;k<360;k++) {
        scm_sample s;double mu;
        s.dt=dt[k%7];s.current=k<180?(k%5?.06:0):(k%4?-.04:.03);
        CHECK(scm_model_step(&generator,NULL,s.dt,s.current,&row)==0,"fixture propagation");
        CHECK(scm_model_predict(&row,modes,c.alpha,&mu,NULL)==0,"fixture prediction");
        s.voltage=mu+c.sigma*(sin(.71*k)+.1*cos(.17*k));
        CHECK(scm_remainder_evidence_push(&old_e,&old_r,c.source_id,(uint64_t)k,&s,&old_ew,&old_rw)==0,"reference paired push");
        CHECK(scm_compact_remainder_evidence_push(&new_e,&new_r,c.source_id,(uint64_t)k,&s,&new_ew,&new_rw)==0,"compact paired push");
        compare_pair();
        if(k%37==0){snapshot_pair();query_pair(delta,.1);}
        if(k==178) {
            CHECK(scm_evidence_seal(&old_e,&old_ew)==0,"reference manual seal");
            CHECK(scm_compact_evidence_seal(&new_e,&new_ew)==0,"compact manual seal");
            compare_pair();
        }
    }
    snapshot_pair();delta[modes+2]=.005;delta[modes+3]=.0025;query_pair(delta,.1);
    delta[modes+3]=.3;query_pair(delta,.1);delta[modes+3]=NAN;query_pair(delta,.1);
    memset(delta,0,sizeof(delta));query_pair(delta,-1);
    CHECK(scm_evidence_seal(&old_e,&old_ew)==0 && scm_compact_evidence_seal(&new_e,&new_ew)==0,"final seal");
    compare_pair();saved_pair();
    CHECK(scm_evidence_seal(&old_e,&old_ew)==0 && scm_compact_evidence_seal(&new_e,&new_ew)==0,"empty seal");
    unchanged_pair();
}
static void failures_and_binding(void)
{
    scm_evidence_config c=configuration(3,1),bad;
    scm_sample s={1./35.,.04,3.8};unsigned char other[32]={0};double delta[16]={0};
    scm_remainder_result out;scm_compact_evidence foreign;
    init_pair(&c);
    CHECK(scm_remainder_evidence_push(&old_e,&old_r,c.source_id,0,&s,&old_ew,&old_rw)==0,"first reference row");
    CHECK(scm_compact_remainder_evidence_push(&new_e,&new_r,c.source_id,0,&s,&new_ew,&new_rw)==0,"first compact row");
    rejected_pair(c.source_id,0,&s,SCM_REMAINDER_ERR_ORDER);
    rejected_pair(c.source_id,2,&s,SCM_REMAINDER_ERR_ORDER);
    rejected_pair(other,1,&s,SCM_REMAINDER_ERR_SOURCE);
    s.dt=-1;rejected_pair(c.source_id,1,&s,SCM_REMAINDER_ERR_ARGUMENT);
    s.dt=NAN;rejected_pair(c.source_id,1,&s,SCM_REMAINDER_ERR_NONFINITE);
    s.dt=1e7;rejected_pair(c.source_id,1,&s,SCM_REMAINDER_ERR_DOMAIN);
    s.dt=1./35.;s.voltage=NAN;rejected_pair(c.source_id,1,&s,SCM_REMAINDER_ERR_NONFINITE);
    s.voltage=DBL_MAX;rejected_pair(c.source_id,1,&s,SCM_EVIDENCE_ERR_NONFINITE);
    s.voltage=3.8;old_e.events_completed=new_e.events_completed=UINT64_MAX;
    rejected_pair(c.source_id,1,&s,SCM_EVIDENCE_ERR_OVERFLOW);
    old_e.events_completed=new_e.events_completed=0;
    old_e.residual_flagged_events=new_e.residual_flagged_events=UINT64_MAX;
    rejected_pair(c.source_id,1,&s,SCM_EVIDENCE_ERR_OVERFLOW);
    old_e.residual_flagged_events=new_e.residual_flagged_events=0;
    old_e.next_index=new_e.next_index=old_r.next_index=new_r.next_index=UINT64_MAX;
    old_e.history.samples=new_e.history.samples=UINT64_MAX-old_e.event.samples;
    rejected_pair(c.source_id,UINT64_MAX,&s,SCM_REMAINDER_ERR_OVERFLOW);
    init_pair(&c);saved_pair();
    bad=c;bad.sigma=0;
    CHECK(scm_evidence_init(&old_e,&bad)==SCM_EVIDENCE_ERR_ARGUMENT && scm_compact_evidence_init(&new_e,&bad)==SCM_EVIDENCE_ERR_ARGUMENT,"invalid init parity");
    unchanged_pair();bad=c;bad.radius[0]=1e308;
    CHECK(scm_remainder_init(&old_r,&bad)==SCM_REMAINDER_ERR_NONFINITE && scm_compact_remainder_init(&new_r,&bad)==SCM_REMAINDER_ERR_NONFINITE,"overflow remainder init parity");
    unchanged_pair();
    CHECK(scm_remainder_evidence_push(&old_e,&old_r,c.source_id,0,&s,&old_ew,&old_rw)==0 &&
          scm_compact_remainder_evidence_push(&new_e,&new_r,c.source_id,0,&s,&new_ew,&new_rw)==0,"fresh pair binding");
    foreign=new_e;
    CHECK(scm_compact_remainder_query(&new_r,&foreign,delta,.1,&out)==SCM_REMAINDER_ERR_MISMATCH,"foreign shallow copy rejected");
    CHECK(scm_evidence_push(&old_e,c.source_id,1,&s,&old_ew)==0 &&
          scm_compact_evidence_push(&new_e,c.source_id,1,&s,&new_ew)==0,"evidence-only advance");
    query_pair(delta,.1);rejected_pair(c.source_id,2,&s,SCM_REMAINDER_ERR_MISMATCH);
    init_pair(&c);
    CHECK(scm_evidence_push(&old_e,c.source_id,0,&s,&old_ew)==0 && scm_compact_evidence_push(&new_e,c.source_id,0,&s,&new_ew)==0,"independent evidence");
    CHECK(scm_remainder_push(&old_r,c.source_id,0,&s,&old_rw)==0 && scm_compact_remainder_push(&new_r,c.source_id,0,&s,&new_rw)==0,"independent envelope");
    compare_pair();query_pair(delta,.1);rejected_pair(c.source_id,1,&s,SCM_REMAINDER_ERR_MISMATCH);
}
static void pwl_and_tiny_rows(void)
{
    static const double z[3]={0,.68,1},u[3]={3,3.8,4.2},flat[3]={3.8,3.8,3.8};
    scm_evidence_config c;scm_sample s={0,0,3.8};int k,mode;
    for(mode=0;mode<4;mode++) {
        c=configuration(3,1);c.ocv.n=3;c.ocv.z=z;c.ocv.u=mode?flat:u;
        if(mode) {
            memset(c.alpha,0,sizeof(c.alpha));c.sigma=mode==3?1.:DBL_MAX;
            for(k=0;k<16;k++)c.scale[k]=mode==3?nextafter(0.,1.):DBL_MIN;
        }
        CHECK(scm_evidence_init(&old_e,&c)==0 && scm_compact_evidence_init(&new_e,&c)==0,"PWL/tiny row init");
        for(k=0;k<4;k++) {
            s.dt=mode?0:((k==2)?1./35.:0);s.current=mode?0:(k%2?.02:-.02);
            s.voltage=mode==2?DBL_MAX:mode==3?3.9:3.8;
            CHECK(scm_evidence_push(&old_e,c.source_id,(uint64_t)k,&s,&old_ew)==0,"PWL/tiny reference row");
            CHECK(scm_compact_evidence_push(&new_e,c.source_id,(uint64_t)k,&s,&new_ew)==0,"PWL/tiny compact row");
            compact_compare_evidence(&comparison,&old_e,&new_e);
        }
        snapshot_pair();
        if(mode==1)for(k=0;k<SCM_EVIDENCE_PACKED;k++)CHECK(new_snapshot.upper[k]==0,"allzero row retained by count only");
        if(mode==2)CHECK(new_snapshot.upper[scm_evidence_packed_index(16,16)]>0,"residual-only row preserved");
    }
}
static void decaying_subnormal(void)
{
    scm_evidence_config c=configuration(3,35);scm_model_state model;scm_model_row row;
    scm_sample s={1./35.,.02,0};int k,subnormals=0;double mu;
    init_pair(&c);CHECK(scm_model_init(&model,3,c.theta)==0,"subnormal fixture model");
    for(k=0;k<3500;k++) {
        CHECK(scm_model_step(&model,NULL,s.dt,s.current,&row)==0 && scm_model_predict(&row,3,c.alpha,&mu,NULL)==0,"subnormal fixture propagation");
        if(model.a[0]!=0 && fabs(model.a[0])<DBL_MIN)subnormals++;
        s.voltage=mu+c.sigma*(cos(.43*k)+.2*sin(.11*k));
        CHECK(scm_remainder_evidence_push(&old_e,&old_r,c.source_id,(uint64_t)k,&s,&old_ew,&old_rw)==0 &&
              scm_compact_remainder_evidence_push(&new_e,&new_r,c.source_id,(uint64_t)k,&s,&new_ew,&new_rw)==0,"subnormal paired rows");
        compare_pair();
    }
    CHECK(subnormals>10,"subnormal entering-state responses exercised");snapshot_pair();
}
int main(void)
{
    int n;for(n=1;n<=3;n++)chronology(n);
    failures_and_binding();pwl_and_tiny_rows();decaying_subnormal();
    CHECK(comparison.mismatches==0,"exact field-by-field core parity");
    printf("{\"schema\":\"mumble_compact_unit_v1\",\"checks\":%" PRIu64 ",\"failed\":%d,\"numeric_comparisons\":%" PRIu64 ",\"scalar_comparisons\":%" PRIu64 ",\"numeric_mismatches\":%" PRIu64 ",\"bit_differences\":%" PRIu64 ",\"max_absolute_difference\":%.17g,\"first_mismatch\":\"%s\"}\n",
           checks,failures,comparison.double_checks,comparison.scalar_checks,comparison.mismatches,
           comparison.bit_differences,comparison.max_absolute_difference,comparison.first_mismatch?comparison.first_mismatch:"");
    return failures?1:0;
}
