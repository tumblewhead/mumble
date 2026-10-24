#include "scm_evidence.h"
#include <math.h>
#include <string.h>

size_t scm_evidence_packed_index(size_t row,size_t column)
{
    if(row>column || column>=SCM_EVIDENCE_AUG)return SIZE_MAX;
    return row*(2*SCM_EVIDENCE_AUG-row+1)/2+column-row;
}

static int bounded(double value,double lo,double hi)
{
    return isfinite(value) && value>=lo-1e-12 && value<=hi+1e-12;
}

static int parameters_valid(int n,const double *t,const double *a)
{
    int i;
    if(!scm_model_ntheta(n))return 0;
    for(i=0;i<n;i++) {
        const double lower[3]={.015,.15,1.5},upper[3]={.15,1.5,30};
        double lo=n==3?lower[i]:(i?.8:.015);
        double hi=n==3?upper[i]:(i?180.:30.);
        if(!bounded(t[i],log(lo),log(hi)))return 0;
    }
    if(!bounded(t[n],log(5.),log(1200.)) ||
       !bounded(t[n+1],log(5.),log(1200.)) ||
       !bounded(t[n+2],.2,.95) ||
       !bounded(t[n+3],log(.03),log(.10)))return 0;
    for(i=0;i<=n;i++)if(!bounded(a[i],0,1))return 0;
    if(!bounded(a[n+1],0,.1))return 0;
    for(i=0;i<n;i++)if(!bounded(a[n+2+i],-.08,.08))return 0;
    if(!bounded(a[2+2*n],-.1,.1) ||
       fabs(a[2+2*n])>a[n+1]+1e-12)return 0;
    return 1;
}

/* A scratch row is destroyed. Count metadata is managed by callers so that
 * merging compressed rows does not count them as additional observations.
 */
static int qr_row(scm_evidence_factor *f,double *row)
{
    int i,j,n=f->dim+1;
    for(i=0;i<n;i++)if(!isfinite(row[i]))return SCM_EVIDENCE_ERR_NONFINITE;
    for(i=0;i<n;i++) {
        size_t ii=scm_evidence_packed_index((size_t)i,(size_t)i);
        double a=f->upper[ii],b=row[i],r,c,s;
        if(b==0)continue;
        r=hypot(a,b);
        if(!isfinite(r) || r==0)return SCM_EVIDENCE_ERR_NONFINITE;
        c=a/r;s=b/r;f->upper[ii]=r;row[i]=0;
        for(j=i+1;j<n;j++) {
            size_t ij=scm_evidence_packed_index((size_t)i,(size_t)j);
            double old=f->upper[ij],tail=row[j];
            f->upper[ij]=c*old+s*tail;
            row[j]=-s*old+c*tail;
            if(!isfinite(f->upper[ij]) || !isfinite(row[j]))
                return SCM_EVIDENCE_ERR_NONFINITE;
        }
    }
    return SCM_EVIDENCE_OK;
}

static int merge(scm_evidence_factor *dst,const scm_evidence_factor *src,
                 double *row)
{
    int i,j,status;
    if(dst->dim!=src->dim)return SCM_EVIDENCE_ERR_ARGUMENT;
    if(UINT64_MAX-dst->samples<src->samples)return SCM_EVIDENCE_ERR_OVERFLOW;
    for(i=0;i<=src->dim;i++) {
        for(j=0;j<=src->dim;j++)
            row[j]=j<i?0:src->upper[scm_evidence_packed_index((size_t)i,(size_t)j)];
        status=qr_row(dst,row);if(status)return status;
    }
    dst->samples+=src->samples;
    return SCM_EVIDENCE_OK;
}

static int seal_staged(scm_evidence *e,double *row)
{
    int status,dim=e->history.dim;
    double rms;
    if(!e->event.samples)return SCM_EVIDENCE_OK;
    if(e->events_completed==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
    rms=scm_evidence_factor_rms_sigma(&e->event);
    if(!isfinite(rms))return SCM_EVIDENCE_ERR_NONFINITE;
    if(rms>e->config.residual_rms_limit_sigma) {
        if(e->residual_flagged_events==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
        e->residual_flagged_events++;
    }
    e->last_event_samples=e->event.samples;e->last_event_anchor_rms_sigma=rms;
    e->max_event_anchor_rms_sigma=fmax(e->max_event_anchor_rms_sigma,rms);
    status=merge(&e->history,&e->event,row);if(status)return status;
    memset(&e->event,0,sizeof(e->event));e->event.dim=dim;
    e->events_completed++;e->active_begin=e->next_index;
    return SCM_EVIDENCE_OK;
}

int scm_evidence_init(scm_evidence *e,const scm_evidence_config *c)
{
    scm_evidence_config config;
    scm_model_state model;
    double u,slope;
    int i,dim,status;
    if(!e || !c || !scm_model_ntheta(c->modes) || !c->max_event_samples)
        return SCM_EVIDENCE_ERR_ARGUMENT;
    if(!isfinite(c->sigma) || !(c->sigma>0))return SCM_EVIDENCE_ERR_ARGUMENT;
    if(!isfinite(c->residual_rms_limit_sigma) || !(c->residual_rms_limit_sigma>0))
        return SCM_EVIDENCE_ERR_ARGUMENT;
    dim=scm_model_ntheta(c->modes)+scm_model_nalpha(c->modes);
    for(i=0;i<dim;i++)if(!isfinite(c->scale[i]) || !(c->scale[i]>0) ||
                           !isfinite(c->radius[i]) || c->radius[i]<0)
        return SCM_EVIDENCE_ERR_ARGUMENT;
    if(!parameters_valid(c->modes,c->theta,c->alpha))return SCM_EVIDENCE_ERR_DOMAIN;
    if(scm_ocv_validate(&c->ocv))return SCM_EVIDENCE_ERR_DOMAIN;
    if(scm_ocv_eval(&c->ocv,c->theta[c->modes+2],&u,&slope))
        return SCM_EVIDENCE_ERR_DOMAIN;
    status=scm_model_init(&model,c->modes,c->theta);
    if(status)return SCM_EVIDENCE_ERR_DOMAIN;
    config=*c;memset(e,0,sizeof(*e));e->config=config;e->model=model;
    e->history.dim=e->event.dim=dim;
    return SCM_EVIDENCE_OK;
}

int scm_evidence_push(scm_evidence *e,
                     const unsigned char id[SCM_EVIDENCE_SOURCE_BYTES],
                     uint64_t index,const scm_sample *sample,
                     scm_evidence_workspace *w)
{
    scm_evidence *s;
    double mu;
    int i,nt,na,status;
    if(!e || !id || !sample || !w)return SCM_EVIDENCE_ERR_ARGUMENT;
    if(memcmp(id,e->config.source_id,SCM_EVIDENCE_SOURCE_BYTES))return SCM_EVIDENCE_ERR_SOURCE;
    if(index!=e->next_index)return SCM_EVIDENCE_ERR_ORDER;
    if(index==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
    if(!isfinite(sample->dt) || !isfinite(sample->current) || !isfinite(sample->voltage))
        return SCM_EVIDENCE_ERR_NONFINITE;
    if(sample->dt<0)return SCM_EVIDENCE_ERR_ARGUMENT;
    nt=scm_model_ntheta(e->config.modes);na=scm_model_nalpha(e->config.modes);
    if(!nt || e->history.dim!=nt+na || e->event.dim!=nt+na)
        return SCM_EVIDENCE_ERR_ARGUMENT;
    w->staged=*e;s=&w->staged;
    if(s->event.samples && (s->event.samples>=s->config.max_event_samples ||
       (s->has_last && (sample->current!=s->last_current || sample->dt!=s->last_dt)))) {
        status=seal_staged(s,w->row);if(status)return status;
    }
    status=scm_model_step(&s->model,&s->config.ocv,sample->dt,sample->current,&w->model_row);
    if(status)return status==SCM_ERR_NONFINITE?SCM_EVIDENCE_ERR_NONFINITE:SCM_EVIDENCE_ERR_DOMAIN;
    status=scm_model_predict(&w->model_row,s->config.modes,s->config.alpha,&mu,w->jac_theta);
    if(status)return SCM_EVIDENCE_ERR_NONFINITE;
    for(i=0;i<nt;i++)w->row[i]=w->jac_theta[i]*s->config.scale[i]/s->config.sigma;
    for(i=0;i<na;i++)w->row[nt+i]=w->model_row.X[i]*s->config.scale[nt+i]/s->config.sigma;
    w->row[nt+na]=(sample->voltage-mu)/s->config.sigma;
    status=qr_row(&s->event,w->row);if(status)return status;
    if(s->event.samples==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
    s->event.samples++;s->next_index++;
    s->last_current=sample->current;s->last_dt=sample->dt;s->has_last=1;
    if(sample->dt>0 && sample->current>0)s->excitation|=1u;
    if(sample->dt>0 && sample->current<0)s->excitation|=2u;
    s->charge_min_Ah=fmin(s->charge_min_Ah,s->model.charge_Ah);
    s->charge_max_Ah=fmax(s->charge_max_Ah,s->model.charge_Ah);
    *e=*s;return SCM_EVIDENCE_OK;
}

int scm_evidence_seal(scm_evidence *e,scm_evidence_workspace *w)
{
    int status;
    if(!e || !w)return SCM_EVIDENCE_ERR_ARGUMENT;
    w->staged=*e;status=seal_staged(&w->staged,w->row);
    if(status)return status;
    *e=w->staged;return SCM_EVIDENCE_OK;
}

int scm_evidence_snapshot(const scm_evidence *e,scm_evidence_factor *out,
                         scm_evidence_workspace *w)
{
    int status;
    if(!e || !out || !w)return SCM_EVIDENCE_ERR_ARGUMENT;
    w->staged=*e;
    status=merge(&w->staged.history,&w->staged.event,w->row);
    if(status)return status;
    *out=w->staged.history;return SCM_EVIDENCE_OK;
}

double scm_evidence_factor_cost(const scm_evidence_factor *f,const double *delta)
{
    int i,j;double norm=0;
    if(!f || !delta || f->dim<1 || f->dim>SCM_EVIDENCE_DIM)return NAN;
    for(i=0;i<f->dim;i++)if(!isfinite(delta[i]))return NAN;
    for(i=0;i<=f->dim;i++) {
        double r=-f->upper[scm_evidence_packed_index((size_t)i,(size_t)f->dim)];
        for(j=i;j<f->dim;j++)r+=f->upper[scm_evidence_packed_index((size_t)i,(size_t)j)]*delta[j];
        norm=hypot(norm,r);
    }
    return .5*norm*norm;
}

double scm_evidence_factor_rms_sigma(const scm_evidence_factor *f)
{
    int i;double norm=0;
    if(!f || f->dim<1 || f->dim>SCM_EVIDENCE_DIM)return NAN;
    if(!f->samples)return 0;
    for(i=0;i<=f->dim;i++)norm=hypot(norm,f->upper[scm_evidence_packed_index((size_t)i,(size_t)f->dim)]);
    return norm/sqrt((double)f->samples);
}

int scm_evidence_factor_normal(const scm_evidence_factor *f,double *normal,
                              double *gradient,double *cost)
{
    int i,j,k,d;double norm=0;
    if(!f || !normal || !gradient || !cost || f->dim<1 || f->dim>SCM_EVIDENCE_DIM)
        return SCM_EVIDENCE_ERR_ARGUMENT;
    d=f->dim;
    for(i=0;i<d;i++) {
        gradient[i]=0;
        for(k=0;k<=i;k++)gradient[i]-=f->upper[scm_evidence_packed_index((size_t)k,(size_t)i)]*
                                           f->upper[scm_evidence_packed_index((size_t)k,(size_t)d)];
        if(!isfinite(gradient[i]))return SCM_EVIDENCE_ERR_NONFINITE;
        for(j=0;j<=i;j++) {
            double h=0;
            for(k=0;k<=j;k++)h+=f->upper[scm_evidence_packed_index((size_t)k,(size_t)i)]*
                                   f->upper[scm_evidence_packed_index((size_t)k,(size_t)j)];
            if(!isfinite(h))return SCM_EVIDENCE_ERR_NONFINITE;
            normal[i*d+j]=normal[j*d+i]=h;
        }
    }
    for(i=0;i<=d;i++)norm=hypot(norm,f->upper[scm_evidence_packed_index((size_t)i,(size_t)d)]);
    *cost=.5*norm*norm;
    return isfinite(*cost)?SCM_EVIDENCE_OK:SCM_EVIDENCE_ERR_NONFINITE;
}

int scm_evidence_check_candidate(const scm_evidence *e,const double *delta)
{
    double theta[SCM_MAX_THETA],alpha[SCM_MAX_ALPHA],zlo,zhi,q,u,slope;
    int i,n,nt,na;
    if(!e || !delta)return SCM_EVIDENCE_ERR_ARGUMENT;
    n=e->config.modes;nt=scm_model_ntheta(n);na=scm_model_nalpha(n);
    if(!nt)return SCM_EVIDENCE_ERR_ARGUMENT;
    for(i=0;i<nt+na;i++) {
        if(!isfinite(delta[i]))return SCM_EVIDENCE_ERR_NONFINITE;
        if(fabs(delta[i])>e->config.radius[i]+1e-12)return SCM_EVIDENCE_ERR_RADIUS;
    }
    for(i=0;i<nt;i++)theta[i]=e->config.theta[i]+e->config.scale[i]*delta[i];
    for(i=0;i<na;i++)alpha[i]=e->config.alpha[i]+e->config.scale[nt+i]*delta[nt+i];
    if(!parameters_valid(n,theta,alpha))return SCM_EVIDENCE_ERR_DOMAIN;
    q=exp(theta[n+3]);zlo=theta[n+2]-e->charge_max_Ah/q;zhi=theta[n+2]-e->charge_min_Ah/q;
    if(scm_ocv_eval(&e->config.ocv,zlo,&u,&slope) ||
       scm_ocv_eval(&e->config.ocv,zhi,&u,&slope))return SCM_EVIDENCE_ERR_DOMAIN;
    return SCM_EVIDENCE_OK;
}
