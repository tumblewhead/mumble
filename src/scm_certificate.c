#include "scm_certificate.h"
#include <limits.h>

/* All divisors passed here are positive. Numerators are bounded far above
 * INT64_MIN, so quotient/remainder correction cannot overflow.
 */
static int64_t floor_ratio(int64_t n,int64_t d)
{
    int64_t q=n/d;
    if(n%d<0)q--;
    return q;
}

static int64_t ceil_ratio(int64_t n,int64_t d)
{
    int64_t q=n/d;
    if(n%d>0)q++;
    return q;
}

static uint64_t domain_mask(uint32_t cells)
{
    return cells==SCM_CERTIFICATE_MAX_CELLS?UINT64_MAX:
        (UINT64_C(1)<<cells)-UINT64_C(1);
}

static int rc_valid(const scm_stable_interval *s)
{
    return s->bound>=0 && s->bound<=SCM_STABLE_STATE_MAX &&
        s->lower<=s->upper && s->lower>=-s->bound && s->upper<=s->bound;
}

int scm_certificate_config_validate(const scm_certificate_config *c)
{
    uint32_t i;
    if(!c)return SCM_STABLE_ERR_ARGUMENT;
    if(!c->cells || c->cells>SCM_CERTIFICATE_MAX_CELLS ||
       c->ocv_knots<2 || c->ocv_knots>SCM_CERTIFICATE_MAX_OCV ||
       c->initial_soc_lower<0 ||
       c->initial_soc_upper>SCM_CERTIFICATE_SOC_ONE ||
       c->initial_soc_lower>c->initial_soc_upper ||
       c->current_limit_uA<=0 ||
       c->current_limit_uA>SCM_CERTIFICATE_CURRENT_LIMIT_UA ||
       c->r0_mOhm>SCM_CERTIFICATE_RESISTANCE_LIMIT_MOHM)
        return SCM_STABLE_ERR_RANGE;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        if(c->r_mOhm[i]>SCM_CERTIFICATE_RESISTANCE_LIMIT_MOHM ||
           !c->tau_ticks[i] || !rc_valid(&c->initial_rc[i]))
            return SCM_STABLE_ERR_RANGE;
        /* This also admits every target for any permitted input current. */
        if((int64_t)c->current_limit_uA*(int64_t)c->r_mOhm[i]>
           c->initial_rc[i].bound)return SCM_STABLE_ERR_RANGE;
    }
    for(i=0;i<c->cells;i++) {
        if(!c->capacity[i].lower_uAh ||
           c->capacity[i].lower_uAh>c->capacity[i].upper_uAh)
            return SCM_STABLE_ERR_RANGE;
    }
    if(c->ocv[0].soc!=0 ||
       c->ocv[c->ocv_knots-1].soc!=SCM_CERTIFICATE_SOC_ONE)
        return SCM_STABLE_ERR_RANGE;
    for(i=0;i<c->ocv_knots;i++) {
        if(c->ocv[i].voltage_nV< -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV ||
           c->ocv[i].voltage_nV>SCM_CERTIFICATE_VOLTAGE_LIMIT_NV)
            return SCM_STABLE_ERR_RANGE;
        if(i && (c->ocv[i].soc<=c->ocv[i-1].soc ||
                 c->ocv[i].voltage_nV<c->ocv[i-1].voltage_nV))
            return SCM_STABLE_ERR_RANGE;
    }
    return SCM_STABLE_OK;
}

static int bank_valid(const scm_certificate_bank *s)
{
    uint32_t i;
    const scm_certificate_config *c=s->config;
    if(scm_certificate_config_validate(c)!=SCM_STABLE_OK)return 0;
    if(s->charge.lower!= -SCM_CERTIFICATE_CHARGE_LIMIT ||
       s->charge.upper!=SCM_CERTIFICATE_CHARGE_LIMIT ||
       s->charge.value<s->charge.lower || s->charge.value>s->charge.upper ||
       s->evidence.domain!=domain_mask(c->cells) ||
       (s->evidence.active&~s->evidence.domain))return 0;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        if(!rc_valid(&s->rc[i]) ||
           s->rc[i].bound!=c->initial_rc[i].bound)return 0;
    }
    for(i=0;i<c->cells;i++) {
        if(s->initial_soc[i].lower<c->initial_soc_lower ||
           s->initial_soc[i].upper>c->initial_soc_upper ||
           s->initial_soc[i].lower>s->initial_soc[i].upper)return 0;
    }
    return 1;
}

int scm_certificate_init(scm_certificate_bank *s,const scm_certificate_config *c)
{
    scm_certificate_bank next={0};
    uint32_t i;
    int status;
    if(!s || !c)return SCM_STABLE_ERR_ARGUMENT;
    status=scm_certificate_config_validate(c);
    if(status<0)return status;
    next.config=c;
    next.charge.lower= -SCM_CERTIFICATE_CHARGE_LIMIT;
    next.charge.upper=SCM_CERTIFICATE_CHARGE_LIMIT;
    next.charge.value=0;
    next.evidence.domain=domain_mask(c->cells);
    next.evidence.active=next.evidence.domain;
    for(i=0;i<SCM_CERTIFICATE_RC;i++)next.rc[i]=c->initial_rc[i];
    for(i=0;i<c->cells;i++) {
        next.initial_soc[i].lower=c->initial_soc_lower;
        next.initial_soc[i].upper=c->initial_soc_upper;
    }
    *s=next;
    return SCM_STABLE_OK;
}

/* Current-SOC preimage for a continuous nondecreasing PWL map. The hull
 * includes complete flat segments and inclusive knot/voltage boundaries.
 * A segment numerator is at most16e9*65536<2^50. All subtraction occurs
 * after clipping voltages to the segment, so these numerators are nonnegative.
 */
static int ocv_preimage(const scm_certificate_config *c,int64_t voltage_low,
                        int64_t voltage_high,scm_certificate_soc *out)
{
    uint32_t i;
    int found=0;
    int64_t low=SCM_CERTIFICATE_SOC_ONE,high=0;
    for(i=1;i<c->ocv_knots;i++) {
        const scm_certificate_ocv_knot *left=&c->ocv[i-1],*right=&c->ocv[i];
        int64_t du=right->voltage_nV-left->voltage_nV;
        int64_t dz=(int64_t)right->soc-left->soc;
        int64_t vl=voltage_low>left->voltage_nV?voltage_low:left->voltage_nV;
        int64_t vh=voltage_high<right->voltage_nV?voltage_high:right->voltage_nV;
        int64_t lo,hi;
        if(vl>vh)continue;
        if(!du) {
            lo=left->soc;hi=right->soc;
        } else {
            lo=(int64_t)left->soc+floor_ratio((vl-left->voltage_nV)*dz,du);
            hi=(int64_t)left->soc+ceil_ratio((vh-left->voltage_nV)*dz,du);
        }
        if(!found || lo<low)low=lo;
        if(!found || hi>high)high=hi;
        found=1;
    }
    if(!found)return SCM_STABLE_INCONSISTENT;
    out->lower=(int32_t)low;out->upper=(int32_t)high;
    return SCM_STABLE_OK;
}

/* |P|<=2^44 and SOC_ONE=2^16 imply |n|<=2^60. Positive uint32
 * capacity endpoints give 126000000<=d<2^59. Ratios and their signed
 * SOC sums/differences stay below2^34 in magnitude; keep them in int64
 * until an intersection with stored [0,SOC_ONE] endpoints is established.
 */
static void depletion(const scm_certificate_capacity *c,int64_t charge,
                       int64_t *lower,int64_t *upper)
{
    int64_t n=charge*(int64_t)SCM_CERTIFICATE_SOC_ONE;
    int64_t dl=SCM_CERTIFICATE_CHARGE_PER_UAH*(int64_t)c->lower_uAh;
    int64_t du=SCM_CERTIFICATE_CHARGE_PER_UAH*(int64_t)c->upper_uAh;
    if(charge>=0) {
        *lower=floor_ratio(n,du);*upper=ceil_ratio(n,dl);
    } else {
        *lower=floor_ratio(n,dl);*upper=ceil_ratio(n,du);
    }
}

int scm_certificate_push(scm_certificate_bank *s,const scm_certificate_sample *o,
                         scm_certificate_workspace *w)
{
    const scm_certificate_config *c;
    scm_certificate_soc observed_soc;
    scm_stable_attenuation a;
    uint64_t allowed;
    uint32_t i;
    int status;
    int64_t corrected_low,corrected_high;
    if(!s || !o || !w || s==&w->staged)return SCM_STABLE_ERR_ARGUMENT;
    if(!bank_valid(s))return SCM_STABLE_ERR_RANGE;
    c=s->config;
    if(o->current_uA< -c->current_limit_uA || o->current_uA>c->current_limit_uA ||
       o->voltage_lower_nV>o->voltage_upper_nV ||
       o->voltage_lower_nV< -SCM_CERTIFICATE_VOLTAGE_LIMIT_NV ||
       o->voltage_upper_nV>SCM_CERTIFICATE_VOLTAGE_LIMIT_NV)
        return SCM_STABLE_ERR_RANGE;
    w->staged=*s;
    status=scm_stable_charge_push(&w->staged.charge,o->current_uA,o->ticks);
    if(status<0)return status;
    /* Each corrected endpoint has magnitude below8e9+0.2e9+3*2^30<2^34. */
    corrected_low=o->voltage_lower_nV+(int64_t)o->current_uA*c->r0_mOhm;
    corrected_high=o->voltage_upper_nV+(int64_t)o->current_uA*c->r0_mOhm;
    for(i=0;i<SCM_CERTIFICATE_RC;i++) {
        int64_t target=(int64_t)o->current_uA*(int64_t)c->r_mOhm[i];
        if(target< -(int64_t)w->staged.rc[i].bound ||
           target>w->staged.rc[i].bound)return SCM_STABLE_ERR_RANGE;
        status=scm_stable_attenuation_ratio(o->ticks,c->tau_ticks[i],&a);
        if(status<0)return status;
        status=scm_stable_interval_step(&w->staged.rc[i],&a,(int32_t)target);
        if(status<0)return status;
        corrected_low+=w->staged.rc[i].lower;
        corrected_high+=w->staged.rc[i].upper;
    }
    allowed=w->staged.evidence.active;
    status=ocv_preimage(c,corrected_low,corrected_high,&observed_soc);
    if(status==SCM_STABLE_INCONSISTENT)allowed=0;
    else {
        for(i=0;i<c->cells;i++) {
            int64_t rlo,rhi,lo,hi;
            uint64_t bit=UINT64_C(1)<<i;
            if(!(allowed&bit))continue;
            depletion(&c->capacity[i],w->staged.charge.value,&rlo,&rhi);
            lo=(int64_t)observed_soc.lower+rlo;
            hi=(int64_t)observed_soc.upper+rhi;
            if(lo<w->staged.initial_soc[i].lower)lo=w->staged.initial_soc[i].lower;
            if(hi>w->staged.initial_soc[i].upper)hi=w->staged.initial_soc[i].upper;
            if(lo>hi)allowed&=~bit;
            else {
                /* A surviving intersection lies inside the old integer SOC
                 * interval, so both casts are representable and in-domain. */
                w->staged.initial_soc[i].lower=(int32_t)lo;
                w->staged.initial_soc[i].upper=(int32_t)hi;
            }
        }
    }
    status=scm_stable_mask_apply(&w->staged.evidence,allowed);
    if(status<0)return status;
    *s=w->staged;
    return status;
}

int scm_certificate_query(const scm_certificate_bank *s,scm_certificate_result *out)
{
    const scm_certificate_config *c;
    scm_certificate_result next={0};
    uint32_t i;
    if(!s || !out)return SCM_STABLE_ERR_ARGUMENT;
    if(!bank_valid(s))return SCM_STABLE_ERR_RANGE;
    c=s->config;
    next.active_mask=s->evidence.active;
    for(i=0;i<c->cells;i++) {
        int64_t rlo,rhi,lo,hi;
        uint64_t bit=UINT64_C(1)<<i;
        if(!(next.active_mask&bit))continue;
        depletion(&c->capacity[i],s->charge.value,&rlo,&rhi);
        lo=(int64_t)s->initial_soc[i].lower-rhi;
        hi=(int64_t)s->initial_soc[i].upper-rlo;
        if(lo<0)lo=0;
        if(hi>SCM_CERTIFICATE_SOC_ONE)hi=SCM_CERTIFICATE_SOC_ONE;
        /* Initialized/updated banks have a nonempty current-SOC outer
         * interval for every active cell. Reject corrupted incompatible state. */
        if(lo>hi)return SCM_STABLE_ERR_RANGE;
        if(!next.has_support || lo<next.soc_lower)next.soc_lower=(int32_t)lo;
        if(!next.has_support || hi>next.soc_upper)next.soc_upper=(int32_t)hi;
        if(!next.has_support || c->capacity[i].lower_uAh<next.capacity_lower_uAh)
            next.capacity_lower_uAh=c->capacity[i].lower_uAh;
        if(!next.has_support || c->capacity[i].upper_uAh>next.capacity_upper_uAh)
            next.capacity_upper_uAh=c->capacity[i].upper_uAh;
        next.active_cells++;
        next.has_support=1;
    }
    *out=next;
    return next.has_support?SCM_STABLE_OK:SCM_STABLE_INCONSISTENT;
}
