#include "scm_stable.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static void test_charge(void)
{
    scm_stable_charge s,before;
    const int64_t most_negative_product=-INT64_C(9223372034707292160);
    const int64_t most_positive_product=INT64_C(9223372030412324865);
    unsigned i;
    assert(scm_stable_charge_init(&s,-100,100,0)==SCM_STABLE_OK);
    for(i=0;i<1024;i++) {
        assert(scm_stable_charge_push(&s,7,13)==SCM_STABLE_OK);
        assert(s.value==91);
        assert(scm_stable_charge_push(&s,-7,13)==SCM_STABLE_OK);
        assert(s.value==0);
    }
    before=s;
    assert(scm_stable_charge_push(&s,101,1)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_charge_init(&s,INT64_MIN,INT64_MAX,0)==SCM_STABLE_OK);
    assert(scm_stable_charge_push(&s,INT32_MIN,UINT32_MAX)==SCM_STABLE_OK);
    assert(s.value==most_negative_product);
    assert(scm_stable_charge_init(&s,INT64_MIN,INT64_MAX,0)==SCM_STABLE_OK);
    assert(scm_stable_charge_push(&s,INT32_MAX,UINT32_MAX)==SCM_STABLE_OK);
    assert(s.value==most_positive_product);
    assert(scm_stable_charge_init(&s,INT64_MIN,INT64_MAX,INT64_MAX)==SCM_STABLE_OK);
    before=s;
    assert(scm_stable_charge_push(&s,1,1)==SCM_STABLE_ERR_OVERFLOW);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_charge_init(&s,INT64_MIN,INT64_MAX,INT64_MIN)==SCM_STABLE_OK);
    before=s;
    assert(scm_stable_charge_push(&s,-1,1)==SCM_STABLE_ERR_OVERFLOW);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_charge_push(&s,INT32_MIN,0)==SCM_STABLE_OK);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_charge_init(&s,4,3,3)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_charge_init(NULL,0,1,0)==SCM_STABLE_ERR_ARGUMENT);
}

static void test_masks(void)
{
    scm_stable_mask s,before;
    unsigned i;
    assert(scm_stable_mask_init(&s,UINT64_MAX)==SCM_STABLE_OK);
    assert(scm_stable_mask_apply(&s,UINT64_C(0x8000000000000005))==SCM_STABLE_OK);
    before=s;
    for(i=0;i<1024;i++) {
        assert(scm_stable_mask_apply(&s,UINT64_MAX)==SCM_STABLE_OK);
        assert(scm_stable_mask_apply(&s,before.active)==SCM_STABLE_OK);
        assert(memcmp(&s,&before,sizeof(s))==0);
    }
    assert(scm_stable_mask_apply(&s,0)==SCM_STABLE_INCONSISTENT);
    assert(s.active==0);
    assert(scm_stable_mask_apply(&s,UINT64_MAX)==SCM_STABLE_INCONSISTENT);
    assert(s.active==0);
    assert(scm_stable_mask_init(&s,UINT64_C(0x15))==SCM_STABLE_OK);
    before=s;
    assert(scm_stable_mask_apply(&s,2)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_mask_init(&s,0)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
}

static void test_attenuation(void)
{
    scm_stable_attenuation a,before;
    const uint32_t numerator[]={0,1,1,1,1,31,32,33,UINT32_MAX,UINT32_MAX,1};
    const uint32_t denominator[]={1,UINT32_MAX,1050,35,1,1,1,1,UINT32_MAX,1,8};
    unsigned i;
    a.lower=11;a.upper=22;before=a;
    assert(scm_stable_attenuation_ratio(1,0,&a)==SCM_STABLE_ERR_ARGUMENT);
    assert(memcmp(&a,&before,sizeof(a))==0);
    for(i=0;i<sizeof(numerator)/sizeof(numerator[0]);i++) {
        assert(scm_stable_attenuation_ratio(numerator[i],denominator[i],&a)==SCM_STABLE_OK);
        assert(a.lower<=a.upper && a.upper<=SCM_STABLE_DEN);
        if(!numerator[i])assert(a.lower==SCM_STABLE_DEN && a.upper==SCM_STABLE_DEN);
        if((uint64_t)numerator[i]>=UINT64_C(32)*denominator[i])
            assert(a.lower==0 && a.upper==1);
    }
    assert(scm_stable_attenuation_ratio(1,1,&a)==SCM_STABLE_OK);
    /* Mathematical coarse bounds 2<e<3 imply 1/3<exp(-1)<1/2.
     * This is a quality smoke check, not the complete exponential audit.
     */
    assert(a.lower>SCM_STABLE_DEN/3 && a.upper<SCM_STABLE_DEN/2);
}

static void test_intervals(void)
{
    scm_stable_interval s,before;
    scm_stable_attenuation a;
    unsigned i;
    assert(scm_stable_interval_init(&s,-7,11,20)==SCM_STABLE_OK);
    a.lower=a.upper=SCM_STABLE_DEN;before=s;
    for(i=0;i<1024;i++) {
        assert(scm_stable_interval_step(&s,&a,20)==SCM_STABLE_OK);
        assert(memcmp(&s,&before,sizeof(s))==0);
    }
    a.lower=a.upper=0;
    assert(scm_stable_interval_step(&s,&a,-9)==SCM_STABLE_OK);
    assert(s.lower==-9 && s.upper==-9);
    assert(scm_stable_interval_init(&s,-1,-1,10)==SCM_STABLE_OK);
    a.lower=a.upper=SCM_STABLE_DEN/2;
    assert(scm_stable_interval_step(&s,&a,0)==SCM_STABLE_OK);
    assert(s.lower==-1 && s.upper==0);
    assert(scm_stable_interval_init(&s,1,1,10)==SCM_STABLE_OK);
    assert(scm_stable_interval_step(&s,&a,0)==SCM_STABLE_OK);
    assert(s.lower==0 && s.upper==1);
    assert(scm_stable_interval_init(&s,-4,8,10)==SCM_STABLE_OK);
    a.lower=SCM_STABLE_DEN/4;a.upper=3*(SCM_STABLE_DEN/4);
    assert(scm_stable_interval_step(&s,&a,2)==SCM_STABLE_OK);
    assert(s.lower==-3 && s.upper==7);
    assert(scm_stable_interval_init(&s,-SCM_STABLE_STATE_MAX,
                SCM_STABLE_STATE_MAX,SCM_STABLE_STATE_MAX)==SCM_STABLE_OK);
    a.lower=0;a.upper=SCM_STABLE_DEN;
    assert(scm_stable_interval_step(&s,&a,SCM_STABLE_STATE_MAX)==SCM_STABLE_OK);
    assert(s.lower==-SCM_STABLE_STATE_MAX && s.upper==SCM_STABLE_STATE_MAX);
    before=s;a.upper=SCM_STABLE_DEN+1;
    assert(scm_stable_interval_step(&s,&a,0)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    a.upper=SCM_STABLE_DEN;
    assert(scm_stable_interval_step(&s,&a,INT32_MIN)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_interval_init(&s,0,0,INT32_MIN)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_interval_init(&s,0,0,SCM_STABLE_STATE_MAX+1)==SCM_STABLE_ERR_RANGE);
    assert(memcmp(&s,&before,sizeof(s))==0);
    assert(scm_stable_interval_init(&s,0,0,0)==SCM_STABLE_OK);
    assert(scm_stable_interval_step(&s,&a,0)==SCM_STABLE_OK);
    assert(s.lower==0 && s.upper==0);
}

int main(void)
{
    test_charge();test_masks();test_attenuation();test_intervals();
    puts("stable integer kernel tests passed");
    return 0;
}
