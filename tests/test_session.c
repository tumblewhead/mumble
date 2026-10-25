#include "scm_session.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static int checks,failures,numerical_fit_calls;
#define CHECK(c,m) do {checks++;if(!(c)){fprintf(stderr,"FAIL %s\n",m);failures++;}} while(0)

static scm_session_config configuration(void)
{
    scm_session_config c;
    scm_session_config_default(&c);memset(c.source_id,0x31,sizeof(c.source_id));
    c.max_history_samples=4096;c.schedule_count=0;return c;
}

static void rejected(scm_session *s,const unsigned char *id,uint64_t index,
    scm_sample sample,int present,int wanted,const char *label)
{
    scm_session before=*s;
    scm_sample saved[4];unsigned char flags[4];size_t n=s->count<4?s->count:4;
    if(n){memcpy(saved,s->samples,n*sizeof(*saved));memcpy(flags,s->voltage_present,n);}
    CHECK(scm_session_ingest(s,id,index,&sample,present)==wanted,label);
    CHECK(!memcmp(&before,s,sizeof(before)),"rejected input leaves every session byte unchanged");
    CHECK(!n||(!memcmp(saved,s->samples,n*sizeof(*saved))&&!memcmp(flags,s->voltage_present,n)),
          "rejected input preserves earlier journal");
}

static void ingestion_and_reset(void)
{
    scm_session s={0},before;scm_session_config c=configuration(),bad=c;
    scm_session_query_result q;scm_sample x={1./35.,.12,3.8};unsigned char wrong[32]={0};
    double total=0,charge=0;size_t old_capacity;int i;
    bad.sigma=NAN;before=s;
    CHECK(scm_session_init(&s,&bad)==SCM_SESSION_ERR_ARGUMENT&&!memcmp(&s,&before,sizeof(s)),"bad config is atomic");
    CHECK(scm_session_init(&s,&c)==0,"initialize public-prior session");
    CHECK(scm_session_query(&s,&q,NULL,NULL)==0&&q.status==SCM_SESSION_COLLECTING&&
          !q.point_available&&!q.capacity_available&&!q.assessment_available,"initial state explicitly unknown");
    CHECK(scm_session_fit(&s)==SCM_SESSION_ERR_NOT_DUE&&s.fit_attempts==0,"no unscheduled fitting");
    rejected(&s,wrong,0,x,1,SCM_SESSION_ERR_SOURCE,"source mismatch");
    rejected(&s,c.source_id,1,x,1,SCM_SESSION_ERR_ORDER,"future input rejected");
    x.dt=-1;rejected(&s,c.source_id,0,x,1,SCM_SESSION_ERR_ARGUMENT,"negative interval rejected");
    x.dt=NAN;rejected(&s,c.source_id,0,x,1,SCM_SESSION_ERR_NONFINITE,"NaN interval rejected");
    x.dt=1./35.;x.current=INFINITY;
    rejected(&s,c.source_id,0,x,1,SCM_SESSION_ERR_NONFINITE,"infinite current rejected");
    x.current=.12;x.voltage=NAN;
    rejected(&s,c.source_id,0,x,1,SCM_SESSION_ERR_NONFINITE,"present NaN voltage rejected");
    x.voltage=3.8;rejected(&s,c.source_id,0,x,2,SCM_SESSION_ERR_ARGUMENT,"malformed voltage validity rejected");
    CHECK(scm_session_ingest(&s,c.source_id,0,&x,1)==0,"first ordered observation");
    total+=x.dt;charge+=x.current*x.dt/3600.;
    rejected(&s,c.source_id,0,x,1,SCM_SESSION_ERR_ORDER,"duplicate rejected atomically");
    x.dt=0.;x.current=0.;CHECK(scm_session_ingest(&s,c.source_id,1,&x,1)==0,"zero interval retained in order");
    x.dt=.031;x.current=-.03;x.voltage=NAN;
    CHECK(scm_session_ingest(&s,c.source_id,2,&x,0)==0,"missing V ignores its payload");
    total+=x.dt;charge+=x.current*x.dt/3600.;
    CHECK(s.samples[2].voltage==0&&!s.voltage_present[2]&&s.epoch_charge_Ah==charge&&s.elapsed_total_s==total,
          "missing V retains exact known input and canonical absent value");
    CHECK(scm_session_rebuild(&s)==0&&s.model_valid,"missing V state rebuild needs no fit");
    old_capacity=s.capacity;x.dt=.0001;x.current=0;x.voltage=3.8;
    for(i=3;i<1025;i++)CHECK(scm_session_ingest(&s,c.source_id,(uint64_t)i,&x,1)==0,"ordered small growth stream");
    CHECK(s.capacity>old_capacity&&s.peak_owned_bytes==sizeof(s)+(old_capacity+s.capacity)*(sizeof(scm_sample)+1),
          "journal growth accounts old and new buffers concurrently");
    CHECK(scm_session_rebuild(&s)==0,"rebuild preserves accumulated floating-point clock order");
    total=s.elapsed_total_s;
    CHECK(scm_session_mark_unknown_gap(&s)==SCM_SESSION_ERR_RECOVERY_REQUIRED,"unknown-input gap latches recovery");
    CHECK(scm_session_query(&s,&q,NULL,NULL)==0&&q.status==SCM_SESSION_RECOVERY_REQUIRED&&
          !q.point_available&&!q.assessment_available,"recovery state cannot expose live estimates");
    rejected(&s,c.source_id,s.next_index,x,1,SCM_SESSION_ERR_RECOVERY_REQUIRED,"known replay must start from valid restore");
    CHECK(scm_session_cold_reset(&s)==0&&s.next_index==1025&&s.epoch_begin==1025&&
          s.elapsed_total_s==total&&s.epoch_start_elapsed_s==total&&s.epoch_elapsed_s==0&&s.epoch_charge_Ah==0,
          "explicit cold reset preserves known absolute position and clock");
    CHECK(s.flags==SCM_SESSION_FLAG_HISTORY_LOST&&!s.count&&!s.capacity&&!s.samples&&!s.has_fit,
          "cold reset releases history and clears entering-state inference");
    CHECK(scm_session_query(&s,&q,NULL,NULL)==0&&!q.point_available&&!q.capacity_available,
          "cold reset has no hidden-state point estimate");
    CHECK(scm_session_ingest(&s,c.source_id,s.next_index,&x,1)==0&&scm_session_rebuild(&s)==0,
          "cold epoch absolute clock reconstructs in original addition order");
    before=s;s.epoch_charge_Ah+=1.;
    CHECK(scm_session_rebuild(&s)==SCM_SESSION_ERR_STATE,"decoded inconsistent charge rejected");s=before;
    scm_session_destroy(&s);CHECK(!s.initialized&&!s.samples,"destroy clears ownership");
}

static void bounds_and_schedule(void)
{
    scm_session s={0},before;scm_session_config c=configuration();scm_sample x={.02,.1,3.8};
    c.max_history_samples=2;c.schedule_count=2;c.fit_checkpoints[0]=1;c.fit_checkpoints[1]=2;
    CHECK(scm_session_init(&s,&c)==0,"small scheduled session");
    CHECK(scm_session_advance(&s,c.source_id,0,x.dt,x.current)==0&&scm_session_fit_due(&s),"missing V still reaches exact schedule");
    rejected(&s,c.source_id,1,x,1,SCM_SESSION_ERR_NOT_DUE,"unconsumed fit prevents skipping scheduled point");
    CHECK(scm_session_fit(&s)==SCM_SESSION_ERR_MISSING_VOLTAGE&&s.fit_attempts==1&&s.fit_results==0,
          "unsupported masked fit is explicit and counted as request only");
    CHECK(scm_session_ingest(&s,c.source_id,1,&x,1)==0,"known input continues after failed request");
    before=s;s.fit_attempts=UINT64_MAX;
    CHECK(scm_session_fit(&s)==SCM_SESSION_ERR_OVERFLOW&&s.schedule_cursor==before.schedule_cursor,
          "fit counter cannot wrap or consume a checkpoint");s=before;
    CHECK(scm_session_fit(&s)==SCM_SESSION_ERR_MISSING_VOLTAGE,"absence remains explicit for whole epoch");
    rejected(&s,c.source_id,2,x,1,SCM_SESSION_ERR_OVERFLOW,"journal allocation guard rejects without eviction");
    CHECK(scm_session_cold_reset(&s)==0&&s.schedule_cursor==2&&s.fit_attempts==2&&s.last_fit_attempt_index==2,
          "cold reset skips elapsed schedule and preserves cumulative request ledger");
    before=s;s.cold_resets=UINT64_MAX;
    CHECK(scm_session_cold_reset(&s)==SCM_SESSION_ERR_OVERFLOW&&s.cold_resets==UINT64_MAX,
          "reset count cannot wrap");s=before;
    /* Fabricated ledger boundary tests counter guards without a long run. */
    s.epoch_begin=s.next_index=UINT64_MAX;
    rejected(&s,c.source_id,UINT64_MAX,x,1,SCM_SESSION_ERR_OVERFLOW,"sample ledger cannot wrap");
    scm_session_destroy(&s);
}

static void tiny_fit_and_failure(void)
{
    scm_session s={0};scm_session_config c=configuration();scm_fit_result saved,transported;
    scm_session_query_result q;scm_assessment a,expected;scm_assess_workspace w,ew;
    scm_physical plant={0};scm_physical_state state={0};scm_sample x;
    double known_charge,known_time;int i,rc,np=16;
    c.starts=1;c.max_iterations=1;c.max_history_samples=128;c.schedule_count=4;
    c.fit_checkpoints[0]=32;c.fit_checkpoints[1]=33;c.fit_checkpoints[2]=35;c.fit_checkpoints[3]=50;
    /* Synthetic values produce observations only; none enter config, start,
     * warm start, assessment, or reset. This is a tiny lifecycle fixture. */
    plant.modes=3;plant.Q=.065;plant.R0=.12;plant.H=.02;plant.gamma_plus=100;plant.gamma_minus=250;
    plant.R[0]=plant.R[1]=plant.R[2]=.2;plant.tau[0]=.04;plant.tau[1]=.5;plant.tau[2]=5;
    state.z=.75;state.h=.2;state.v[0]=.01;state.v[1]=-.005;
    CHECK(scm_session_init(&s,&c)==0,"tiny all-unknown 3RC fit setup");
    for(i=0;i<32;i++) {
        x.dt=1./35.+(i%3)*.00001;x.current=i%8<4?.1:-.05;
        CHECK(scm_physical_step(&plant,&state,NULL,x.dt,x.current,&x.voltage)==0,"fixture observation generated");
        CHECK(scm_session_ingest(&s,c.source_id,(uint64_t)i,&x,1)==0,"tiny fixture ordered ingest");
    }
    numerical_fit_calls++;rc=scm_session_fit(&s);
    CHECK(rc==0&&s.has_fit&&s.fit_attempts==1&&s.fit_results==1,"tiny optimizer returns a complete numerical result");
    if(rc){scm_session_destroy(&s);return;}
    saved=s.fit;
    CHECK(scm_session_query(&s,&q,&a,&w)==0&&q.point_available&&q.capacity_available&&q.assessment_available&&
          q.evidence_current&&q.evidence_next_index==32,"fit exposes point and separately qualified evidence");
    CHECK(q.last_problem_auxiliary_bytes==saved.retained_bytes-saved.data_bytes&&
          q.peak_fit_owned_bytes==q.owned_bytes+saved.retained_bytes-saved.data_bytes,
          "borrowed raw observations are not counted twice in fit memory");
    if(saved.status!=0)for(i=0;i<a.target_count;i++)
        CHECK(!a.targets[i].has_local_range,"nonconverged fit cannot claim trusted local ranges");
    x.dt=.027;x.current=.04;x.voltage=DBL_MAX;
    CHECK(scm_session_ingest(&s,c.source_id,32,&x,1)==0,"finite but numerically unfit voltage retained as observation");
    numerical_fit_calls++;rc=scm_session_fit(&s);
    CHECK(rc==SCM_SESSION_ERR_FIT&&s.fit_attempts==2&&s.fit_results==1&&
          s.last_fit_next_index==32&&!memcmp(&saved,&s.fit,sizeof(saved)),"failed new solve preserves entire earlier result");
    CHECK(scm_session_query(&s,&q,&a,&w)==0&&q.point_available&&q.assessment_available&&
          q.evidence_age_samples==1&&!q.evidence_current&&(q.flags&SCM_SESSION_FLAG_FIT_FAILED),
          "old evidence and current known-input state remain distinct after failed fit");
    transported=s.fit;transported.charge_Ah=s.epoch_charge_Ah;transported.elapsed_physical_s=s.epoch_elapsed_s;
    CHECK(scm_assess(&transported,3,NULL,&expected,&ew)==0&&
          !memcmp(&expected,&a,sizeof(a)),"query transports the target through full earlier joint evidence");
    CHECK(a.targets[np].point==q.current_soc,"assessment and query use same current SOC target");
    x.voltage=NAN;
    CHECK(scm_session_ingest(&s,c.source_id,33,&x,0)==0,"missing voltage after fit preserves known input");
    x.voltage=3.8;CHECK(scm_session_ingest(&s,c.source_id,34,&x,1)==0,"later voltage remains in ordered history");
    CHECK(scm_session_fit(&s)==SCM_SESSION_ERR_MISSING_VOLTAGE&&s.fit_attempts==3&&s.fit_results==1&&
          !memcmp(&saved,&s.fit,sizeof(saved)),"mask limitation neither deletes nor double-counts earlier fit");
    known_charge=s.epoch_charge_Ah;known_time=s.elapsed_total_s;x.dt=3600;x.current=1;
    CHECK(scm_session_ingest(&s,c.source_id,35,&x,1)==0&&s.count==36&&
          s.epoch_charge_Ah==known_charge+1.&&s.elapsed_total_s==known_time+3600&&!s.model_valid,
          "point-domain failure retains actual input journal and charge");
    x.current=-1;CHECK(scm_session_ingest(&s,c.source_id,36,&x,1)==0,"known reversal retained after model domain failure");
    CHECK(scm_session_query(&s,&q,&a,&w)==0&&q.status==SCM_SESSION_POINT_UNAVAILABLE&&
          !q.point_available&&!q.assessment_available&&q.capacity_available,
          "state point remains unavailable until valid refit while earlier capacity remains labeled");
    CHECK(scm_session_rebuild(&s)==0&&!s.model_valid,"restore reconstruction preserves invalid point latch by replay");
    CHECK(scm_session_cold_reset(&s)==0&&s.next_index==37&&s.epoch_begin==37&&s.schedule_cursor==3&&
          s.fit_attempts==3&&s.fit_results==1&&s.last_fit_attempt_index==35&&!s.has_fit,
          "cold reset discards inference while preserving operational history");
    CHECK(scm_session_rebuild(&s)==0,"cold session with prior operational fit ledger reconstructs");
    scm_session_destroy(&s);
}

int main(void)
{
    ingestion_and_reset();bounds_and_schedule();tiny_fit_and_failure();
    printf("{\"test\":\"session_lifecycle\",\"checks\":%d,\"failures\":%d,\"tiny_numerical_fit_calls\":%d,"
           "\"primary_fit_calls\":0,\"session_bytes\":%zu,\"config_bytes\":%zu,\"query_bytes\":%zu,"
           "\"sample_bytes\":%zu,\"fit_result_bytes\":%zu,\"model_bytes\":%zu,\"assessment_bytes\":%zu,\"assessment_workspace_bytes\":%zu}\n",
           checks,failures,numerical_fit_calls,sizeof(scm_session),sizeof(scm_session_config),sizeof(scm_session_query_result),
           sizeof(scm_sample),sizeof(scm_fit_result),sizeof(scm_model_state),sizeof(scm_assessment),sizeof(scm_assess_workspace));
    return failures?1:0;
}
