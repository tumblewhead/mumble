#include "scm_certificate_box.h"

/* Stability004 test adaptation of tests/test_certificate.c at parent
 * 4a990cf923e2e56935a1ffb346215faad05bff66, plus new interval-forcing,
 * uncertain-parameter, transaction and degenerate-equivalence checks.
 * The original test and its frozen evidence are unchanged.
 */
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static scm_certificate_box_config basic_config(void)
{
    scm_certificate_box_config c={0};
    unsigned i;
    c.cells=3;c.ocv_knots=2;
    c.initial_soc_lower=0;c.initial_soc_upper=SCM_CERTIFICATE_SOC_ONE;
    c.current_limit_uA=SCM_CERTIFICATE_CURRENT_LIMIT_UA;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        c.mode[i].tau_lower_ticks=c.mode[i].tau_upper_ticks=UINT32_C(1000)*(i+1);
        c.initial_rc[i].bound=INT32_C(1048576);
    }
    for(i=0;i<3;i++) {
        c.capacity[i].lower_uAh=UINT32_C(50000)+UINT32_C(10000)*i;
        c.capacity[i].upper_uAh=c.capacity[i].lower_uAh+UINT32_C(10000);
    }
    c.ocv[0].soc=0;c.ocv[0].voltage_nV=INT64_C(3000000000);
    c.ocv[1].soc=SCM_CERTIFICATE_SOC_ONE;
    c.ocv[1].voltage_nV=INT64_C(3655360000);
    return c;
}

static void anchor(scm_certificate_box_bank *s,scm_certificate_box_workspace *w)
{
    scm_certificate_box_sample o={0,0,INT64_C(3327680000),INT64_C(3327680000)};
    assert(scm_certificate_box_push(s,&o,w)==SCM_STABLE_OK);
}

static void test_box_attenuation(void)
{
    static const uint32_t cases[][3]={
        {0,1,UINT32_MAX},{1,1,1},{1,1,UINT32_MAX},
        {1000,999,1001},{32,1,2},{UINT32_MAX,1,UINT32_MAX},
        {UINT32_MAX,UINT32_MAX,UINT32_MAX}
    };
    static const uint32_t invalid[][2]={{0,0},{0,1},{1,0},{2,1}};
    scm_stable_attenuation a,lo,hi,before;
    size_t i;
    for(i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
        assert(scm_stable_attenuation_ratio(cases[i][0],cases[i][1],&lo)==SCM_STABLE_OK);
        assert(scm_stable_attenuation_ratio(cases[i][0],cases[i][2],&hi)==SCM_STABLE_OK);
        assert(scm_certificate_box_attenuation(cases[i][0],cases[i][1],cases[i][2],&a)==SCM_STABLE_OK);
        assert(a.lower==lo.lower && a.upper==hi.upper);
        assert(a.lower<=a.upper && a.upper<=SCM_STABLE_DEN);
        if(!cases[i][0])assert(a.lower==SCM_STABLE_DEN && a.upper==SCM_STABLE_DEN);
    }
    memset(&a,0xa5,sizeof(a));memcpy(&before,&a,sizeof(a));
    for(i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        /* Even exact zero-time calls must reject an invalid tau range. */
        assert(scm_certificate_box_attenuation(0,invalid[i][0],invalid[i][1],&a)==SCM_STABLE_ERR_RANGE);
        assert(memcmp(&a,&before,sizeof(a))==0);
    }
    assert(scm_certificate_box_attenuation(1,1,1,NULL)==SCM_STABLE_ERR_ARGUMENT);
}

static void step_error_unchanged(scm_stable_interval *s,
                                  const scm_stable_attenuation *a,
                                  int32_t lo,int32_t hi,int expected)
{
    scm_stable_interval before;
    memcpy(&before,s,sizeof(*s));
    assert(scm_certificate_box_interval_step(s,a,lo,hi)==expected);
    assert(memcmp(s,&before,sizeof(*s))==0);
}

static void test_interval_forcing(void)
{
    scm_stable_interval s,before,point;
    scm_stable_attenuation a={SCM_STABLE_DEN/4,SCM_STABLE_DEN*3/4};
    int32_t b=SCM_STABLE_STATE_MAX;
    assert(scm_stable_interval_init(&s,-20,40,100)==SCM_STABLE_OK);
    /* Exact eight-corner extrema: (a,x,t)=(1/4,-20,-100) and
     * (1/4,40,80), respectively. */
    assert(scm_certificate_box_interval_step(&s,&a,-100,80)==SCM_STABLE_OK);
    assert(s.lower== -80 && s.upper==70 && s.bound==100);
    assert(scm_stable_interval_init(&s,-1,1,10)==SCM_STABLE_OK);
    a.lower=SCM_STABLE_DEN/4;a.upper=SCM_STABLE_DEN/2;
    assert(scm_certificate_box_interval_step(&s,&a,-2,3)==SCM_STABLE_OK);
    assert(s.lower== -2 && s.upper==3);
    assert(scm_stable_interval_init(&s,-7,9,10)==SCM_STABLE_OK);
    a.lower=a.upper=0;
    assert(scm_certificate_box_interval_step(&s,&a,-3,5)==SCM_STABLE_OK);
    assert(s.lower== -3 && s.upper==5);
    /* These legal corners reach +/-2^62 before division. */
    assert(scm_stable_interval_init(&s,-b,b,b)==SCM_STABLE_OK);
    a.lower=0;a.upper=SCM_STABLE_DEN;
    assert(scm_certificate_box_interval_step(&s,&a,-b,b)==SCM_STABLE_OK);
    assert(s.lower== -b && s.upper==b);
    assert(scm_stable_interval_init(&s,b,b,b)==SCM_STABLE_OK);
    a.lower=a.upper=SCM_STABLE_DEN/2;
    assert(scm_certificate_box_interval_step(&s,&a,-b,-b+1)==SCM_STABLE_OK);
    assert(s.lower==0 && s.upper==1);
    assert(scm_stable_interval_init(&s,-b,-b,b)==SCM_STABLE_OK);
    assert(scm_certificate_box_interval_step(&s,&a,b-1,b)==SCM_STABLE_OK);
    assert(s.lower== -1 && s.upper==0);
    assert(scm_stable_interval_init(&s,-b,b,b)==SCM_STABLE_OK);
    point=s;
    assert(scm_stable_interval_step(&point,&a,-123)==SCM_STABLE_OK);
    assert(scm_certificate_box_interval_step(&s,&a,-123,-123)==SCM_STABLE_OK);
    assert(s.lower==point.lower && s.upper==point.upper && s.bound==point.bound);
    memset(&s,0xa5,sizeof(s));s.lower=-7;s.upper=9;s.bound=10;
    memcpy(&before,&s,sizeof(s));a.lower=a.upper=SCM_STABLE_DEN;
    assert(scm_certificate_box_interval_step(&s,&a,-10,10)==SCM_STABLE_OK);
    assert(memcmp(&s,&before,sizeof(s))==0);
    step_error_unchanged(&s,&a,1,0,SCM_STABLE_ERR_RANGE);
    step_error_unchanged(&s,&a,-11,0,SCM_STABLE_ERR_RANGE);
    step_error_unchanged(&s,&a,0,11,SCM_STABLE_ERR_RANGE);
    step_error_unchanged(&s,NULL,0,0,SCM_STABLE_ERR_ARGUMENT);
    s.bound=INT32_MIN;
    step_error_unchanged(&s,&a,0,0,SCM_STABLE_ERR_RANGE);
    s=before;s.lower=11;
    step_error_unchanged(&s,&a,0,0,SCM_STABLE_ERR_RANGE);
    s=before;a.lower=SCM_STABLE_DEN;a.upper=SCM_STABLE_DEN-1;
    step_error_unchanged(&s,&a,0,0,SCM_STABLE_ERR_RANGE);
    a.lower=0;a.upper=SCM_STABLE_DEN+1;
    step_error_unchanged(&s,&a,0,0,SCM_STABLE_ERR_RANGE);
    assert(scm_certificate_box_interval_step(NULL,&a,0,0)==SCM_STABLE_ERR_ARGUMENT);
    assert(scm_stable_interval_init(&s,0,0,0)==SCM_STABLE_OK);
    a.lower=0;a.upper=SCM_STABLE_DEN;
    assert(scm_certificate_box_interval_step(&s,&a,0,0)==SCM_STABLE_OK);
    assert(s.lower==0 && s.upper==0 && s.bound==0);
}

static void test_config_and_atomic_errors(void)
{
    scm_certificate_box_config c=basic_config(),bad;
    scm_certificate_box_bank s,before;
    scm_certificate_box_workspace w;
    scm_certificate_box_sample o={0,1000,INT64_C(3000000000),INT64_C(4000000000)};
    scm_certificate_box_result q,qbefore;
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    memcpy(&before,&s,sizeof(s));
    bad=c;bad.cells=0;
    assert(scm_certificate_box_init(&s,&bad)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    bad=c;bad.capacity[0].lower_uAh=0;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.ocv[1].soc=0;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.ocv[1].voltage_nV=bad.ocv[0].voltage_nV-1;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.mode[1].tau_lower_ticks=0;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.initial_rc[1].bound=INT32_MIN;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.mode[0].r_upper_mOhm=6;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.mode[0].r_lower_mOhm=1;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.mode[0].r_upper_mOhm=1001;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.mode[0].tau_lower_ticks=bad.mode[0].tau_upper_ticks+1;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.mode[0].r_upper_mOhm=1;bad.mode[1].tau_upper_ticks++;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.mode[0].r_upper_mOhm=1;bad.mode[0].tau_upper_ticks++;
    assert(scm_certificate_box_config_validate(&bad)==SCM_STABLE_OK);
    o.current_uA=INT32_MIN;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    o.current_uA=0;o.voltage_lower_nV=o.voltage_upper_nV+1;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    o.voltage_lower_nV= -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV-1;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    o.voltage_lower_nV=0;o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    /* Constructed arithmetic boundary, not a reachable-history assertion. */
    s.charge.value=SCM_CERTIFICATE_CHARGE_LIMIT;
    memcpy(&before,&s,sizeof(s));o.current_uA=1;o.ticks=1;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    s.charge.value= -SCM_CERTIFICATE_CHARGE_LIMIT;
    memcpy(&before,&s,sizeof(s));o.current_uA=-1;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    memset(&q,0x5a,sizeof(q));memcpy(&qbefore,&q,sizeof(q));
    s.evidence.domain=0;
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&q,&qbefore,sizeof(q))==0);
    assert(scm_certificate_box_init(NULL,&c)==SCM_STABLE_ERR_ARGUMENT);
    assert(scm_certificate_box_config_validate(NULL)==SCM_STABLE_ERR_ARGUMENT);
    assert(scm_certificate_box_push(&w.staged,&o,&w)==SCM_STABLE_ERR_ARGUMENT);
}

static void test_boundary_capacity_and_signed_charge(void)
{
    scm_certificate_box_config c=basic_config();
    scm_certificate_box_bank s;
    scm_certificate_box_workspace w;
    scm_certificate_box_result q;
    scm_certificate_box_sample o={126000,6000000,
        INT64_C(3262144000),INT64_C(3262144000)};
    unsigned i;
    c.mode[0].r_upper_mOhm=1;
    c.mode[0].tau_lower_ticks=999;c.mode[0].tau_upper_ticks=1001;
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);anchor(&s,&w);
    assert(s.evidence.active==7);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==32768 && q.soc_upper==32768);
    assert(q.capacity_lower_uAh==50000 && q.capacity_upper_uAh==80000);
    /* Q=60000microAh lies in BOTH closed cells0/1, and R=0 is an admitted
     * endpoint of the uncertain mode. After6mAh discharge, z=32768-6553.6
     * and the corresponding exact voltage is3262144000nV.
     */
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==INT64_C(756000000000));
    assert(s.evidence.active==3);
    for(i=0;i<2;i++)assert(s.initial_soc[i].lower<=32768 &&
                              s.initial_soc[i].upper>=32768);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert((int64_t)q.soc_lower*10<=262144 &&
           (int64_t)q.soc_upper*10>=262144);
    assert(q.capacity_lower_uAh==50000 && q.capacity_upper_uAh==70000);
    o.current_uA=-126000;
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3327680000);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==0 && s.evidence.active==3);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==32768 && q.soc_upper==32768);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);anchor(&s,&w);
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3393216000);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value== -INT64_C(756000000000));
    assert(s.evidence.active==3);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert((int64_t)q.soc_lower*10<=393216 &&
           (int64_t)q.soc_upper*10>=393216);
}

static void test_plateau_knots_and_inconsistency(void)
{
    scm_certificate_box_config c=basic_config();
    scm_certificate_box_bank s;
    scm_certificate_box_workspace w;
    scm_certificate_box_result q;
    scm_certificate_box_sample o={0,0,INT64_C(3100000000),INT64_C(3100000000)};
    c.ocv_knots=4;
    c.ocv[1].soc=10000;c.ocv[1].voltage_nV=INT64_C(3100000000);
    c.ocv[2].soc=30000;c.ocv[2].voltage_nV=INT64_C(3100000000);
    c.ocv[3].soc=SCM_CERTIFICATE_SOC_ONE;
    c.ocv[3].voltage_nV=INT64_C(3700000000);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==10000 && q.soc_upper==30000 && q.active_cells==3);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3000000000);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==0 && q.soc_upper==0);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3700000000);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==SCM_CERTIFICATE_SOC_ONE &&
           q.soc_upper==SCM_CERTIFICATE_SOC_ONE);
    o.current_uA=1000;o.ticks=1000;
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3800000000);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(s.charge.value==1000000 && s.evidence.active==0);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_INCONSISTENT);
    assert(!q.has_support && !q.active_cells && !q.active_mask);
    o.voltage_lower_nV= -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(s.charge.value==2000000 && s.evidence.active==0);
}

static void test_quiet_retention_and_RC_propagation(void)
{
    scm_certificate_box_config c=basic_config();
    scm_certificate_box_bank s,before;
    scm_certificate_box_workspace w;
    scm_certificate_box_result q,qbefore;
    scm_certificate_box_sample o={0,0,INT64_C(3327677000),INT64_C(3327677000)};
    unsigned i;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        c.mode[i].r_lower_mOhm=c.mode[i].r_upper_mOhm=i+1;
        c.initial_rc[i].lower=c.initial_rc[i].upper=1000;
    }
    c.mode[0].r_upper_mOhm=2;c.mode[0].tau_upper_ticks=1001;
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    for(i=0;i<3;i++)assert(s.initial_soc[i].lower==32768 &&
                              s.initial_soc[i].upper==32768);
    o.current_uA=100000;o.ticks=1000;
    o.voltage_lower_nV= -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        assert(s.rc[i].lower>1000);
        assert(s.rc[i].upper<100000*(int32_t)c.mode[i].r_upper_mOhm);
    }
    assert(scm_certificate_box_query(&s,&qbefore)==SCM_STABLE_OK);
    memcpy(&before,&s,sizeof(s));
    o.current_uA=0;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==before.charge.value);
    assert(s.evidence.active==before.evidence.active);
    assert(memcmp(s.initial_soc,before.initial_soc,sizeof(s.initial_soc))==0);
    for(i=0;i<SCM_CERTIFICATE_RC;i++)assert(s.rc[i].upper<before.rc[i].upper);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower>=qbefore.soc_lower && q.soc_upper<=qbefore.soc_upper);
    assert(q.capacity_lower_uAh>=qbefore.capacity_lower_uAh &&
           q.capacity_upper_uAh<=qbefore.capacity_upper_uAh);
    memcpy(&before,&s,sizeof(s));o.ticks=0;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==before.charge.value);
    assert(memcmp(s.rc,before.rc,sizeof(s.rc))==0);
}

static void test_signed_forcing_and_committed_contradiction(void)
{
    scm_certificate_box_config c=basic_config();
    scm_certificate_box_bank s,before;
    scm_certificate_box_workspace w;
    scm_certificate_box_result q;
    scm_certificate_box_sample o={100000,64,-SCM_CERTIFICATE_VOLTAGE_LIMIT_NV,
                                         SCM_CERTIFICATE_VOLTAGE_LIMIT_NV};
    c.mode[0].r_lower_mOhm=2;c.mode[0].r_upper_mOhm=4;
    c.mode[0].tau_lower_ticks=1;c.mode[0].tau_upper_ticks=2;
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    /* Both endpoint exponent ratios exceed32: a=[0,1]/D. From x=0,
     * [2I,4I] therefore rounds outward to[2I-1,4I] for positive I. */
    assert(s.rc[0].lower==199999 && s.rc[0].upper==400000);
    assert(s.charge.value==6400000);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    o.current_uA=-100000;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.rc[0].lower== -400000 && s.rc[0].upper== -199999);
    assert(s.charge.value== -6400000);
    memcpy(&before,&s,sizeof(s));
    o.current_uA=100000;
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(7000000000);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(s.charge.value==0 && !s.evidence.active);
    assert(s.rc[0].lower>0 && s.rc[0].upper==400000);
    assert(memcmp(s.initial_soc,before.initial_soc,sizeof(s.initial_soc))==0);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_INCONSISTENT);
    assert(!q.has_support && !q.active_cells && !q.active_mask);
    o.voltage_lower_nV=-SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(s.charge.value==6400000 && !s.evidence.active);
}

static void test_extreme_box_domains(void)
{
    scm_certificate_box_config c=basic_config();
    scm_certificate_box_bank s,before;
    scm_certificate_box_workspace w;
    scm_certificate_box_result q;
    scm_certificate_box_sample o={200000,1,-SCM_CERTIFICATE_VOLTAGE_LIMIT_NV,
                                      SCM_CERTIFICATE_VOLTAGE_LIMIT_NV};
    unsigned i;
    c.cells=1;c.capacity[0].lower_uAh=c.capacity[0].upper_uAh=UINT32_MAX;
    c.r0_mOhm=SCM_CERTIFICATE_RESISTANCE_LIMIT_MOHM;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        c.mode[i].r_lower_mOhm=c.mode[i].r_upper_mOhm=1000;
        c.mode[i].tau_lower_ticks=c.mode[i].tau_upper_ticks=UINT32_MAX;
        c.initial_rc[i].lower=-SCM_STABLE_STATE_MAX;
        c.initial_rc[i].upper=c.initial_rc[i].bound=SCM_STABLE_STATE_MAX;
    }
    c.mode[0].r_lower_mOhm=0;c.mode[0].tau_lower_ticks=1;
    assert(scm_certificate_box_config_validate(&c)==SCM_STABLE_OK);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    o.current_uA=-200000;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==0);
    o.current_uA=1;o.ticks=UINT32_MAX;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==(int64_t)UINT32_MAX);
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        assert(s.rc[i].lower>= -SCM_STABLE_STATE_MAX);
        assert(s.rc[i].lower<=s.rc[i].upper);
        assert(s.rc[i].upper<=SCM_STABLE_STATE_MAX);
    }
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    memcpy(&before,&s,sizeof(s));o.current_uA=200000;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    o.current_uA=-200000;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
}

static void assert_same_numerical_bank(const scm_certificate_box_bank *box,
                                       const scm_certificate_bank *point)
{
    unsigned i;
    assert(box->charge.value==point->charge.value);
    assert(box->charge.lower==point->charge.lower);
    assert(box->charge.upper==point->charge.upper);
    assert(box->evidence.domain==point->evidence.domain);
    assert(box->evidence.active==point->evidence.active);
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        assert(box->rc[i].lower==point->rc[i].lower);
        assert(box->rc[i].upper==point->rc[i].upper);
        assert(box->rc[i].bound==point->rc[i].bound);
    }
    for(i=0;i<SCM_CERTIFICATE_MAX_CELLS;i++) {
        assert(box->initial_soc[i].lower==point->initial_soc[i].lower);
        assert(box->initial_soc[i].upper==point->initial_soc[i].upper);
    }
}

static void assert_same_result(const scm_certificate_result *a,
                               const scm_certificate_result *b)
{
    assert(a->soc_lower==b->soc_lower && a->soc_upper==b->soc_upper);
    assert(a->capacity_lower_uAh==b->capacity_lower_uAh);
    assert(a->capacity_upper_uAh==b->capacity_upper_uAh);
    assert(a->active_mask==b->active_mask && a->active_cells==b->active_cells);
    assert(a->has_support==b->has_support);
}

static void test_degenerate_equivalence(void)
{
    static const int32_t currents[]={0,200000,-200000,12345,-87654,0};
    static const uint32_t ticks[]={0,1,999,1001,1000000,UINT32_MAX};
    scm_certificate_box_config c=basic_config();
    scm_certificate_config p={0};
    scm_certificate_box_bank box;
    scm_certificate_bank point;
    scm_certificate_box_workspace bw;
    scm_certificate_workspace pw;
    scm_certificate_result bq,pq;
    scm_certificate_sample o={0,0,INT64_C(3327677000),INT64_C(3327683000)};
    unsigned i,n;
    int bs,ps;
    c.r0_mOhm=2;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        c.mode[i].r_lower_mOhm=c.mode[i].r_upper_mOhm=i+1;
        c.initial_rc[i].lower=-17*(int32_t)(i+1);
        c.initial_rc[i].upper=23*(int32_t)(i+1);
    }
    p.cells=c.cells;p.ocv_knots=c.ocv_knots;
    p.initial_soc_lower=c.initial_soc_lower;p.initial_soc_upper=c.initial_soc_upper;
    p.current_limit_uA=c.current_limit_uA;p.r0_mOhm=c.r0_mOhm;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        p.r_mOhm[i]=c.mode[i].r_lower_mOhm;
        p.tau_ticks[i]=c.mode[i].tau_lower_ticks;
        p.initial_rc[i]=c.initial_rc[i];
    }
    memcpy(p.capacity,c.capacity,sizeof(p.capacity));
    memcpy(p.ocv,c.ocv,sizeof(p.ocv));
    assert(scm_certificate_box_init(&box,&c)==SCM_STABLE_OK);
    assert(scm_certificate_init(&point,&p)==SCM_STABLE_OK);
    assert_same_numerical_bank(&box,&point);
    for(n=0;n<18;n++) {
        i=n%6;
        o.current_uA=currents[i];o.ticks=ticks[i];
        if(n) {
            o.voltage_lower_nV=-SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
            o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
        }
        bs=scm_certificate_box_push(&box,&o,&bw);
        ps=scm_certificate_push(&point,&o,&pw);
        assert(bs==ps && bs==SCM_STABLE_OK);
        assert_same_numerical_bank(&box,&point);
        bs=scm_certificate_box_query(&box,&bq);ps=scm_certificate_query(&point,&pq);
        assert(bs==ps);assert_same_result(&bq,&pq);
    }
    o.current_uA=1;o.ticks=1;
    o.voltage_lower_nV=o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    assert(scm_certificate_box_push(&box,&o,&bw)==SCM_STABLE_INCONSISTENT);
    assert(scm_certificate_push(&point,&o,&pw)==SCM_STABLE_INCONSISTENT);
    assert_same_numerical_bank(&box,&point);
    assert(scm_certificate_box_query(&box,&bq)==SCM_STABLE_INCONSISTENT);
    assert(scm_certificate_query(&point,&pq)==SCM_STABLE_INCONSISTENT);
    assert_same_result(&bq,&pq);
}

static void test_maximum_mask_and_ratio_extremes(void)
{
    scm_certificate_box_config c=basic_config();
    scm_certificate_box_bank s;
    scm_certificate_box_workspace w;
    scm_certificate_box_result q;
    scm_certificate_box_sample o={0,0,-SCM_CERTIFICATE_VOLTAGE_LIMIT_NV,
                                  SCM_CERTIFICATE_VOLTAGE_LIMIT_NV};
    unsigned i;
    c.cells=64;
    for(i=0;i<64;i++)c.capacity[i].lower_uAh=c.capacity[i].upper_uAh=1000+i;
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    assert(s.evidence.active==UINT64_MAX);
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.active_cells==64 && q.active_mask==UINT64_MAX);
    assert(q.capacity_lower_uAh==1000 && q.capacity_upper_uAh==1063);
    c.cells=1;c.capacity[0].lower_uAh=c.capacity[0].upper_uAh=UINT32_MAX;
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value=SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==0 && q.soc_upper==SCM_CERTIFICATE_SOC_ONE-2);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value= -SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_box_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==2 && q.soc_upper==SCM_CERTIFICATE_SOC_ONE);
    /* Extreme ratio products are evaluated in int64 and discarded before
     * narrowing when no SOC-domain-compatible point remains. */
    c.capacity[0].lower_uAh=c.capacity[0].upper_uAh=1;
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value=SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(!s.evidence.active);
    assert(scm_certificate_box_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value= -SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_box_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(!s.evidence.active);
}

int main(void)
{
    test_box_attenuation();
    test_interval_forcing();
    test_config_and_atomic_errors();
    test_boundary_capacity_and_signed_charge();
    test_plateau_knots_and_inconsistency();
    test_quiet_retention_and_RC_propagation();
    test_signed_forcing_and_committed_contradiction();
    test_extreme_box_domains();
    test_degenerate_equivalence();
    test_maximum_mask_and_ratio_extremes();
    printf("certificate box tests passed; config=%zu bank=%zu workspace=%zu sample=%zu result=%zu bytes\n",
           sizeof(scm_certificate_box_config),sizeof(scm_certificate_box_bank),
           sizeof(scm_certificate_box_workspace),sizeof(scm_certificate_box_sample),
           sizeof(scm_certificate_box_result));
    return 0;
}
