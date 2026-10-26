/* Fixed host arithmetic/transaction fixture, not a cell trajectory or tuning
 * experiment. The runner extracts the selector from the frozen production
 * source and links an instrumented copy. No live estimator ABI is changed. */
#include "boundary_transaction_capture.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#ifndef FIXTURE_REMEDY
#error "The runner must select baseline or diagnostic remedy explicitly."
#endif
#define D SCM_ONLINE_DIM
#define AT(i,j) ((i)*D+(j))

static unsigned checks, failures, ingest_calls, accepted_inputs;
static double max_joseph_error;

#define CHECK(test, message) do { \
    checks++; if (!(test)) { failures++; fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, message); } \
} while (0)

static const char *stage_name(int stage)
{
    static const char *const names[]={"none","observation","innovation",
        "projection","innovation_sd","optimal_rotation","standard",
        "raw_change","mean_domain","joseph_sd","joseph_rotation",
        "final_observation","validation"};
    return stage>=0 && stage<(int)(sizeof(names)/sizeof(names[0])) ? names[stage] : "invalid";
}

static void print_capture(const boundary_capture *c)
{
    printf("{\"stage\":\"%s\",\"coordinate\":%d,\"column\":%d,"
           "\"fallback_mask\":%u,\"boundary_coordinate\":%d,"
           "\"mean_before_hex\":\"%a\",\"raw_gain_hex\":\"%a\","
           "\"standard_hex\":\"%a\",\"raw_change_hex\":\"%a\","
           "\"scale_hex\":\"%a\",\"attempted_selected_gain_hex\":\"%a\","
           "\"proposed_mean_hex\":\"%a\"}",
           stage_name(c->stage),c->coordinate,c->column,c->fallback_mask,
           c->boundary_coordinate,c->mean_before,c->raw_gain,c->standard,
           c->raw_change,c->scale,c->selected_gain,c->proposed_mean);
}

static void prior(scm_online *s)
{
    scm_online_config config;
    scm_online_config_default(&config);
    memset(config.source_id,0x41,sizeof(config.source_id));
    CHECK(scm_online_init(s,&config)==0,"public prior initializes");
}

static int ingest(scm_online *s,uint64_t index,const scm_sample *input,
                  int present,scm_online_workspace *w,boundary_capture *capture)
{
    int rc;
    ingest_calls++;
    rc=fixture_ingest(s,s->config.source_id,index,input,present,w,capture);
    if(rc>=0)accepted_inputs++;
    return rc;
}

static void scalar_case(const char *name,double mean,double standard,int baseline_reject)
{
    scm_online s;
    scm_online_workspace w;
    boundary_capture capture;
    int rc;
    prior(&s);memset(&w,0,sizeof(w));
    s.mean[9]=mean;w.covariance_gradient[9]=1.;
    rc=fixture_select(&s,&w,standard,&capture);
    CHECK((rc!=0)==(baseline_reject&&!FIXTURE_REMEDY),"declared scalar outcome");
    if(baseline_reject) {
        double unit=nextafter(0.,1.);
        CHECK(capture.boundary_coordinate==9,"witness names R3");
        CHECK(capture.mean_before==unit&&capture.raw_gain==1.&&capture.standard==-1.5,
              "minimal witness operands captured exactly");
        CHECK(capture.scale==unit&&capture.selected_gain==unit&&capture.proposed_mean==-unit,
              "rounded backoff and negative proposed mean captured exactly");
        if(FIXTURE_REMEDY) {
            CHECK(capture.stage==BOUNDARY_STAGE_NONE&&capture.fallback_mask==(1u<<9),
                  "finite infeasible coordinate is repaired without rejecting observation");
            CHECK(w.correction[9]==0.&&s.mean[9]==mean,"fallback selects zero, preserves tiny mean");
            CHECK(s.last_gain_scale==0.&&s.last_limited_mask==(1u<<9)&&s.last_blocked_mask==(1u<<9),
                  "fallback selection and multiplier masks agree");
        } else {
            CHECK(capture.stage==BOUNDARY_STAGE_MEAN_DOMAIN&&capture.coordinate==9,
                  "baseline names the actual mean-domain rejection");
        }
    } else {
        CHECK(capture.stage==BOUNDARY_STAGE_NONE&&capture.fallback_mask==0,
              "other declared scalar cases need no remedy");
    }
    if(rc==0) {
        CHECK(isfinite(s.mean[9])&&s.mean[9]>=0.&&s.mean[9]<=1.,"selected mean remains in support");
        if(w.correction[9]==0.||standard==0.)
            CHECK(!memcmp(&mean,&s.mean[9],sizeof(mean)),"zero gain/residual preserves mean bytes");
    }
    printf("{\"case\":\"%s\",\"return\":%d,\"mean_after_hex\":\"%a\","
           "\"actual_selected_gain_hex\":\"%a\",\"capture\":",name,rc,s.mean[9],w.correction[9]);
    print_capture(&capture);printf("}");
}

static void covariance(const double *factor,double *p)
{
    int i,j,k;
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        p[AT(i,j)]=0.;
        for(k=0;k<D;k++)p[AT(i,j)]+=factor[AT(i,k)]*factor[AT(j,k)];
    }
}

/* Dense Joseph oracle: forms (I-KH)P(I-KH)^T+K R K^T directly from
 * the committed prediction and actual selected t, K=t/sd. It does not use
 * either production rotation pass or its g-t covariance identity. */
static void check_joseph(const scm_online *predicted,const scm_online *after,
                         const scm_online_workspace *w,const scm_sample *input)
{
    double p[D*D],a[D*D],ap[D*D],actual[D*D],h[D]={0},k[D];
    double u,slope,sd=sqrt(after->last_innovation_variance_V2);
    double standard=(input->voltage-predicted->last_prediction_V)/sd;
    int i,j,l;
    CHECK(scm_ocv_eval(NULL,predicted->mean[11],&u,&slope)==0,"independent observation derivative");
    h[6]=-input->current;h[10]=-predicted->mean[15];h[11]=slope;
    h[12]=h[13]=h[14]=-1.;h[15]=-predicted->mean[10];
    covariance(predicted->factor,p);covariance(after->factor,actual);
    for(i=0;i<D;i++)k[i]=w->correction[i]/sd;
    for(i=0;i<D;i++)for(j=0;j<D;j++)a[AT(i,j)]=(i==j?1.:0.)-k[i]*h[j];
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        ap[AT(i,j)]=0.;
        for(l=0;l<D;l++)ap[AT(i,j)]+=a[AT(i,l)]*p[AT(l,j)];
    }
    for(i=0;i<D;i++) {
        double expected_mean=predicted->mean[i];
        if(w->correction[i]!=0.&&standard!=0.)expected_mean+=w->correction[i]*standard;
        CHECK(after->mean[i]==expected_mean,"mean uses the actual selected gain");
        for(j=0;j<D;j++) {
            double expected=k[i]*k[j]*after->config.sigma_V*after->config.sigma_V;
            double error;
            for(l=0;l<D;l++)expected+=ap[AT(i,l)]*a[AT(j,l)];
            error=fabs(actual[AT(i,j)]-expected);
            max_joseph_error=fmax(max_joseph_error,error);
            CHECK(error<=3e-13*fmax(1.,fabs(expected)),"full covariance matches independent dense Joseph");
            if(j>i)CHECK(after->factor[AT(i,j)]==0.,"factor remains exactly lower triangular");
        }
        CHECK(after->factor[AT(i,i)]>=0.,"factor diagonal remains nonnegative");
    }
    CHECK(fabs(actual[AT(9,9)]-p[AT(9,9)])<=3e-15,"zero-gain R3 retains marginal variance");
    CHECK(w->correction[12]!=0.&&after->mean[12]!=predicted->mean[12],
          "another coordinate still learns when R3 is blocked");
}

static void full_boundary_witness(void)
{
    scm_online before,predicted,after,saved;
    scm_online_workspace w;
    boundary_capture capture,ignored;
    scm_sample input={0.,0.,0.};
    double unit=nextafter(0.,1.),sd;
    int rc;
    prior(&before);memset(&w,0,sizeof(w));
    memset(before.factor,0,sizeof(before.factor));before.mean[9]=7.*unit;
    before.factor[AT(9,9)]=.25;before.factor[AT(12,9)]=-1.;
    CHECK(scm_online_validate(&before)==0,"constructed boundary state meets the production API contract");
    predicted=before;
    CHECK(ingest(&predicted,0,&input,0,&w,&ignored)==0,"independent prediction-only reference");
    sd=hypot(before.config.sigma_V,1.);
    input.voltage=predicted.last_prediction_V-8.*sd;
    after=before;rc=ingest(&after,0,&input,1,&w,&capture);
    CHECK(rc==0,"known input accepted even if voltage correction is rejected");
    CHECK(after.next_index==1&&after.prediction_count==1&&after.voltage_count==1&&
          after.missing_voltage_count==0,"boundary input accounted exactly once");
    CHECK(capture.mean_before==7.*unit&&capture.selected_gain==unit&&capture.standard==-8.&&
          capture.proposed_mean==-unit,"full production-order witness captured exactly");
    if(FIXTURE_REMEDY) {
        CHECK(capture.stage==BOUNDARY_STAGE_NONE&&capture.fallback_mask==(1u<<9),
              "fallback resolves constructed mean-domain failure");
        CHECK(after.rejected_voltage_count==0&&!(after.flags&SCM_ONLINE_FLAG_UPDATE_REJECTED),
              "remedy fixture does not reject corrected observation");
        CHECK(w.correction[9]==0.&&after.mean[9]==before.mean[9],"same zero gain used for R3 mean");
        CHECK(after.has_voltage&&after.evidence_next_index==1&&after.zero_gain_count==0,
              "feasible coordinates retain current observation evidence");
        CHECK(after.last_blocked_mask==(1u<<9)&&after.last_gain_scale==0.&&after.last_max_gain_scale>0.,
              "fallback does not force a global stall");
        check_joseph(&predicted,&after,&w,&input);
    } else {
        CHECK(capture.stage==BOUNDARY_STAGE_MEAN_DOMAIN&&capture.coordinate==9,
              "production rejection identifies stage and coordinate");
        CHECK(after.rejected_voltage_count==1&&(after.flags&SCM_ONLINE_FLAG_UPDATE_REJECTED),
              "baseline records exactly one rejected correction");
        CHECK(!memcmp(after.mean,predicted.mean,sizeof(after.mean))&&
              !memcmp(after.factor,predicted.factor,sizeof(after.factor)),
              "rejected correction retains committed prediction bytes");
        CHECK(memcmp(w.candidate.factor,predicted.factor,sizeof(predicted.factor))!=0,
              "discarded trial actually mutated its factor before failing");
        CHECK(!after.has_voltage&&after.evidence_next_index==0,"rejection creates no evidence");
    }
    CHECK(scm_online_validate(&after)==0,"boundary output remains checkpoint-valid");
    saved=after;
    CHECK(ingest(&after,0,&input,1,&w,&ignored)==SCM_ONLINE_ERR_ORDER,"duplicate boundary input rejected");
    CHECK(!memcmp(&saved,&after,sizeof(after)),"duplicate input has no side effects");
    printf("{\"return\":%d,\"default_sigma_V\":%.17g,\"mean_R3_before_hex\":\"%a\","
           "\"mean_R3_after_hex\":\"%a\",\"voltage_V\":%.17g,"
           "\"rejected_corrections\":%llu,\"evidence_next_index\":%llu,\"capture\":",
           rc,before.config.sigma_V,before.mean[9],saved.mean[9],input.voltage,
           (unsigned long long)saved.rejected_voltage_count,(unsigned long long)saved.evidence_next_index);
    print_capture(&capture);printf("}");
}

static void advanced_prediction_failure(void)
{
    scm_online before,predicted,after,saved;
    scm_online_workspace w;
    boundary_capture capture,ignored;
    scm_sample input={.031,.04,3.8};
    prior(&before);before.factor[AT(11,0)]=1e200;memset(&w,0,sizeof(w));
    CHECK(scm_online_validate(&before)==0,"finite large factor is admissible fixture state");
    predicted=before;
    CHECK(ingest(&predicted,0,&input,0,&w,&ignored)==0,"positive-dt physical prediction succeeds");
    CHECK(memcmp(before.mean,predicted.mean,sizeof(before.mean))!=0&&
          memcmp(before.factor,predicted.factor,sizeof(before.factor))!=0,
          "prediction differs from entering mean and factor");
    after=before;
    CHECK(ingest(&after,0,&input,1,&w,&capture)==0,"unusable correction retains accepted interval");
    CHECK(capture.stage==BOUNDARY_STAGE_INNOVATION_SD&&capture.column==0,
          "capture identifies independent innovation-scale rejection");
    CHECK(capture.fallback_mask==0,"boundary remedy leaves other numerical rejection unchanged");
    CHECK(after.rejected_voltage_count==1&&(after.flags&SCM_ONLINE_FLAG_UPDATE_REJECTED),
          "independent stage remains explicitly rejected");
    CHECK(!memcmp(after.mean,predicted.mean,sizeof(after.mean))&&
          !memcmp(after.factor,predicted.factor,sizeof(after.factor)),
          "failure preserves advanced prediction instead of reverting physical time");
    CHECK(memcmp(w.candidate.factor,predicted.factor,sizeof(predicted.factor))!=0,
          "failed correction has a genuinely partially mutated trial");
    CHECK(after.next_index==1&&after.prediction_count==1&&after.voltage_count==1&&
          after.elapsed_s==input.dt&&after.epoch_elapsed_s==input.dt&&
          after.evidence_next_index==0&&!after.has_voltage,"failed correction respects physical and evidence ledgers");
    CHECK(scm_online_validate(&after)==0,"retained advanced prediction is valid");
    saved=after;
    CHECK(ingest(&after,0,&input,1,&w,&ignored)==SCM_ONLINE_ERR_ORDER,"retry of consumed input is refused");
    CHECK(!memcmp(&saved,&after,sizeof(after)),"refused retry is byte-atomic");
    CHECK(ingest(&after,1,&input,0,&w,&ignored)==0,"next known interval can advance without correction");
    CHECK(after.next_index==2&&after.prediction_count==2&&after.voltage_count==1&&
          after.missing_voltage_count==1&&after.rejected_voltage_count==1&&
          after.elapsed_s==2.*input.dt&&after.evidence_next_index==0,
          "two different inputs are counted once each, no posterior replay");
    printf("{\"advanced_prediction_preserved\":true,\"duplicate_atomic\":true,"
           "\"next_index_after_next_input\":%llu,\"capture\":",(unsigned long long)after.next_index);
    print_capture(&capture);printf("}");
}

static void all_zero_gain(void)
{
    scm_online before,predicted,after;
    scm_online_workspace w;
    boundary_capture capture;
    scm_sample input={0.,0.,0.};
    prior(&before);memset(before.factor,0,sizeof(before.factor));memset(&w,0,sizeof(w));
    before.mean[9]=-0.;before.mean[12]=.25;
    before.factor[AT(9,9)]=.25;before.factor[AT(12,9)]=-1.;
    predicted=before;
    CHECK(ingest(&predicted,0,&input,0,&w,&capture)==0,"all-zero reference prediction");
    input.voltage=predicted.last_prediction_V-8.*hypot(before.config.sigma_V,1.);
    after=before;
    CHECK(ingest(&after,0,&input,1,&w,&capture)==0,"all-zero selected gain accepted");
    CHECK(capture.stage==BOUNDARY_STAGE_NONE&&capture.fallback_mask==0,"exact boundary needs no arithmetic fallback");
    CHECK(!memcmp(after.mean,predicted.mean,sizeof(after.mean))&&
          !memcmp(after.factor,predicted.factor,sizeof(after.factor)),"all-zero gain retains mean/factor bytes including signed zero");
    CHECK(after.zero_gain_count==1&&after.limited_gain_count==1&&after.rejected_voltage_count==0,
          "all-zero and limited counters retain their definitions");
    CHECK(!after.has_voltage&&after.evidence_next_index==0,"all-zero gain does not manufacture evidence");
    CHECK(after.last_blocked_mask==((1u<<9)|(1u<<12)),"all-zero mask names both blocked coordinates");
    CHECK(scm_online_validate(&after)==0,"all-zero state validates");
    printf("{\"mean_factor_bytes_preserved\":true,\"zero_gain_count\":%llu,"
           "\"blocked_mask\":%u}",(unsigned long long)after.zero_gain_count,after.last_blocked_mask);
}

int main(void)
{
    double unit=nextafter(0.,1.),largest_subnormal=nextafter(DBL_MIN,0.);
    unsigned baseline_scalar_expected_rejections=1;
    CHECK(sizeof(double)==8&&DBL_MANT_DIG==53&&DBL_MAX_EXP==1024&&FLT_RADIX==2,
          "fixture requires binary64");
    CHECK(fegetround()==FE_TONEAREST,"fixture requires round-to-nearest");
    CHECK(FLT_EVAL_METHOD==0,"fixture requires operations evaluated at declared precision");
    CHECK(unit>0.&&fpclassify(unit)==FP_SUBNORMAL&&unit*1.5==2.*unit,
          "fixture requires gradual underflow and ties-to-even");
    printf("{\"schema\":\"mumble_boundary_transaction_fixture_v1\",\"variant\":\"%s\","
           "\"binary64_gradual_underflow\":true,\"scalar_cases\":[",FIXTURE_REMEDY?"finite_coordinate_zero_fallback":"production_baseline");
    scalar_case("lower_zero_outward",0.,-1.5,0);printf(",");
    scalar_case("lower_zero_inward",0.,.125,0);printf(",");
    scalar_case("lower_adjacent_outward",unit,-1.5,1);printf(",");
    scalar_case("lower_adjacent_inward",unit,.125,0);printf(",");
    scalar_case("lower_second_subnormal_outward",2.*unit,-1.5,0);printf(",");
    scalar_case("lower_largest_subnormal_outward",largest_subnormal,-1.5,0);printf(",");
    scalar_case("lower_largest_subnormal_inward",largest_subnormal,.125,0);printf(",");
    scalar_case("lower_min_normal_outward",DBL_MIN,-1.5,0);printf(",");
    scalar_case("lower_min_normal_inward",DBL_MIN,.125,0);printf(",");
    scalar_case("upper_zero_distance_outward",1.,.125,0);printf(",");
    scalar_case("upper_adjacent_outward",nextafter(1.,0.),.125,0);printf(",");
    scalar_case("upper_adjacent_inward",nextafter(1.,0.),-.125,0);printf(",");
    scalar_case("zero_innovation_at_adjacent",unit,0.,0);printf(",");
    scalar_case("negative_zero_outward",-0.,-1.5,0);
    printf("],\"full_boundary_witness\":");full_boundary_witness();
    printf(",\"advanced_prediction_failure\":");advanced_prediction_failure();
    printf(",\"all_zero_gain\":");all_zero_gain();
    printf(",\"scalar_case_count\":14,\"expected_baseline_scalar_rejections\":%u,"
           "\"max_dense_Joseph_error\":%.17g,\"ingest_calls\":%u,\"accepted_fixture_inputs\":%u,"
           "\"storage_bytes\":{\"state\":%zu,\"workspace\":%zu,\"query\":%zu,"
           "\"fixture_capture\":%zu,\"production_added\":0,\"checkpoint_added\":0},"
           "\"cell_trace_deliveries\":0,\"checks\":%u,\"failed_checks\":%u,\"passed\":%s,\"result\":\"%s\"}\n",
           baseline_scalar_expected_rejections,max_joseph_error,ingest_calls,accepted_inputs,
           sizeof(scm_online),sizeof(scm_online_workspace),sizeof(scm_online_query_result),sizeof(boundary_capture),
           checks,failures,failures?"false":"true",failures?"failed":"expected_outcomes_reproduced");
    return failures?1:0;
}
