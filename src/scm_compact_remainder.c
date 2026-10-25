/* Layout-only adaptation of the preserved B002 remainder reference.
 * The recurrence and arithmetic order below are intentionally unchanged. */
#include "scm_compact_remainder.h"
#include <math.h>
#include <string.h>

static int bounded(double x,double lo,double hi)
{
    return isfinite(x) && x>=lo-1e-12 && x<=hi+1e-12;
}

/* Mirror the reference's declared supports without allocating a replay or
 * evidence object. Bounds qualify the anchor; the envelope uses the ENTIRE
 * configured rectangle, including any infeasible parts, for safe supersets.
 */
static int config_valid(const scm_evidence_config *c)
{
    int i,n=c->modes,nt=scm_model_ntheta(n),na=scm_model_nalpha(n);
    if(!nt || !c->max_event_samples || !isfinite(c->sigma) || !(c->sigma>0) ||
       !isfinite(c->residual_rms_limit_sigma) || !(c->residual_rms_limit_sigma>0))return 0;
    for(i=0;i<nt+na;i++)if(!isfinite(c->scale[i]) || !(c->scale[i]>0) ||
                           !isfinite(c->radius[i]) || c->radius[i]<0)return 0;
    for(i=0;i<n;i++) {
        const double lo3[3]={.015,.15,1.5},hi3[3]={.15,1.5,30};
        double lo=n==3?lo3[i]:(i?.8:.015),hi=n==3?hi3[i]:(i?180.:30.);
        if(!bounded(c->theta[i],log(lo),log(hi)))return 0;
    }
    if(!bounded(c->theta[n],log(5.),log(1200.)) ||
       !bounded(c->theta[n+1],log(5.),log(1200.)) ||
       !bounded(c->theta[n+2],.2,.95) ||
       !bounded(c->theta[n+3],log(.03),log(.10)))return 0;
    for(i=0;i<=n;i++)if(!bounded(c->alpha[i],0,1))return 0;
    if(!bounded(c->alpha[n+1],0,.1))return 0;
    for(i=0;i<n;i++)if(!bounded(c->alpha[n+2+i],-.08,.08))return 0;
    return bounded(c->alpha[2+2*n],-.1,.1) &&
           fabs(c->alpha[2+2*n])<=c->alpha[n+1]+1e-12;
}

static int exponential_box(double anchor,double halfwidth,double *lo,double *hi)
{
    if(!isfinite(halfwidth) || !isfinite(anchor-halfwidth) || !isfinite(anchor+halfwidth))return 0;
    *lo=exp(anchor-halfwidth);*hi=exp(anchor+halfwidth);
    return isfinite(*lo) && *lo>0 && isfinite(*hi) && *hi>0;
}

static void pair(scm_compact_remainder *r,int a,int b)
{
    int k=r->pair_count++;
    r->pair_row[k]=(unsigned char)a;r->pair_column[k]=(unsigned char)b;
}

int scm_compact_remainder_init(scm_compact_remainder *r,const scm_evidence_config *c)
{
    scm_compact_remainder next;
    double unused;
    int i,n,nt;
    if(!r || !c)return SCM_REMAINDER_ERR_ARGUMENT;
    if(c->ocv.n)return SCM_REMAINDER_ERR_UNSUPPORTED;
    if(!config_valid(c))return SCM_REMAINDER_ERR_ARGUMENT;
    memset(&next,0,sizeof(next));next.config=c;next.paired_ancestry=1;n=c->modes;nt=scm_model_ntheta(n);
    next.dim=nt+scm_model_nalpha(n);
    for(i=0;i<n;i++) {
        if(!exponential_box(c->theta[i],c->scale[i]*c->radius[i],&next.tau_lo[i],&next.tau_hi[i]))
            return SCM_REMAINDER_ERR_NONFINITE;
        next.R_abs_max[i]=fabs(c->alpha[1+i])+c->scale[nt+1+i]*c->radius[nt+1+i];
        next.v_abs_max[i]=fabs(c->alpha[n+2+i])+c->scale[nt+n+2+i]*c->radius[nt+n+2+i];
        if(!isfinite(next.R_abs_max[i]) || !isfinite(next.v_abs_max[i]))return SCM_REMAINDER_ERR_NONFINITE;
        pair(&next,i,i);pair(&next,i,nt+1+i);pair(&next,i,nt+n+2+i);
    }
    for(i=0;i<2;i++)if(!exponential_box(c->theta[n+i],c->scale[n+i]*c->radius[n+i],
                                      &next.gamma_lo[i],&next.gamma_hi[i]))
        return SCM_REMAINDER_ERR_NONFINITE;
    if(!exponential_box(c->theta[n+3],c->scale[n+3]*c->radius[n+3],&next.Q_lo,&unused))
        return SCM_REMAINDER_ERR_NONFINITE;
    next.H_abs_max=fabs(c->alpha[n+1])+c->scale[nt+n+1]*c->radius[nt+n+1];
    next.u_abs_max=fabs(c->alpha[2+2*n])+c->scale[nt+2+2*n]*c->radius[nt+2+2*n];
    if(!isfinite(next.H_abs_max) || !isfinite(next.u_abs_max))return SCM_REMAINDER_ERR_NONFINITE;
    pair(&next,n,n);pair(&next,n,n+1);pair(&next,n+1,n+1);
    pair(&next,n,nt+n+1);pair(&next,n,nt+2+2*n);
    pair(&next,n+1,nt+n+1);pair(&next,n+1,nt+2+2*n);
    pair(&next,n+2,n+2);pair(&next,n+2,n+3);pair(&next,n+3,n+3);
    *r=next;return SCM_REMAINDER_OK;
}

/* q*exp(-q) and |q*(q-1)*exp(-q)| evaluated without inf*0 or q*q overflow.
 * q=+infinity denotes the limit zero. This is ordinary libm evaluation;
 * it deliberately makes no directed-rounding claim.
 */
static double q_exp(double q)
{
    if(q==0 || isinf(q))return 0;
    return exp(log(q)-q);
}

static double second_exp(double q)
{
    if(q==0 || q==1 || isinf(q))return 0;
    return exp(log(q)+log(fabs(q-1))-q);
}

static double max_first(double lo,double hi)
{
    double b=fmax(q_exp(lo),q_exp(hi));
    if(lo<=1 && hi>=1)b=fmax(b,exp(-1.));
    return b;
}

static double max_second(double lo,double hi)
{
    double q0=(3.-sqrt(5.))/2.,q1=(3.+sqrt(5.))/2.;
    double b=fmax(second_exp(lo),second_exp(hi));
    if(lo<=q0 && hi>=q0)b=fmax(b,second_exp(q0));
    if(lo<=q1 && hi>=q1)b=fmax(b,second_exp(q1));
    return b;
}

/* Interval enclosure of target+e*(old-target). Correlation is discarded only
 * outward in real arithmetic: all four product corners are included.
 */
static void range_step(double *lo,double *hi,double target,double elo,double ehi)
{
    double a=*lo-target,b=*hi-target;
    double p0=elo*a,p1=elo*b,p2=ehi*a,p3=ehi*b;
    *lo=target+fmin(fmin(p0,p1),fmin(p2,p3));
    *hi=target+fmax(fmax(p0,p1),fmax(p2,p3));
}

static int add_bound(scm_compact_remainder *r,int k,double unscaled)
{
    int i=r->pair_row[k],j=r->pair_column[k];
    double value;
    if(!isfinite(unscaled) || unscaled<0)return SCM_REMAINDER_ERR_NONFINITE;
    value=unscaled*r->config->scale[i]*r->config->scale[j]/r->config->sigma;
    if(!isfinite(value))return SCM_REMAINDER_ERR_NONFINITE;
    r->last_bound[k]=value;r->coefficient[k]=hypot(r->coefficient[k],value);
    return isfinite(r->coefficient[k])?SCM_REMAINDER_OK:SCM_REMAINDER_ERR_NONFINITE;
}

static int advance(scm_compact_remainder *r,const unsigned char *id,uint64_t index,const scm_sample *sample)
{
    double dt,I,step_charge,wabs,ha_first[2],ha_second[3],qlo[2],qhi[2];
    int n=r->config->modes,i,j,k=0,status;
    if(memcmp(id,r->config->source_id,SCM_EVIDENCE_SOURCE_BYTES))return SCM_REMAINDER_ERR_SOURCE;
    if(index!=r->next_index)return SCM_REMAINDER_ERR_ORDER;
    if(index==UINT64_MAX)return SCM_REMAINDER_ERR_OVERFLOW;
    dt=sample->dt;I=sample->current;
    if(!isfinite(dt) || !isfinite(I) || !isfinite(sample->voltage))return SCM_REMAINDER_ERR_NONFINITE;
    if(dt<0)return SCM_REMAINDER_ERR_ARGUMENT;
    step_charge=I*dt/3600.;r->charge_Ah+=step_charge;r->elapsed+=dt;
    if(!isfinite(r->charge_Ah) || !isfinite(r->elapsed))return SCM_REMAINDER_ERR_NONFINITE;
    {
        double z=r->config->theta[n+2]-r->charge_Ah/exp(r->config->theta[n+3]);
        if(!isfinite(z) || z<0 || z>1)return SCM_REMAINDER_ERR_DOMAIN;
    }
    r->charge_min_Ah=fmin(r->charge_min_Ah,r->charge_Ah);
    r->charge_max_Ah=fmax(r->charge_max_Ah,r->charge_Ah);
    for(i=0;i<n;i++) {
        double da,dda;
        if(dt>0) {
            double lo=dt/r->tau_hi[i],hi=dt/r->tau_lo[i];
            double eh=exp(-lo),el=exp(-hi),de=max_first(lo,hi),dde=max_second(lo,hi);
            double distance=fmax(fabs(r->f_lo[i]-I),fabs(r->f_hi[i]-I));
            double old_first=r->f_first[i];
            r->f_second[i]=eh*r->f_second[i]+2*de*old_first+dde*distance;
            r->f_first[i]=eh*old_first+de*distance;
            range_step(&r->f_lo[i],&r->f_hi[i],I,el,eh);
            if(!isfinite(r->f_lo[i]) || !isfinite(r->f_hi[i]))return SCM_REMAINDER_ERR_NONFINITE;
        }
        da=max_first(r->elapsed/r->tau_hi[i],r->elapsed/r->tau_lo[i]);
        dda=max_second(r->elapsed/r->tau_hi[i],r->elapsed/r->tau_lo[i]);
        status=add_bound(r,k++,r->R_abs_max[i]*r->f_second[i]+r->v_abs_max[i]*dda);if(status)return status;
        status=add_bound(r,k++,r->f_first[i]);if(status)return status;
        status=add_bound(r,k++,da);if(status)return status;
    }
    if(dt>0 && I!=0) {
        int active=I>0?0:1;
        double sign=I>0?1.:-1.,amount=fabs(step_charge);
        double lo=r->gamma_lo[active]*amount,hi=r->gamma_hi[active]*amount;
        double eh=exp(-lo),el=exp(-hi),de=max_first(lo,hi),dde=max_second(lo,hi);
        double distance=fmax(fabs(r->hb_lo-sign),fabs(r->hb_hi-sign));
        double old_first[2]={r->hb_first[0],r->hb_first[1]};
        const int rows[3]={0,0,1},cols[3]={0,1,1};
        r->throughput_Ah[active]+=amount;
        if(!isfinite(r->throughput_Ah[active]))return SCM_REMAINDER_ERR_NONFINITE;
        for(j=0;j<3;j++) {
            int a=rows[j],b=cols[j];
            r->hb_second[j]=eh*r->hb_second[j]+(a==active?de*old_first[b]:0)+
                (b==active?de*old_first[a]:0)+(a==active && b==active?dde*distance:0);
        }
        for(j=0;j<2;j++)r->hb_first[j]=eh*old_first[j]+(j==active?de*distance:0);
        range_step(&r->hb_lo,&r->hb_hi,sign,el,eh);
        if(!isfinite(r->hb_lo) || !isfinite(r->hb_hi))return SCM_REMAINDER_ERR_NONFINITE;
    }
    for(i=0;i<2;i++) {
        qlo[i]=r->gamma_lo[i]*r->throughput_Ah[i];qhi[i]=r->gamma_hi[i]*r->throughput_Ah[i];
    }
    ha_first[0]=max_first(qlo[0],qhi[0])*exp(-qlo[1]);
    ha_first[1]=max_first(qlo[1],qhi[1])*exp(-qlo[0]);
    ha_second[0]=max_second(qlo[0],qhi[0])*exp(-qlo[1]);
    ha_second[1]=max_first(qlo[0],qhi[0])*max_first(qlo[1],qhi[1]);
    ha_second[2]=max_second(qlo[1],qhi[1])*exp(-qlo[0]);
    for(i=0;i<3;i++) {
        status=add_bound(r,k++,r->H_abs_max*r->hb_second[i]+r->u_abs_max*ha_second[i]);if(status)return status;
    }
    for(i=0;i<2;i++) {
        status=add_bound(r,k++,r->hb_first[i]);if(status)return status;
        status=add_bound(r,k++,ha_first[i]);if(status)return status;
    }
    wabs=fabs(r->charge_Ah)/r->Q_lo;
    status=add_bound(r,k++,4.);if(status)return status;
    status=add_bound(r,k++,4.*wabs);if(status)return status;
    status=add_bound(r,k++,4.*wabs*wabs+1.79*wabs);if(status)return status;
    if(k!=r->pair_count)return SCM_REMAINDER_ERR_ARGUMENT;
    r->next_index++;return SCM_REMAINDER_OK;
}

static int same_config(const scm_evidence_config *a,const scm_evidence_config *b)
{
    int i,nt=scm_model_ntheta(a->modes),na=scm_model_nalpha(a->modes);
    if(!nt || a->modes!=b->modes || a->ocv.n || b->ocv.n || a->sigma!=b->sigma ||
       a->residual_rms_limit_sigma!=b->residual_rms_limit_sigma ||
       a->max_event_samples!=b->max_event_samples ||
       memcmp(a->source_id,b->source_id,SCM_EVIDENCE_SOURCE_BYTES))return 0;
    for(i=0;i<nt;i++)if(a->theta[i]!=b->theta[i])return 0;
    for(i=0;i<na;i++)if(a->alpha[i]!=b->alpha[i])return 0;
    for(i=0;i<nt+na;i++)if(a->scale[i]!=b->scale[i] || a->radius[i]!=b->radius[i])return 0;
    return 1;
}

static int matched(const scm_compact_remainder *r,const scm_compact_evidence *e)
{
    return r->config && e->config && r->paired_ancestry &&
        (r->bound_evidence==e || (!r->bound_evidence && !r->next_index && !e->next_index)) &&
        same_config(r->config,e->config) && e->first_index==0 &&
        r->next_index==e->next_index && e->history.dim==r->dim && e->event.dim==r->dim &&
        e->history.samples<=e->next_index && e->event.samples==e->next_index-e->history.samples &&
        r->elapsed==e->model.elapsed && r->charge_Ah==e->model.charge_Ah &&
        r->charge_min_Ah==e->charge_min_Ah && r->charge_max_Ah==e->charge_max_Ah;
}

int scm_compact_remainder_push(scm_compact_remainder *r,const unsigned char id[SCM_EVIDENCE_SOURCE_BYTES],
                       uint64_t index,const scm_sample *sample,scm_compact_remainder_workspace *w)
{
    int status;
    if(!r || !id || !sample || !w)return SCM_REMAINDER_ERR_ARGUMENT;
    if(!r->config || !scm_model_ntheta(r->config->modes))return SCM_REMAINDER_ERR_ARGUMENT;
    w->staged=*r;status=advance(&w->staged,id,index,sample);
    if(status)return status;
    w->staged.paired_ancestry=0;
    *r=w->staged;return SCM_REMAINDER_OK;
}

int scm_compact_remainder_evidence_push(scm_compact_evidence *e,scm_compact_remainder *r,
                               const unsigned char id[SCM_EVIDENCE_SOURCE_BYTES],
                               uint64_t index,const scm_sample *sample,
                               scm_compact_evidence_workspace *ew,scm_compact_remainder_workspace *rw)
{
    int status;
    if(!e || !r || !id || !sample || !ew || !rw)return SCM_REMAINDER_ERR_ARGUMENT;
    if(!matched(r,e))return SCM_REMAINDER_ERR_MISMATCH;
    rw->staged=*r;status=advance(&rw->staged,id,index,sample);
    if(status)return status;
    status=scm_compact_evidence_push(e,id,index,sample,ew);if(status)return status;
    rw->staged.bound_evidence=e;
    *r=rw->staged;return SCM_REMAINDER_OK;
}

int scm_compact_remainder_query(const scm_compact_remainder *r,const scm_compact_evidence *e,
                        const double *delta,double budget,scm_remainder_result *out)
{
    double error=0,cost;int k,status;
    if(!out)return SCM_REMAINDER_ERR_ARGUMENT;
    memset(out,0,sizeof(*out));out->status=SCM_REMAINDER_UNAVAILABLE;out->budget=budget;
    if(!r || !e || !delta || !isfinite(budget) || budget<0)return SCM_REMAINDER_ERR_ARGUMENT;
    if(!matched(r,e))return SCM_REMAINDER_ERR_MISMATCH;
    for(k=0;k<r->dim;k++) {
        if(!isfinite(delta[k]))return SCM_REMAINDER_ERR_NONFINITE;
        /* The analytic rectangle uses exact configured radii, so do not use
         * the evidence module's small numerical tolerance to enlarge it.
         */
        if(fabs(delta[k])>r->config->radius[k]) {
            out->domain_code=SCM_EVIDENCE_ERR_RADIUS;out->status=SCM_REMAINDER_OUTSIDE_DOMAIN;
            return SCM_REMAINDER_OK;
        }
    }
    status=scm_compact_evidence_check_candidate(e,delta);out->domain_code=status;
    if(status) {out->status=SCM_REMAINDER_OUTSIDE_DOMAIN;return SCM_REMAINDER_OK;}
    for(k=0;k<r->pair_count;k++) {
        int i=r->pair_row[k],j=r->pair_column[k];
        error+=(i==j?.5:1.)*r->coefficient[k]*fabs(delta[i]*delta[j]);
    }
    cost=scm_evidence_factor_cost(&e->history,delta)+scm_evidence_factor_cost(&e->event,delta);
    if(!isfinite(error) || !isfinite(cost) || error<0 || cost<0)return SCM_REMAINDER_ERR_NONFINITE;
    out->affine_nll=cost;out->whitened_prediction_error_bound=error;
    out->nll_error_bound=sqrt(2*cost)*error+.5*error*error;
    if(!isfinite(out->nll_error_bound))return SCM_REMAINDER_ERR_NONFINITE;
    out->status=out->nll_error_bound<=budget?SCM_REMAINDER_WITHIN_ANALYTIC_BUDGET:SCM_REMAINDER_EXCEEDS_BUDGET;
    return SCM_REMAINDER_OK;
}
