#include "scm_certificate.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static scm_certificate_config basic_config(void)
{
    scm_certificate_config c={0};
    unsigned i;
    c.cells=3;c.ocv_knots=2;
    c.initial_soc_lower=0;c.initial_soc_upper=SCM_CERTIFICATE_SOC_ONE;
    c.current_limit_uA=SCM_CERTIFICATE_CURRENT_LIMIT_UA;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        c.tau_ticks[i]=UINT32_C(1000)*(i+1);
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

static void anchor(scm_certificate_bank *s,scm_certificate_workspace *w)
{
    scm_certificate_sample o={0,0,INT64_C(3327680000),INT64_C(3327680000)};
    assert(scm_certificate_push(s,&o,w)==SCM_STABLE_OK);
}

static void test_config_and_atomic_errors(void)
{
    scm_certificate_config c=basic_config(),bad;
    scm_certificate_bank s,before;
    scm_certificate_workspace w;
    scm_certificate_sample o={0,1000,INT64_C(3000000000),INT64_C(4000000000)};
    scm_certificate_result q,qbefore;
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    memcpy(&before,&s,sizeof(s));
    bad=c;bad.cells=0;
    assert(scm_certificate_init(&s,&bad)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    bad=c;bad.capacity[0].lower_uAh=0;
    assert(scm_certificate_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.ocv[1].soc=0;
    assert(scm_certificate_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.ocv[1].voltage_nV=bad.ocv[0].voltage_nV-1;
    assert(scm_certificate_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.tau_ticks[1]=0;
    assert(scm_certificate_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.initial_rc[1].bound=INT32_MIN;
    assert(scm_certificate_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    bad=c;bad.r_mOhm[0]=6;
    assert(scm_certificate_config_validate(&bad)==SCM_STABLE_ERR_RANGE);
    o.current_uA=INT32_MIN;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    o.current_uA=0;o.voltage_lower_nV=o.voltage_upper_nV+1;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    o.voltage_lower_nV= -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV-1;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    o.voltage_lower_nV=0;o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    /* Constructed arithmetic boundary, not a reachable-history assertion. */
    s.charge.value=SCM_CERTIFICATE_CHARGE_LIMIT;
    memcpy(&before,&s,sizeof(s));o.current_uA=1;o.ticks=1;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    s.charge.value= -SCM_CERTIFICATE_CHARGE_LIMIT;
    memcpy(&before,&s,sizeof(s));o.current_uA=-1;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    memset(&q,0x5a,sizeof(q));memcpy(&qbefore,&q,sizeof(q));
    s.evidence.domain=0;
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&q,&qbefore,sizeof(q))==0);
    assert(scm_certificate_init(NULL,&c)==SCM_STABLE_ERR_ARGUMENT);
    assert(scm_certificate_config_validate(NULL)==SCM_STABLE_ERR_ARGUMENT);
}

static void test_boundary_capacity_and_signed_charge(void)
{
    scm_certificate_config c=basic_config();
    scm_certificate_bank s;
    scm_certificate_workspace w;
    scm_certificate_result q;
    scm_certificate_sample o={126000,6000000,
        INT64_C(3262144000),INT64_C(3262144000)};
    unsigned i;
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);anchor(&s,&w);
    assert(s.evidence.active==7);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==32768 && q.soc_upper==32768);
    assert(q.capacity_lower_uAh==50000 && q.capacity_upper_uAh==80000);
    /* Q=60000microAh lies in BOTH closed cells0/1. After6mAh discharge,
     * z=32768-6553.6 and linear-OCV voltage is exactly3262144000nV.
     */
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==INT64_C(756000000000));
    assert(s.evidence.active==3);
    for(i=0;i<2;i++)assert(s.initial_soc[i].lower<=32768 &&
                              s.initial_soc[i].upper>=32768);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert((int64_t)q.soc_lower*10<=262144 &&
           (int64_t)q.soc_upper*10>=262144);
    assert(q.capacity_lower_uAh==50000 && q.capacity_upper_uAh==70000);
    o.current_uA=-126000;
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3327680000);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==0 && s.evidence.active==3);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==32768 && q.soc_upper==32768);
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);anchor(&s,&w);
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3393216000);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value== -INT64_C(756000000000));
    assert(s.evidence.active==3);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert((int64_t)q.soc_lower*10<=393216 &&
           (int64_t)q.soc_upper*10>=393216);
}

static void test_plateau_knots_and_inconsistency(void)
{
    scm_certificate_config c=basic_config();
    scm_certificate_bank s;
    scm_certificate_workspace w;
    scm_certificate_result q;
    scm_certificate_sample o={0,0,INT64_C(3100000000),INT64_C(3100000000)};
    c.ocv_knots=4;
    c.ocv[1].soc=10000;c.ocv[1].voltage_nV=INT64_C(3100000000);
    c.ocv[2].soc=30000;c.ocv[2].voltage_nV=INT64_C(3100000000);
    c.ocv[3].soc=SCM_CERTIFICATE_SOC_ONE;
    c.ocv[3].voltage_nV=INT64_C(3700000000);
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==10000 && q.soc_upper==30000 && q.active_cells==3);
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3000000000);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==0 && q.soc_upper==0);
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3700000000);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==SCM_CERTIFICATE_SOC_ONE &&
           q.soc_upper==SCM_CERTIFICATE_SOC_ONE);
    o.current_uA=1000;o.ticks=1000;
    o.voltage_lower_nV=o.voltage_upper_nV=INT64_C(3800000000);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(s.charge.value==1000000 && s.evidence.active==0);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_INCONSISTENT);
    assert(!q.has_support && !q.active_cells && !q.active_mask);
    o.voltage_lower_nV= -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(s.charge.value==2000000 && s.evidence.active==0);
}

static void test_quiet_retention_and_RC_propagation(void)
{
    scm_certificate_config c=basic_config();
    scm_certificate_bank s,before;
    scm_certificate_workspace w;
    scm_certificate_result q,qbefore;
    scm_certificate_sample o={0,0,INT64_C(3327677000),INT64_C(3327677000)};
    unsigned i;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        c.r_mOhm[i]=i+1;
        c.initial_rc[i].lower=c.initial_rc[i].upper=1000;
    }
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    for(i=0;i<3;i++)assert(s.initial_soc[i].lower==32768 &&
                              s.initial_soc[i].upper==32768);
    o.current_uA=100000;o.ticks=1000;
    o.voltage_lower_nV= -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    o.voltage_upper_nV=SCM_CERTIFICATE_VOLTAGE_LIMIT_NV;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        assert(s.rc[i].lower>1000);
        assert(s.rc[i].upper<100000*(int32_t)(i+1));
    }
    assert(scm_certificate_query(&s,&qbefore)==SCM_STABLE_OK);
    memcpy(&before,&s,sizeof(s));
    o.current_uA=0;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==before.charge.value);
    assert(s.evidence.active==before.evidence.active);
    assert(memcmp(s.initial_soc,before.initial_soc,sizeof(s.initial_soc))==0);
    for(i=0;i<SCM_CERTIFICATE_RC;i++)assert(s.rc[i].upper<before.rc[i].upper);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower>=qbefore.soc_lower && q.soc_upper<=qbefore.soc_upper);
    assert(q.capacity_lower_uAh>=qbefore.capacity_lower_uAh &&
           q.capacity_upper_uAh<=qbefore.capacity_upper_uAh);
    memcpy(&before,&s,sizeof(s));o.ticks=0;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(s.charge.value==before.charge.value);
    assert(memcmp(s.rc,before.rc,sizeof(s.rc))==0);
}

static void test_maximum_mask_and_ratio_extremes(void)
{
    scm_certificate_config c=basic_config();
    scm_certificate_bank s;
    scm_certificate_workspace w;
    scm_certificate_result q;
    scm_certificate_sample o={0,0,-SCM_CERTIFICATE_VOLTAGE_LIMIT_NV,
                                  SCM_CERTIFICATE_VOLTAGE_LIMIT_NV};
    unsigned i;
    c.cells=64;
    for(i=0;i<64;i++)c.capacity[i].lower_uAh=c.capacity[i].upper_uAh=1000+i;
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    assert(s.evidence.active==UINT64_MAX);
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.active_cells==64 && q.active_mask==UINT64_MAX);
    assert(q.capacity_lower_uAh==1000 && q.capacity_upper_uAh==1063);
    c.cells=1;c.capacity[0].lower_uAh=c.capacity[0].upper_uAh=UINT32_MAX;
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value=SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==0 && q.soc_upper==SCM_CERTIFICATE_SOC_ONE-2);
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value= -SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_OK);
    assert(scm_certificate_query(&s,&q)==SCM_STABLE_OK);
    assert(q.soc_lower==2 && q.soc_upper==SCM_CERTIFICATE_SOC_ONE);
    /* Extreme ratio products are evaluated in int64 and discarded before
     * narrowing when no SOC-domain-compatible point remains. */
    c.capacity[0].lower_uAh=c.capacity[0].upper_uAh=1;
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value=SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(!s.evidence.active);
    assert(scm_certificate_init(&s,&c)==SCM_STABLE_OK);
    s.charge.value= -SCM_CERTIFICATE_CHARGE_LIMIT;
    assert(scm_certificate_push(&s,&o,&w)==SCM_STABLE_INCONSISTENT);
    assert(!s.evidence.active);
}

int main(void)
{
    test_config_and_atomic_errors();
    test_boundary_capacity_and_signed_charge();
    test_plateau_knots_and_inconsistency();
    test_quiet_retention_and_RC_propagation();
    test_maximum_mask_and_ratio_extremes();
    printf("certificate tests passed; config=%zu bank=%zu workspace=%zu sample=%zu result=%zu bytes\n",
           sizeof(scm_certificate_config),sizeof(scm_certificate_bank),
           sizeof(scm_certificate_workspace),sizeof(scm_certificate_sample),
           sizeof(scm_certificate_result));
    return 0;
}
