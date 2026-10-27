#line 1 "/workspace/scratch/d8e043c88fda/mumble-repo/experiments/live_anchor_integration_001/rolling_engine.c"
#include "rolling_engine.h"
#include "../live_anchor_bootstrap_001/history_translation.h"
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

typedef char re_objects_fit[(sizeof(re_context)==8680) ? 1 : -1];
typedef char re_planning_fit[(sizeof(re_context)+LAB_OWN_STACK_CAP+
                             LAB_RUNTIME_IRQ_CALLER_CAP<=LAB_SRAM_LIMIT) ? 1 : -1];
typedef struct { double sum,correction; } re_sum;

static size_t packed(unsigned i,unsigned j)
{
    unsigned k;if(j>i){k=i;i=j;j=k;}
    return (size_t)i*(i+1u)/2u+j;
}

static int overlap(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<=y ? y-x<na : x-y<nb;
}

static int add(re_sum *s,double x)
{
    double n;
    if(!isfinite(x))return CH_ERR_NONFINITE;
    n=s->sum+x;if(!isfinite(n))return CH_ERR_NONFINITE;
    s->correction+=fabs(s->sum)>=fabs(x)?(s->sum-n)+x:(x-n)+s->sum;
    s->sum=n;
    return isfinite(s->correction) && isfinite(n+s->correction)?CH_OK:CH_ERR_NONFINITE;
}

static double total(const re_sum *s) { return s->sum+s->correction; }
static double up(double x) { return nextafter(x,INFINITY); }
static double add_up(double x,double y) { return up(x+y); }
static double mul_up(double x,double y) { return up(x*y); }
static double allowance(unsigned n,double scale)
{
    double nu=(double)n*0x1p-53,g=up(nu/nextafter(1.-nu,-INFINITY));
    return add_up(mul_up(g,scale),mul_up((double)n,0x0.0000000000001p-1022));
}

static int ready(const re_context *c)
{
    uint64_t pending;
    if(!c)return CH_ERR_ARGUMENT;
    if(!c->core.bank.available)return CH_ERR_UNAVAILABLE;
    if((c->inputs.phase_and_flags&RE_PHASE_MASK)!=RE_PHASE_READY)return RE_ERR_STATE;
    if(c->inputs.block_count>LAB_BLOCK_DEPTH || c->inputs.ingress_count>LAB_INGRESS_DEPTH ||
       c->inputs.ingress_head>=LAB_INGRESS_DEPTH)return RE_ERR_STATE;
    pending=(uint64_t)c->inputs.block_count+c->inputs.ingress_count;
    if(c->core.bank.next_index>UINT64_MAX-pending ||
       c->core.bank.next_index+pending!=c->inputs.next_ingress_sequence)return RE_ERR_STATE;
    return CH_OK;
}

static int input_domain(const adc12_reading *r)
{
    if(!isfinite(r->dt_s) || !isfinite(r->current_A) || !isfinite(r->voltage_V) ||
       !isfinite(r->temperature_C) || !isfinite(r->voltage_V/RE_SIGMA_V))return CH_ERR_NONFINITE;
    return r->dt_s>=0. && r->dt_s<=1. && fabs(r->current_A)<=.25 ? CH_OK:CH_ERR_DOMAIN;
}

int re_invalidate(re_context *c,int reason)
{
    if(!c)return CH_ERR_ARGUMENT;
    c->core.bank.available=0;c->core.bank.last_error=reason;
    c->inputs.phase_and_flags=(c->inputs.phase_and_flags&~RE_PHASE_MASK)|RE_PHASE_FAILED;
    return reason;
}

int re_init(re_context *c,const unsigned char id[32],const adc12_calibration *cal)
{
    adc12_raw_sample raw={0,{0,0,0}};adc12_reading decoded;int status;
    if(!c || !id || !cal)return CH_ERR_ARGUMENT;
    if(overlap(c,sizeof(*c),id,32) || overlap(c,sizeof(*c),cal,sizeof(*cal)))return RE_ERR_ALIAS;
    if(adc12_convert(&raw,cal,&decoded)!=ADC12_OK)return RE_ERR_CALIBRATION;
    memset(c,0,sizeof(*c));
    memcpy(c->core.bank.source_id,id,32);c->calibration=*cal;
    memcpy(c->core.bank.origin,ch_public_mean,sizeof(c->core.bank.origin));
    memcpy(c->core.bank.estimate,ch_public_mean,sizeof(c->core.bank.estimate));
    status=rm_init_jet(&c->core.bank.jet,ch_public_mean);
    if(status)return re_invalidate(c,status);
    c->core.bank.available=1;
    c->inputs.phase_and_flags=RE_PHASE_READY|RE_FLAG_TEMPERATURE_UNMODELED;
    return CH_OK;
}

int re_offer(re_context *c,const unsigned char id[32],uint64_t sequence,
             const adc12_raw_sample *raw)
{
    adc12_reading decoded;unsigned tail;int status=ready(c);
    if(status)return status;
    if(!id || !raw)return CH_ERR_ARGUMENT;
    if(overlap(c,sizeof(*c),id,32) || overlap(c,sizeof(*c),raw,sizeof(*raw)))return RE_ERR_ALIAS;
    if(memcmp(id,c->core.bank.source_id,32))return CH_ERR_SOURCE;
    if(sequence!=c->inputs.next_ingress_sequence)return CH_ERR_ORDER;
    if(sequence==UINT64_MAX)return CH_ERR_OVERFLOW;
    if(c->inputs.ingress_count==LAB_INGRESS_DEPTH)return RE_ERR_FULL;
    if(adc12_convert(raw,&c->calibration,&decoded)!=ADC12_OK)return CH_ERR_DOMAIN;
    status=input_domain(&decoded);if(status)return status;
    tail=(c->inputs.ingress_head+c->inputs.ingress_count)%LAB_INGRESS_DEPTH;
    c->inputs.ingress[tail]=*raw;++c->inputs.ingress_count;
    ++c->inputs.next_ingress_sequence;return CH_OK;
}

int re_admit(re_context *c)
{
    int status=ready(c);if(status)return status;
    while(c->inputs.block_count<LAB_BLOCK_DEPTH && c->inputs.ingress_count) {
        c->inputs.retained[c->inputs.block_count++]=c->inputs.ingress[c->inputs.ingress_head];
        c->inputs.ingress_head=(c->inputs.ingress_head+1u)%LAB_INGRESS_DEPTH;
        --c->inputs.ingress_count;
    }
    return CH_OK;
}

static int charge_extrema(re_context *c,double *lo,double *hi)
{
    double charge=c->core.bank.jet.model.charge_Ah;unsigned k;int status;
    *lo=c->core.bank.charge_min_Ah;*hi=c->core.bank.charge_max_Ah;
    for(k=0;k<c->inputs.block_count;k++) {
        if(adc12_convert(&c->inputs.retained[k],&c->calibration,
                         &c->core.workspace.query.decoded)!=ADC12_OK)return CH_ERR_DOMAIN;
        status=input_domain(&c->core.workspace.query.decoded);if(status)return status;
        charge+=c->core.workspace.query.decoded.current_A*
                c->core.workspace.query.decoded.dt_s/3600.;
        if(!isfinite(charge))return CH_ERR_NONFINITE;
        *lo=fmin(*lo,charge);*hi=fmax(*hi,charge);
    }
    return CH_OK;
}

static int point_support(const double *x,double cmin,double cmax,double *slack)
{
    double s=DBL_MAX,Q,zlo,zhi;unsigned i;
    for(i=0;i<CH_DIM;i++) {
        if(!isfinite(x[i]))return CH_ERR_NONFINITE;
        s=fmin(s,fmin(x[i]-ch_lower[i],ch_upper[i]-x[i]));
    }
    Q=exp(x[5]);if(!isfinite(Q) || !(Q>0.))return CH_ERR_NONFINITE;
    zlo=x[11]-cmax/Q;zhi=x[11]-cmin/Q;
    if(!isfinite(zlo) || !isfinite(zhi))return CH_ERR_NONFINITE;
    s=fmin(s,fmin(zlo,1.-zhi));if(slack)*slack=s;
    return s>=0.?CH_OK:CH_ERR_DOMAIN;
}

static double qr(const ch_bank *b,unsigned row,unsigned col)
{
    return col<row?0.:b->upper[ht_index(row,col)];
}

static double displacement(const ch_bank *b,const double *x,unsigned i)
{
    return (x[i]-b->origin[i])/ch_public_sd[i];
}

static int polynomial_row(const ch_bank *b,const double *x,unsigned row,
                           double *residual,double *absolute)
{
    re_sum s={0,0},a={0,0};unsigned k;
    for(k=row;k<CH_AUG;k++) {
        double feature=k<20 ? displacement(b,x,ht_pair[k][0])*displacement(b,x,ht_pair[k][1]):
                       k<36 ? displacement(b,x,k-20u):1.;
        double term=qr(b,row,k)*feature;
        if(add(&s,term) || add(&a,fabs(term)))return CH_ERR_NONFINITE;
    }
    *residual=total(&s);*absolute=total(&a);return CH_OK;
}

static double polynomial_derivative(const ch_bank *b,const double *x,
                                     unsigned row,unsigned coordinate)
{
    re_sum s={0,0};unsigned k;
    if(add(&s,qr(b,row,20u+coordinate)))return NAN;
    for(k=row;k<20;k++) {
        unsigned a=ht_pair[k][0],d=ht_pair[k][1];double q=qr(b,row,k);
        if(a==coordinate && add(&s,q*displacement(b,x,d)))return NAN;
        if(d==coordinate && add(&s,q*displacement(b,x,a)))return NAN;
    }
    return total(&s)/ch_public_sd[coordinate];
}

static double precision(unsigned i)
{
    double sd=i==5?.20951093757861336:ch_public_sd[i];return 1./(sd*sd);
}

static int prior(re_context *c,int derivatives)
{
    const double *x=c->core.workspace.query.point;
    re_sum common={0,0},normal={0,0};unsigned i;
    double q0,q1,l0,l1,m,ls,w1,dp,cost;
    if(c->core.bank.prior_evaluations==UINT64_MAX)return CH_ERR_OVERFLOW;
    ++c->core.bank.prior_evaluations;
    for(i=0;i<CH_DIM;i++) {
        double sd=i==5?.20951093757861336:ch_public_sd[i];
        if(add(&normal,log(sd*sd)))return CH_ERR_NONFINITE;
        if(i!=5 && add(&common,(x[i]-ch_public_mean[i])*(x[i]-ch_public_mean[i])*precision(i)))
            return CH_ERR_NONFINITE;
    }
    q0=x[5]-(-3.0907210901048416);q1=x[5]-(-2.536100343415231);
    l0=-.5*q0*q0*precision(5);l1=-.5*q1*q1*precision(5);
    m=fmax(l0,l1);ls=m+log(exp(l0-m)+exp(l1-m));w1=exp(l1-ls);
    cost=.5*total(&common)+.5*total(&normal)+
         8.*log(2.*3.141592653589793238462643383279502884)+log(2.)-ls;
    if(!isfinite(cost) || !isfinite(w1))return CH_ERR_NONFINITE;
    c->core.result.evidence.prior_cost=cost;
    c->core.result.evidence.total_cost=c->core.result.evidence.likelihood_cost+cost;
    c->core.result.evidence.flags|=CH_FLAG_PRIOR_INCLUDED;
    if(derivatives) {
        c->core.result.evidence.flags|=CH_FLAG_PRIOR_MAJORIZER;
        for(i=0;i<CH_DIM;i++) {
            double g=(x[i]-ch_public_mean[i])*precision(i);
            if(i==5){dp=(-3.0907210901048416+2.536100343415231)*precision(i);g=q0*precision(i)+w1*dp;}
            c->core.workspace.query.gradient[i]+=g;
            c->core.workspace.query.packed[packed(i,i)]+=precision(i);
            if(!isfinite(c->core.workspace.query.gradient[i]) ||
               !isfinite(c->core.workspace.query.packed[packed(i,i)]))return CH_ERR_NONFINITE;
        }
    }
    return isfinite(c->core.result.evidence.total_cost)?CH_OK:CH_ERR_NONFINITE;
}

static int endpoint(re_context *c,double support)
{
    const lab_query_state *s=&c->core.workspace.query.state;
    const double *x=c->core.workspace.query.point;
    ch_result *r=&c->core.result.evidence;double minimum;unsigned i;
    r->detail.endpoint.SOC=s->z;r->detail.endpoint.min_support_slack=support;
    minimum=fmin(s->z,1.-s->z);
    for(i=0;i<3;i++) {
        r->detail.endpoint.v[i]=s->f[i]*x[7+i]+s->a[i]*x[12+i];
        if(!isfinite(r->detail.endpoint.v[i]))return CH_ERR_NONFINITE;
        minimum=fmin(minimum,.25-fabs(r->detail.endpoint.v[i]));
    }
    r->detail.endpoint.h=s->hb+s->ha*x[15];
    if(!isfinite(r->detail.endpoint.h) || !isfinite(s->z))return CH_ERR_NONFINITE;
    minimum=fmin(minimum,1.-fabs(r->detail.endpoint.h));
    r->detail.endpoint.min_endpoint_slack=minimum;
    if(minimum<0.)r->flags|=CH_FLAG_ENDPOINT_INVALID;
    if(c->inputs.phase_and_flags&RE_FLAG_BOUNDARY_APPROXIMATE)r->flags|=CH_FLAG_ENDPOINT_APPROXIMATE;
    for(i=0;i<CH_DIM;i++)if(x[i]!=c->core.bank.origin[i])r->flags|=CH_FLAG_ENDPOINT_APPROXIMATE;
    return CH_OK;
}

int iq_real_engine_query(re_context *c,int derivatives,int include_prior)
{
    re_sum cost={0,0},absolute={0,0};double cmin,cmax,slack;unsigned row,i,j,k;
    const double *x;int status=ready(c);
    if(status)return status;
    if((derivatives!=0 && derivatives!=1) || (include_prior!=0 && include_prior!=1))return CH_ERR_ARGUMENT;
    x=c->core.workspace.query.point;
    status=charge_extrema(c,&cmin,&cmax);if(status)return status;
    status=point_support(x,cmin,cmax,&slack);if(status)return status;
    if(c->core.bank.query_evaluations==UINT64_MAX)return CH_ERR_OVERFLOW;
    ++c->core.bank.query_evaluations;memset(&c->core.result,0,sizeof(c->core.result));
    if(derivatives) {
        memset(c->core.workspace.query.gradient,0,sizeof(c->core.workspace.query.gradient));
        memset(c->core.workspace.query.packed,0,sizeof(c->core.workspace.query.packed));
    }
    for(row=0;row<CH_AUG;row++) {
        double r,a;
        status=polynomial_row(&c->core.bank,x,row,&r,&a);if(status)return status;
        if(add(&cost,.5*r*r) || add(&absolute,.5*a*a))return CH_ERR_NONFINITE;
        if(derivatives) {
            /* The block state is not live until rm_query_init. Reuse its
             * first128B through the explicit proposal phase's vector. */
            for(i=0;i<CH_DIM;i++) {
                double di=polynomial_derivative(&c->core.bank,x,row,i);
                c->core.workspace.proposal.majorizer[i]=di;
                c->core.workspace.query.gradient[i]+=r*di;
                if(!isfinite(di) || !isfinite(c->core.workspace.query.gradient[i]))return CH_ERR_NONFINITE;
            }
            for(i=0;i<CH_DIM;i++)for(j=0;j<=i;j++)
                c->core.workspace.query.packed[packed(i,j)]+=
                    c->core.workspace.proposal.majorizer[i]*c->core.workspace.proposal.majorizer[j];
        }
    }
    status=rm_query_init(&c->core.workspace.query.state,&c->core.bank.jet,c->core.bank.origin,x);
    if(status)return status;
    for(k=0;k<c->inputs.block_count;k++) {
        double r,a;
        if(adc12_convert(&c->inputs.retained[k],&c->calibration,&c->core.workspace.query.decoded)!=ADC12_OK)
            return CH_ERR_DOMAIN;
        if(c->core.bank.model_steps==UINT64_MAX)return CH_ERR_OVERFLOW;
        ++c->core.bank.model_steps;
        status=rm_query_step(&c->core.workspace.query.state,x,&c->core.workspace.query.decoded);
        if(status)return status;
        r=(c->core.workspace.query.state.mu-c->core.workspace.query.decoded.voltage_V)/RE_SIGMA_V;
        a=(fabs(c->core.workspace.query.state.mu)+fabs(c->core.workspace.query.decoded.voltage_V))/RE_SIGMA_V;
        if(add(&cost,.5*r*r) || add(&absolute,.5*a*a))return CH_ERR_NONFINITE;
        if(derivatives)for(i=0;i<CH_DIM;i++) {
            double di=rm_query_derivative(&c->core.workspace.query.state,x,&c->core.workspace.query.decoded,i)/RE_SIGMA_V;
            c->core.workspace.query.gradient[i]+=r*di;
            if(!isfinite(di) || !isfinite(c->core.workspace.query.gradient[i]))return CH_ERR_NONFINITE;
            for(j=0;j<=i;j++) {
                double dj=rm_query_derivative(&c->core.workspace.query.state,x,&c->core.workspace.query.decoded,j)/RE_SIGMA_V;
                c->core.workspace.query.packed[packed(i,j)]+=di*dj;
            }
        }
    }
    if(derivatives)for(i=0;i<CH_PACKED;i++)if(!isfinite(c->core.workspace.query.packed[i]))return CH_ERR_NONFINITE;
    c->core.result.evidence.likelihood_cost=total(&cost);
    c->core.result.evidence.total_cost=total(&cost);
    c->core.result.evidence.cost_absolute_scale=total(&absolute);
    c->core.result.evidence.flags=CH_FLAG_FEASIBLE|CH_FLAG_COST_AVAILABLE;
    if(include_prior){status=prior(c,derivatives);if(status)return status;}
    return endpoint(c,slack);
}

static int search_stop(re_context *c,unsigned round,unsigned fraction,
                        unsigned reason,int status)
{
    c->core.result.evidence.round=round;c->core.result.evidence.fraction=fraction;
    c->core.result.evidence.stop_reason=reason;return status;
}

int re_refine(re_context *c,unsigned max_rounds)
{
    unsigned round,i,f;int status=ready(c);
    if(status)return status;
    if(!max_rounds || max_rounds>RE_MAX_ROUNDS)return CH_ERR_ARGUMENT;
    if(!c->inputs.block_count)return RE_ERR_EMPTY;
    for(round=0;round<max_rounds;round++) {
        int accepted=0;
        if(c->core.bank.proposal_rounds==UINT64_MAX)return CH_ERR_OVERFLOW;
        ++c->core.bank.proposal_rounds;
        memcpy(c->core.workspace.query.point,c->core.bank.estimate,sizeof(c->core.bank.estimate));
        status=re_query(c,1,1);
        if(status)return search_stop(c,round,UINT32_MAX,CH_STOP_QUERY,status);
        if(c->core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID)
            return search_stop(c,round,UINT32_MAX,CH_STOP_QUERY,CH_UNRESOLVED);
        c->auxiliary.refine.base_cost=c->core.result.evidence.total_cost;
        c->auxiliary.refine.base_prior=c->core.result.evidence.prior_cost;
        c->auxiliary.refine.base_abs=c->core.result.evidence.cost_absolute_scale;
        c->auxiliary.refine.input.anchor=c->core.bank.estimate;
        c->auxiliary.refine.input.sd=ch_public_sd;
        c->auxiliary.refine.input.lower=ch_lower;
        c->auxiliary.refine.input.upper=ch_upper;
        status=charge_extrema(c,&c->auxiliary.refine.input.charge_min_Ah,
                               &c->auxiliary.refine.input.charge_max_Ah);
        if(status)return search_stop(c,round,UINT32_MAX,CH_STOP_QUERY,status);
        status=ss_propose(&c->auxiliary.refine.input,&c->core.workspace.proposal,&c->core.result.proposal);
        if(status) {
            unsigned reason=CH_STOP_METRIC;
            if(status==SS_UNRESOLVED) {
                reason=c->core.result.proposal.reason==SS_REASON_ROUNDING ? RE_STOP_ROUNDING:CH_STOP_DIRECTION;
                status=CH_UNRESOLVED;
            } else if(status==SS_ERR_METRIC)status=CH_UNRESOLVED;
            else if(status==SS_ERR_NONFINITE)status=CH_ERR_NONFINITE;
            else if(status==SS_ERR_DOMAIN)status=CH_ERR_DOMAIN;
            else status=CH_ERR_ARGUMENT;
            memset(&c->core.result,0,sizeof(c->core.result));
            return search_stop(c,round,UINT32_MAX,reason,status);
        }
        c->auxiliary.refine.slope=c->core.result.proposal.original_slope;
        c->auxiliary.refine.slope_allowance=c->core.result.proposal.original_slope_allowance;
        memset(&c->core.result,0,sizeof(c->core.result));
        /* The Cholesky metric is now dead. Keep the EXACT full endpoint in
         * its first16 doubles, outside the block state/decoded overlay. */
        for(i=0;i<CH_DIM;i++)c->core.workspace.query.packed[i]=c->core.workspace.query.point[i];
        for(f=0;f<RE_FRACTIONS;f++) {
            double alpha=ldexp(1.,-(int)f),delta,guard,required,combine;
            for(i=0;i<CH_DIM;i++)c->core.workspace.query.point[i]=f==0?
                c->core.workspace.query.packed[i]:c->core.bank.estimate[i]+
                alpha*(c->core.workspace.query.packed[i]-c->core.bank.estimate[i]);
            status=re_query(c,0,1);
            if(status==CH_ERR_DOMAIN) {
                memset(&c->core.result,0,sizeof(c->core.result));
                continue;
            }
            if(status)return search_stop(c,round,f,CH_STOP_QUERY,status);
            delta=c->auxiliary.refine.base_cost-c->core.result.evidence.total_cost;
            guard=add_up(allowance(16384,add_up(c->auxiliary.refine.base_abs,c->core.result.evidence.cost_absolute_scale)),
                         allowance(256,add_up(fabs(c->auxiliary.refine.base_prior),fabs(c->core.result.evidence.prior_cost))));
            guard=add_up(guard,allowance(16,add_up(fabs(c->auxiliary.refine.base_cost),fabs(c->core.result.evidence.total_cost))));
            required=mul_up(.25,mul_up(alpha,add_up(c->auxiliary.refine.slope,c->auxiliary.refine.slope_allowance)));
            combine=allowance(32,add_up(add_up(fabs(delta),guard),required));
            if(!isfinite(delta) || !isfinite(guard) || !isfinite(required) || !isfinite(combine))
                return search_stop(c,round,f,CH_STOP_QUERY,CH_ERR_NONFINITE);
            c->core.result.evidence.detail.step.slope=c->auxiliary.refine.slope;
            c->core.result.evidence.detail.step.slope_allowance=c->auxiliary.refine.slope_allowance;
            c->core.result.evidence.detail.step.cost_decrease=delta;
            c->core.result.evidence.detail.step.cost_allowance=guard;
            c->core.result.evidence.detail.step.armijo_required=required;
            c->core.result.evidence.detail.step.combine_allowance=combine;
            c->core.result.evidence.detail.step.alpha=alpha;
            if(!(c->core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID) &&
               delta>guard && delta-guard>required+combine) {
                if(c->core.bank.accepted_steps==UINT64_MAX)return CH_ERR_OVERFLOW;
                memcpy(c->core.bank.estimate,c->core.workspace.query.point,sizeof(c->core.bank.estimate));
                ++c->core.bank.accepted_steps;
                c->core.result.evidence.flags|=CH_FLAG_ACCEPTED;accepted=1;break;
            }
        }
        if(!accepted)return search_stop(c,round,RE_FRACTIONS-1u,CH_STOP_NO_TRIAL,CH_UNRESOLVED);
        search_stop(c,round,f,CH_STOP_ROUND_LIMIT,CH_UNRESOLVED);
    }
    return CH_UNRESOLVED;
}

static int qr_append(ch_bank *b,double *row)
{
    unsigned i,k;
    for(i=0;i<CH_AUG;i++)if(!isfinite(row[i]))return CH_ERR_NONFINITE;
    for(i=0;i<CH_AUG;i++) {
        size_t ii=ht_index(i,i);double a=b->upper[ii],v=row[i],scale,aa,bb,h,cs,sn,r;
        if(!isfinite(a))return CH_ERR_NONFINITE;
        if(v==0.)continue;
        scale=fmax(fabs(a),fabs(v));aa=a/scale;bb=v/scale;h=hypot(aa,bb);
        cs=aa/h;sn=bb/h;r=scale*h;
        if(!isfinite(r) || !(r>0.))return CH_ERR_NONFINITE;
        b->upper[ii]=r;row[i]=0.;
        for(k=i+1;k<CH_AUG;k++) {
            size_t ik=ht_index(i,k);double old=b->upper[ik],tail=row[k];
            b->upper[ik]=cs*old+sn*tail;row[k]=-sn*old+cs*tail;
            if(!isfinite(b->upper[ik]) || !isfinite(row[k]))return CH_ERR_NONFINITE;
        }
    }
    return CH_OK;
}

int re_commit(re_context *c)
{
    unsigned i,k,count;int changed=0,status=ready(c);
    if(status)return status;
    count=c->inputs.block_count;if(!count)return RE_ERR_EMPTY;
    if(c->core.bank.qr_rows>UINT64_MAX-count || c->core.bank.model_steps>UINT64_MAX-2u*count ||
       c->core.bank.next_index>UINT64_MAX-count)return CH_ERR_OVERFLOW;
    memcpy(c->core.workspace.query.point,c->core.bank.estimate,sizeof(c->core.bank.estimate));
    /* A complete read-only physical/block preflight. Work counters advance,
     * but committed evidence/state/cursors and raw ownership do not. */
    status=re_query(c,0,0);if(status)return status;
    if(c->core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID)return CH_ERR_DOMAIN;
    status=rm_transport(&c->core.bank.jet,c->core.bank.origin,c->core.bank.estimate,
                         &c->core.workspace.merge.prospective);
    if(status)return status;
    for(i=0;i<CH_DIM;i++) {
        c->core.workspace.merge.row[i]=(c->core.bank.estimate[i]-c->core.bank.origin[i])/ch_public_sd[i];
        if(c->core.bank.estimate[i]!=c->core.bank.origin[i])changed=1;
    }
    c->inputs.phase_and_flags=(c->inputs.phase_and_flags&~RE_PHASE_MASK)|RE_PHASE_COMMITTING;
    status=ht_translate(c->core.bank.upper,c->core.workspace.merge.row);
    if(status)return re_invalidate(c,CH_ERR_NONFINITE);
    c->core.bank.jet=c->core.workspace.merge.prospective;
    if(changed && c->core.bank.next_index)c->inputs.phase_and_flags|=RE_FLAG_BOUNDARY_APPROXIMATE;
    memcpy(c->core.bank.origin,c->core.bank.estimate,sizeof(c->core.bank.origin));
    for(k=0;k<count;k++) {
        if(adc12_convert(&c->inputs.retained[k],&c->calibration,&c->core.workspace.merge.decoded)!=ADC12_OK)
            return re_invalidate(c,CH_ERR_DOMAIN);
        c->core.workspace.merge.model_sample.dt=c->core.workspace.merge.decoded.dt_s;
        c->core.workspace.merge.model_sample.current=c->core.workspace.merge.decoded.current_A;
        c->core.workspace.merge.model_sample.voltage=c->core.workspace.merge.decoded.voltage_V;
        c->core.workspace.merge.prospective=c->core.bank.jet;
        if(c->core.bank.model_steps==UINT64_MAX)return re_invalidate(c,CH_ERR_OVERFLOW);
        ++c->core.bank.model_steps;
        status=rm_merge_step(&c->core.workspace.merge.prospective,c->core.bank.origin,
                             &c->core.workspace.merge.model_sample,RE_SIGMA_V,c->core.workspace.merge.row);
        if(status)return re_invalidate(c,status);
        status=qr_append(&c->core.bank,c->core.workspace.merge.row);
        if(status)return re_invalidate(c,status);
        c->core.bank.jet=c->core.workspace.merge.prospective;
        c->core.bank.charge_min_Ah=fmin(c->core.bank.charge_min_Ah,c->core.bank.jet.model.charge_Ah);
        c->core.bank.charge_max_Ah=fmax(c->core.bank.charge_max_Ah,c->core.bank.jet.model.charge_Ah);
    }
    c->core.bank.next_index+=count;c->core.bank.qr_rows+=count;
    memset(c->inputs.retained,0,count*sizeof(c->inputs.retained[0]));
    c->inputs.block_count=0;
    c->inputs.phase_and_flags=(c->inputs.phase_and_flags&~RE_PHASE_MASK)|RE_PHASE_READY|RE_FLAG_HISTORY_APPROXIMATE;
    return CH_OK;
}

int re_process(re_context *c,unsigned max_rounds)
{
    uint32_t reason,round,fraction;int status=ready(c);
    if(status)return status;
    if(!max_rounds || max_rounds>RE_MAX_ROUNDS)return CH_ERR_ARGUMENT;
    if(!c->inputs.block_count)return RE_ERR_EMPTY;
    status=re_refine(c,max_rounds);
    if(status<0)return re_invalidate(c,status);
    reason=c->core.result.evidence.stop_reason;round=c->core.result.evidence.round;
    fraction=c->core.result.evidence.fraction;
    status=re_commit(c);
    if(status)return re_invalidate(c,status);
    c->core.result.evidence.stop_reason=reason;c->core.result.evidence.round=round;
    c->core.result.evidence.fraction=fraction;return CH_OK;
}
