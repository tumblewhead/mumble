/* Small boundary witnesses, not an endurance run or a stability certificate.
 * Several public structures are deliberately initialized to synthetic boundary
 * states. They are NOT claimed to result from valid battery histories and must
 * never be reused as inference evidence. Production source is linked unchanged.
 */
#include "scm_remainder.h"
#include <fenv.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define REPEATS 4096
#ifndef __STDC_IEC_559__
#define __STDC_IEC_559__ 0
#endif

static int failures;
static const char *boolean(int v) { return v ? "true" : "false"; }
static void mark(int expected) { if(!expected)failures++; }

static scm_evidence_config configuration(void)
{
    scm_evidence_config c;
    const double taus[3]={.05,.5,5};
    int i;
    memset(&c,0,sizeof(c));
    c.modes=3;c.sigma=.001;c.max_event_samples=4096;
    c.residual_rms_limit_sigma=4;c.source_id[0]=71;c.source_id[31]=23;
    for(i=0;i<3;i++)c.theta[i]=log(taus[i]);
    c.theta[3]=log(150.);c.theta[4]=log(300.);
    c.theta[5]=.68;c.theta[6]=log(.06);
    c.alpha[0]=.12;c.alpha[4]=.025;c.alpha[8]=.005;
    for(i=0;i<3;i++){c.alpha[1+i]=.2;c.alpha[5+i]=.002*(i+1);}
    for(i=0;i<7;i++)c.scale[i]=i==5?.1:1.;
    for(i=0;i<9;i++)c.scale[7+i]=i<=3?.2:.03;
    for(i=0;i<16;i++)c.radius[i]=.2;
    return c;
}

static void scalar_sum(void)
{
    volatile double s=0x1p53,one=1.;
    const double before=s;
    int i,ok;
    for(i=0;i<REPEATS;i++)s=s+one;
    ok=s==before;mark(ok);
    printf("{\"id\":\"unit_sum_absorption\",\"kind\":\"scalar_boundary\","
           "\"before_hex\":\"%a\",\"after_hex\":\"%a\","
           "\"iterations\":%d,\"exact_increment\":%d,"
           "\"mechanism_reproduced\":%s}",before,(double)s,REPEATS,REPEATS,boolean(ok));
}

static void bounded_cycle(void)
{
    volatile double s=.5,increment=0x1p-54;
    double middle,after;
    int ok;
    s=s+increment;middle=s;s=s-increment;after=s;
    ok=middle==.5 && after==nextafter(.5,0.) && after-.5==-0x1p-54;mark(ok);
    printf(",{\"id\":\"bounded_zero_net_cycle\",\"kind\":\"scalar_boundary\","
           "\"before_hex\":\"%a\",\"increment_hex\":\"%a\","
           "\"after_positive_hex\":\"%a\",\"after_cycle_hex\":\"%a\","
           "\"exact_after_cycle_hex\":\"%a\",\"signed_error_hex\":\"%a\","
           "\"cycles\":1,\"asymptotic_drift_claim\":false,\"mechanism_reproduced\":%s}",
           .5,(double)increment,middle,after,.5,after-.5,boolean(ok));
}

static void scalar_rss(void)
{
    volatile double norm=0x1p27,one=1.;
    const double before=norm;
    const uint64_t exact_square=(UINT64_C(1)<<54)+REPEATS;
    uint64_t computed_square;
    int i,ok;
    for(i=0;i<REPEATS;i++)norm=hypot(norm,one);
    computed_square=(uint64_t)((double)norm*(double)norm);
    ok=norm==before && exact_square-computed_square==REPEATS;mark(ok);
    printf(",{\"id\":\"hypot_rss_absorption\",\"kind\":\"scalar_boundary\","
           "\"before_hex\":\"%a\",\"after_hex\":\"%a\","
           "\"iterations\":%d,\"exact_squared_norm\":\"%" PRIu64 "\","
           "\"computed_squared_norm\":\"%" PRIu64 "\",\"missing_squared_mass\":%d,"
           "\"libm_behavior_measured_only\":true,\"mechanism_reproduced\":%s}",
           before,(double)norm,REPEATS,exact_square,computed_square,REPEATS,boolean(ok));
}

static void production_qr(void)
{
    scm_evidence_config c=configuration();
    scm_evidence e;
    scm_evidence_workspace w;
    const uint64_t initial_count=UINT64_C(1)<<54;
    const size_t first=scm_evidence_packed_index(0,0);
    int status=scm_evidence_init(&e,&c),i=0,ok;
    double before=0,after=0;
    uint64_t final_count=0;
    if(!status) {
        /* Algebraically valid factor/count construction only. It is not a
         * replay-derived physical model state or an allowed inference restore.
         */
        e.history.upper[first]=0x1p27;e.history.samples=initial_count;
        e.next_index=initial_count;before=e.history.upper[first];
        for(i=0;i<REPEATS;i++) {
            e.event.upper[first]=1.;e.event.samples=1;
            e.next_index=e.history.samples+1;
            status=scm_evidence_seal(&e,&w);if(status)break;
        }
        after=e.history.upper[first];final_count=e.history.samples;
    }
    ok=!status && i==REPEATS && before==after && final_count==initial_count+REPEATS;
    mark(ok);
    printf(",{\"id\":\"production_qr_merge_absorption\",\"kind\":\"constructed_api_boundary\","
           "\"api\":\"scm_evidence_seal\",\"reachable_battery_history_claim\":false,"
           "\"before_diagonal_hex\":\"%a\",\"after_diagonal_hex\":\"%a\","
           "\"initial_count\":\"%" PRIu64 "\",\"final_count\":\"%" PRIu64 "\","
           "\"iterations_completed\":%d,\"status\":%d,"
           "\"exact_information_increment\":%d,\"mechanism_reproduced\":%s}",
           before,after,initial_count,final_count,i,status,REPEATS,boolean(ok));
}

static void production_remainder(void)
{
    scm_evidence_config c=configuration();
    scm_remainder r;
    scm_remainder_workspace w;
    scm_sample sample={1./35.,0.,3.8};
    int status=scm_remainder_init(&r,&c),i=0,pair=-1,k,ok;
    double before=0,after=0,last_bound=0;
    if(!status) {
        for(k=0;k<r.pair_count;k++)if(r.pair_row[k]==5 && r.pair_column[k]==5)pair=k;
        if(pair<0)status=SCM_REMAINDER_ERR_ARGUMENT;
    }
    if(!status) {
        /* Deliberately synthetic old curvature mass. Standalone push is an
         * audit interface; this object is never paired with inference evidence.
         */
        r.coefficient[pair]=0x1p36;before=r.coefficient[pair];
        for(i=0;i<REPEATS;i++) {
            status=scm_remainder_push(&r,c.source_id,(uint64_t)i,&sample,&w);
            if(status)break;
        }
        after=r.coefficient[pair];last_bound=r.last_bound[pair];
    }
    ok=!status && i==REPEATS && before==after && last_bound>0;
    mark(ok);
    printf(",{\"id\":\"production_remainder_rss_absorption\",\"kind\":\"constructed_api_boundary\","
           "\"api\":\"scm_remainder_push\",\"reachable_battery_history_claim\":false,"
           "\"used_for_inference\":false,\"pair\":[5,5],"
           "\"before_coefficient_hex\":\"%a\",\"after_coefficient_hex\":\"%a\","
           "\"last_positive_bound_hex\":\"%a\",\"last_positive_bound\":%.17g,"
           "\"iterations_completed\":%d,\"status\":%d,\"mechanism_reproduced\":%s}",
           before,after,last_bound,last_bound,i,status,boolean(ok));
}

static void production_elapsed(void)
{
    scm_evidence_config c=configuration();
    scm_model_state s;
    scm_model_row row;
    int status=scm_model_init(&s,c.modes,c.theta),ok;
    double before=0,after=0,dt=1./35.;
    if(!status) {
        s.elapsed=0x1p48;before=s.elapsed;
        status=scm_model_step(&s,&c.ocv,dt,0.,&row);after=s.elapsed;
    }
    ok=!status && before==after && dt>0;mark(ok);
    printf(",{\"id\":\"production_elapsed_absorption\",\"kind\":\"constructed_api_boundary\","
           "\"api\":\"scm_model_step\",\"replayed_lifetime_claim\":false,"
           "\"before_seconds_hex\":\"%a\",\"after_seconds_hex\":\"%a\","
           "\"dt_seconds_hex\":\"%a\",\"status\":%d,\"mechanism_reproduced\":%s}",
           before,after,dt,status,boolean(ok));
}

static void production_counters(void)
{
    scm_evidence_config c=configuration();
    scm_evidence e,saved_e;
    scm_evidence_workspace ew;
    scm_remainder r,saved_r;
    scm_remainder_workspace rw;
    scm_sample sample={1./35.,0.,3.8};
    int es=scm_evidence_init(&e,&c),rs=scm_remainder_init(&r,&c);
    int ea=0,ra=0,ok;
    if(!es) {
        e.next_index=UINT64_MAX;e.history.samples=UINT64_MAX;
        memcpy(&saved_e,&e,sizeof(e));
        es=scm_evidence_push(&e,c.source_id,UINT64_MAX,&sample,&ew);
        ea=memcmp(&saved_e,&e,sizeof(e))==0;
    }
    if(!rs) {
        r.next_index=UINT64_MAX;memcpy(&saved_r,&r,sizeof(r));
        rs=scm_remainder_push(&r,c.source_id,UINT64_MAX,&sample,&rw);
        ra=memcmp(&saved_r,&r,sizeof(r))==0;
    }
    ok=es==SCM_EVIDENCE_ERR_OVERFLOW && rs==SCM_REMAINDER_ERR_OVERFLOW && ea && ra;
    mark(ok);
    printf(",{\"id\":\"production_counter_exhaustion\",\"kind\":\"constructed_api_boundary\","
           "\"index\":\"%" PRIu64 "\",\"evidence_status\":%d,\"remainder_status\":%d,"
           "\"evidence_unchanged\":%s,\"remainder_unchanged\":%s,"
           "\"meaning\":\"fail_closed_safety_not_indefinite_availability\","
           "\"mechanism_reproduced\":%s}",
           UINT64_MAX,es,rs,boolean(ea),boolean(ra),boolean(ok));
}

int main(void)
{
    int rounding=fegetround();
    int supported=FLT_RADIX==2 && DBL_MANT_DIG==53 && DBL_MAX_EXP==1024 &&
                  sizeof(double)==8 && rounding==FE_TONEAREST;
    printf("{\"schema\":\"mumble_stability_witness_output_v1\",\"machine\":{"
           "\"FLT_RADIX\":%d,\"DBL_MANT_DIG\":%d,\"DBL_MAX_EXP\":%d,"
           "\"FLT_EVAL_METHOD\":%d,\"LDBL_MANT_DIG\":%d,\"sizeof_double\":%zu,"
           "\"sizeof_uint64_t\":%zu,\"IEC559_macro\":%d,\"fegetround\":%d,"
           "\"FE_TONEAREST\":%d},\"format_supported\":%s,\"cases\":[",
           FLT_RADIX,DBL_MANT_DIG,DBL_MAX_EXP,FLT_EVAL_METHOD,LDBL_MANT_DIG,
           sizeof(double),sizeof(uint64_t),__STDC_IEC_559__,rounding,FE_TONEAREST,boolean(supported));
    if(supported) {
        scalar_sum();bounded_cycle();scalar_rss();production_qr();
        production_remainder();production_elapsed();production_counters();
    }
    printf("],\"mechanisms_reproduced\":%d,\"mechanisms_expected\":7,"
           "\"all_expected_mechanisms_reproduced\":%s,"
           "\"indefinite_stability_proved\":false,\"endurance_run\":false}\n",
           supported?7-failures:0,boolean(supported && !failures));
    return supported ? (failures?1:0) : 77;
}
