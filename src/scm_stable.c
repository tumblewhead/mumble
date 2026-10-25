#include "scm_stable.h"
#include <limits.h>

/* Positive division rounded upward without an overflowing n+d-1. */
static uint64_t ceil_div(uint64_t n,uint64_t d)
{
    return n/d+(n%d!=0);
}

/* Inputs are in [0,D]. Except for the explicitly handled unity case,
 * a*b<2^64. No floating point, signed shift or overflowing ceil numerator.
 */
static uint64_t mul_down(uint64_t a,uint64_t b)
{
    if(a==SCM_STABLE_DEN)return b;
    if(b==SCM_STABLE_DEN)return a;
    return (a*b)>>32;
}

static uint64_t mul_up(uint64_t a,uint64_t b)
{
    uint64_t p;
    if(a==SCM_STABLE_DEN)return b;
    if(b==SCM_STABLE_DEN)return a;
    p=a*b;
    return (p>>32)+((p&(SCM_STABLE_DEN-1))!=0);
}

static int charge_valid(const scm_stable_charge *s)
{
    return s->lower<=s->upper && s->value>=s->lower && s->value<=s->upper;
}

int scm_stable_charge_init(scm_stable_charge *s,int64_t lower,int64_t upper,
                          int64_t value)
{
    scm_stable_charge next;
    if(!s)return SCM_STABLE_ERR_ARGUMENT;
    if(lower>upper || value<lower || value>upper)return SCM_STABLE_ERR_RANGE;
    next.value=value;next.lower=lower;next.upper=upper;
    *s=next;return SCM_STABLE_OK;
}

int scm_stable_charge_push(scm_stable_charge *s,int32_t current_code,
                          uint32_t ticks)
{
    int64_t product,next;
    if(!s)return SCM_STABLE_ERR_ARGUMENT;
    if(!charge_valid(s))return SCM_STABLE_ERR_RANGE;
    /* Largest magnitude is 2^31*(2^32-1)=2^63-2^31, so every
     * admitted int32/uint32 product is representable in signed int64.
     */
    product=(int64_t)current_code*(int64_t)ticks;
    if((product>0 && s->value>INT64_MAX-product) ||
       (product<0 && s->value<INT64_MIN-product))
        return SCM_STABLE_ERR_OVERFLOW;
    next=s->value+product;
    if(next<s->lower || next>s->upper)return SCM_STABLE_ERR_RANGE;
    s->value=next;return SCM_STABLE_OK;
}

int scm_stable_mask_init(scm_stable_mask *s,uint64_t domain)
{
    scm_stable_mask next;
    if(!s)return SCM_STABLE_ERR_ARGUMENT;
    if(!domain)return SCM_STABLE_ERR_RANGE;
    next.domain=domain;next.active=domain;
    *s=next;return SCM_STABLE_OK;
}

int scm_stable_mask_apply(scm_stable_mask *s,uint64_t allowed)
{
    uint64_t next;
    if(!s)return SCM_STABLE_ERR_ARGUMENT;
    if(!s->domain || (s->active&~s->domain) || (allowed&~s->domain))
        return SCM_STABLE_ERR_RANGE;
    next=s->active&allowed;
    s->active=next;
    return next?SCM_STABLE_OK:SCM_STABLE_INCONSISTENT;
}

int scm_stable_attenuation_ratio(uint32_t num,uint32_t den,
                                scm_stable_attenuation *out)
{
    static const uint32_t factorial[8]={1,1,2,6,24,120,720,5040};
    scm_stable_attenuation next;
    uint64_t numerator,xlo,xhi,power_lo,power_hi;
    int64_t lower,upper;
    unsigned reductions=0,k;
    if(!out || !den)return SCM_STABLE_ERR_ARGUMENT;
    if(!num) {
        next.lower=next.upper=SCM_STABLE_DEN;
        *out=next;return SCM_STABLE_OK;
    }
    /* e>2 implies exp(-q)<2^-32 for q>=32. This branch avoids
     * constructing very large fixed-point q and is an enclosure, not zero.
     */
    if((uint64_t)num>=UINT64_C(32)*(uint64_t)den) {
        next.lower=0;next.upper=1;
        *out=next;return SCM_STABLE_OK;
    }
    /* num<=2^32-1, so the shifted numerator is strictly below 2^64.
     * q<32 gives xhi<=32*D before reduction. At most eight halvings
     * therefore put the entire interval within [0,1/8].
     */
    numerator=(uint64_t)num<<32;
    xlo=numerator/(uint64_t)den;
    xhi=ceil_div(numerator,(uint64_t)den);
    while(xhi>SCM_STABLE_DEN/8) {
        xlo>>=1;xhi=(xhi>>1)+(xhi&1);reductions++;
    }
    /* On [0,1/8], alternating-series bounds give P7(x)<=exp(-x)<=P6(x).
     * Each power and each signed term is rounded in the outward direction.
     * Every power lies in [0,D], and even a loose sum of all eight scaled
     * magnitudes is below 8*D, far inside signed int64.
     */
    lower=upper=(int64_t)SCM_STABLE_DEN;
    power_lo=power_hi=SCM_STABLE_DEN;
    for(k=1;k<=7;k++) {
        power_lo=mul_down(power_lo,xlo);
        power_hi=mul_up(power_hi,xhi);
        if(k&1) {
            lower-=(int64_t)ceil_div(power_hi,factorial[k]);
            if(k<=6)upper-=(int64_t)(power_lo/factorial[k]);
        } else {
            lower+=(int64_t)(power_lo/factorial[k]);
            upper+=(int64_t)ceil_div(power_hi,factorial[k]);
        }
    }
    /* Intersect the enclosure with the proved range exp(-x) in [0,1]. */
    next.lower=lower<0?0:(lower>(int64_t)SCM_STABLE_DEN?SCM_STABLE_DEN:(uint64_t)lower);
    next.upper=upper<0?0:(upper>(int64_t)SCM_STABLE_DEN?SCM_STABLE_DEN:(uint64_t)upper);
    for(k=0;k<reductions;k++) {
        next.lower=mul_down(next.lower,next.lower);
        next.upper=mul_up(next.upper,next.upper);
    }
    *out=next;return SCM_STABLE_OK;
}

static int interval_valid(const scm_stable_interval *s)
{
    return s->bound>=0 && s->bound<=SCM_STABLE_STATE_MAX &&
        s->lower<=s->upper && s->lower>=-s->bound && s->upper<=s->bound;
}

int scm_stable_interval_init(scm_stable_interval *s,int32_t lower,int32_t upper,
                            int32_t bound)
{
    scm_stable_interval next;
    if(!s)return SCM_STABLE_ERR_ARGUMENT;
    next.lower=lower;next.upper=upper;next.bound=bound;
    if(!interval_valid(&next))return SCM_STABLE_ERR_RANGE;
    *s=next;return SCM_STABLE_OK;
}

static int64_t corner(int32_t x,int32_t target,uint64_t attenuation)
{
    /* Convex weights sum to D. Each product and their sum are in
     * [-D*bound,D*bound] subset [-2^62,2^62], so signed arithmetic is exact.
     */
    return (int64_t)attenuation*(int64_t)x+
           (int64_t)(SCM_STABLE_DEN-attenuation)*(int64_t)target;
}

static int64_t floor_D(int64_t value)
{
    int64_t q=value/(int64_t)SCM_STABLE_DEN;
    if(value%(int64_t)SCM_STABLE_DEN<0)q--;
    return q;
}

static int64_t ceil_D(int64_t value)
{
    int64_t q=value/(int64_t)SCM_STABLE_DEN;
    if(value%(int64_t)SCM_STABLE_DEN>0)q++;
    return q;
}

int scm_stable_interval_step(scm_stable_interval *s,
                             const scm_stable_attenuation *a,int32_t target)
{
    scm_stable_interval next;
    int64_t low,high,value;
    unsigned i;
    int32_t endpoints[2];
    uint64_t coefficients[2];
    if(!s || !a)return SCM_STABLE_ERR_ARGUMENT;
    if(!interval_valid(s) || target< -s->bound || target>s->bound ||
       a->lower>a->upper || a->upper>SCM_STABLE_DEN)
        return SCM_STABLE_ERR_RANGE;
    /* Preserve the entire object, including any ABI padding, on a true
     * identity. All input/domain validation deliberately precedes this.
     */
    if(a->lower==SCM_STABLE_DEN && a->upper==SCM_STABLE_DEN)
        return SCM_STABLE_OK;
    endpoints[0]=s->lower;endpoints[1]=s->upper;
    coefficients[0]=a->lower;coefficients[1]=a->upper;
    low=high=corner(endpoints[0],target,coefficients[0]);
    for(i=1;i<4;i++) {
        value=corner(endpoints[i&1u],target,coefficients[i>>1]);
        if(value<low)low=value;
        if(value>high)high=value;
    }
    next=*s;
    next.lower=(int32_t)floor_D(low);
    next.upper=(int32_t)ceil_D(high);
    *s=next;return SCM_STABLE_OK;
}
