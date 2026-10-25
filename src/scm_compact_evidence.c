#include "scm_compact_evidence.h"
#include <math.h>
#include <string.h>

/* The normalized Givens arithmetic and compressed-row merge order below are
 * deliberately identical to scm_evidence.c. Keep the original as comparison
 * reference while qualifying this alternative storage/transaction layout. */
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
        double a=f->upper[ii],b=row[i],r,c,s,scale,aa,bb,h;
        if(b==0)continue;
        /* Normalize before forming the rotation. If a and b are subnormal,
         * hypot(a,b) can round to a value with very few significant bits;
         * dividing by that rounded value can make c*c+s*s materially differ
         * from 1 and corrupt ordinary-size trailing columns/residuals.
         * The rounded tiny diagonal is unavoidable, but the rotation need
         * not inherit its relative error. No information is thresholded.
         */
        scale=fmax(fabs(a),fabs(b));aa=a/scale;bb=b/scale;
        h=hypot(aa,bb);c=aa/h;s=bb/h;r=scale*h;
        if(!isfinite(r) || r==0)return SCM_EVIDENCE_ERR_NONFINITE;
        f->upper[ii]=r;row[i]=0;
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


#define COPY_METADATA(dst,src) do { \
    (dst)->first_index=(src)->first_index; \
    (dst)->next_index=(src)->next_index; \
    (dst)->active_begin=(src)->active_begin; \
    (dst)->events_completed=(src)->events_completed; \
    (dst)->excitation=(src)->excitation; \
    (dst)->has_last=(src)->has_last; \
    (dst)->last_current=(src)->last_current; \
    (dst)->last_dt=(src)->last_dt; \
    (dst)->charge_min_Ah=(src)->charge_min_Ah; \
    (dst)->charge_max_Ah=(src)->charge_max_Ah; \
    (dst)->last_event_samples=(src)->last_event_samples; \
    (dst)->residual_flagged_events=(src)->residual_flagged_events; \
    (dst)->last_event_anchor_rms_sigma=(src)->last_event_anchor_rms_sigma; \
    (dst)->max_event_anchor_rms_sigma=(src)->max_event_anchor_rms_sigma; \
} while(0)

/* Advance an already prospective model; no second whole-state stack copy.
 * The row doubles first hold the nine X values, then the whitened joint row.
 * All derivative products/additions retain the original alpha-index order,
 * including zeros: this preserves signed-zero and nonfinite behavior without
 * allocating the dense 7-by-9 dX table or a separate theta Jacobian. */
static int model_joint_row(scm_model_state *t,const scm_evidence_config *c,
                           const scm_sample *sample,double *row)
{
    int i,j,n=t->modes,nt=scm_model_ntheta(n),na=scm_model_nalpha(n),k,status;
    double dt=sample->dt,I=sample->current;
    double e,om,dlog,q,oldf,olda,oldb,sgn,dudz,ocv,z,v,der;
    if(!nt || n!=c->modes)return SCM_EVIDENCE_ERR_DOMAIN;
    t->charge_Ah+=I*dt/3600;t->elapsed+=dt;
    if(!isfinite(t->charge_Ah) || !isfinite(t->elapsed))return SCM_EVIDENCE_ERR_NONFINITE;
    z=t->z0-t->charge_Ah/t->Q;
    status=scm_ocv_eval(&c->ocv,z,&ocv,&dudz);
    if(status)return status==SCM_ERR_NONFINITE?SCM_EVIDENCE_ERR_NONFINITE:SCM_EVIDENCE_ERR_DOMAIN;
    row[nt]=-I;
    for(i=0;i<n;i++) {
        q=dt/t->tau[i];e=exp(-q);om=-expm1(-q);
        dlog=isfinite(q)?q*e:0;
        oldf=t->f[i];olda=t->a[i];
        t->f[i]=e*oldf+om*I;t->a[i]=e*olda;
        t->df[i]=e*t->df[i]+dlog*(oldf-I);
        t->da[i]=e*t->da[i]+dlog*olda;
        row[nt+1+i]=-t->f[i];row[nt+2+n+i]=-t->a[i];
    }
    if(I!=0 && dt!=0) {
        k=I>0?0:1;sgn=I>0?1:-1;
        q=t->gamma[k]*(fabs(I)/3600)*dt;
        if(isnan(q))return SCM_EVIDENCE_ERR_NONFINITE;
        e=exp(-q);om=-expm1(-q);dlog=isfinite(q)?-q*e:0;
        oldb=t->hb;olda=t->ha;t->hb=e*oldb+om*sgn;t->ha=e*olda;
        for(j=0;j<2;j++) {
            t->dhb[j]=e*t->dhb[j]+(j==k?dlog*(oldb-sgn):0);
            t->dha[j]=e*t->dha[j]+(j==k?dlog*olda:0);
        }
    }
    row[nt+1+n]=-t->hb;row[nt+2+2*n]=-t->ha;
    v=ocv;
    for(j=0;j<na;j++) {
        if(!isfinite(c->alpha[j]))return SCM_EVIDENCE_ERR_NONFINITE;
        v+=row[nt+j]*c->alpha[j];
    }
    row[nt+na]=(sample->voltage-v)/c->sigma;
    for(i=0;i<nt;i++) {
        double jac=i==n+2?dudz:i==n+3?dudz*t->charge_Ah/t->Q:0.;
        for(j=0;j<na;j++) {
            der=0.;
            if(i<n) {
                if(j==1+i)der=-t->df[i];
                else if(j==2+n+i)der=-t->da[i];
            } else if(i<n+2) {
                if(j==1+n)der=-t->dhb[i-n];
                else if(j==2+2*n)der=-t->dha[i-n];
            }
            jac+=der*c->alpha[j];
        }
        if(!isfinite(jac))return SCM_EVIDENCE_ERR_NONFINITE;
        row[i]=jac*c->scale[i]/c->sigma;
    }
    if(!isfinite(v))return SCM_EVIDENCE_ERR_NONFINITE;
    for(i=0;i<na;i++)row[nt+i]=row[nt+i]*c->scale[nt+i]/c->sigma;
    return SCM_EVIDENCE_OK;
}

/* Metadata and one history factor are prospective. The live event remains
 * available as merge input; its QR grouping and monitor are unchanged. */
static int stage_seal(const scm_compact_evidence *e,scm_compact_evidence_workspace *w)
{
    scm_compact_evidence_metadata *m=&w->metadata;
    double rms;
    int status;
    if(m->events_completed==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
    rms=scm_evidence_factor_rms_sigma(&e->event);
    if(!isfinite(rms))return SCM_EVIDENCE_ERR_NONFINITE;
    if(rms>e->config->residual_rms_limit_sigma) {
        if(m->residual_flagged_events==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
        m->residual_flagged_events++;
    }
    m->last_event_samples=e->event.samples;m->last_event_anchor_rms_sigma=rms;
    m->max_event_anchor_rms_sigma=fmax(m->max_event_anchor_rms_sigma,rms);
    w->trial=e->history;
    status=merge(&w->trial,&e->event,w->row);if(status)return status;
    m->events_completed++;m->active_begin=m->next_index;
    return SCM_EVIDENCE_OK;
}

/* Inserting one row into an all-zero factor has just one nonzero pivot.
 * Use exactly qr_row's normalized rotation, retaining all-zero, residual-only
 * and subnormal cases. Store the resulting nonzero factor row back in scratch.
 * Nothing here modifies the live bank. After success, materialization below
 * consists only of assignments and cannot introduce a late transactional error.
 */
static int prepare_single_row(double *row,int dim,int *pivot)
{
    int i,j,n=dim+1;
    double a=0,b,r,c,s,scale,aa,bb,h;
    for(i=0;i<n;i++)if(!isfinite(row[i]))return SCM_EVIDENCE_ERR_NONFINITE;
    for(i=0;i<n;i++)if(row[i]!=0)break;
    *pivot=i;
    if(i==n)return SCM_EVIDENCE_OK;
    b=row[i];scale=fmax(fabs(a),fabs(b));aa=a/scale;bb=b/scale;
    h=hypot(aa,bb);c=aa/h;s=bb/h;r=scale*h;
    if(!isfinite(r) || r==0)return SCM_EVIDENCE_ERR_NONFINITE;
    row[i]=r;
    for(j=i+1;j<n;j++) {
        double old=0,tail=row[j],remainder;
        row[j]=c*old+s*tail;
        remainder=-s*old+c*tail;
        if(!isfinite(row[j]) || !isfinite(remainder))return SCM_EVIDENCE_ERR_NONFINITE;
    }
    return SCM_EVIDENCE_OK;
}

static void materialize_single_row(scm_evidence_factor *f,const double *row,int dim,int pivot)
{
    int j;
    memset(f,0,sizeof(*f));f->dim=dim;f->samples=1;
    for(j=pivot;j<=dim;j++)
        f->upper[scm_evidence_packed_index((size_t)pivot,(size_t)j)]=row[j];
}

int scm_compact_evidence_init(scm_compact_evidence *e,const scm_evidence_config *c)
{
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
    memset(e,0,sizeof(*e));e->config=c;e->model=model;
    e->history.dim=e->event.dim=dim;
    return SCM_EVIDENCE_OK;
}

int scm_compact_evidence_push(scm_compact_evidence *e,
    const unsigned char id[SCM_EVIDENCE_SOURCE_BYTES],uint64_t index,
    const scm_sample *sample,scm_compact_evidence_workspace *w)
{
    scm_compact_evidence_metadata *m;
    int nt,na,status,sealing,pivot=0;
    if(!e || !e->config || !id || !sample || !w)return SCM_EVIDENCE_ERR_ARGUMENT;
    if(memcmp(id,e->config->source_id,SCM_EVIDENCE_SOURCE_BYTES))return SCM_EVIDENCE_ERR_SOURCE;
    if(index!=e->next_index)return SCM_EVIDENCE_ERR_ORDER;
    if(index==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
    if(!isfinite(sample->dt) || !isfinite(sample->current) || !isfinite(sample->voltage))
        return SCM_EVIDENCE_ERR_NONFINITE;
    if(sample->dt<0)return SCM_EVIDENCE_ERR_ARGUMENT;
    nt=scm_model_ntheta(e->config->modes);na=scm_model_nalpha(e->config->modes);
    if(!nt || e->history.dim!=nt+na || e->event.dim!=nt+na)
        return SCM_EVIDENCE_ERR_ARGUMENT;
    m=&w->metadata;COPY_METADATA(m,e);w->model=e->model;
    sealing=e->event.samples && (e->event.samples>=e->config->max_event_samples ||
        (e->has_last && (sample->current!=e->last_current || sample->dt!=e->last_dt)));
    if(sealing) {
        /* Merge first: original failure precedence, and the same row scratch
         * can then be reused for the next observation. */
        status=stage_seal(e,w);if(status)return status;
    }
    status=model_joint_row(&w->model,e->config,sample,w->row);if(status)return status;
    if(sealing) {
        status=prepare_single_row(w->row,nt+na,&pivot);if(status)return status;
    } else {
        w->trial=e->event;
        status=qr_row(&w->trial,w->row);if(status)return status;
        if(w->trial.samples==UINT64_MAX)return SCM_EVIDENCE_ERR_OVERFLOW;
        w->trial.samples++;
    }
    m->next_index++;m->last_current=sample->current;m->last_dt=sample->dt;m->has_last=1;
    if(sample->dt>0 && sample->current>0)m->excitation|=1u;
    if(sample->dt>0 && sample->current<0)m->excitation|=2u;
    m->charge_min_Ah=fmin(m->charge_min_Ah,w->model.charge_Ah);
    m->charge_max_Ah=fmax(m->charge_max_Ah,w->model.charge_Ah);
    /* Every fallible operation precedes these writes to the live bank. */
    if(sealing) {
        e->history=w->trial;
        materialize_single_row(&e->event,w->row,nt+na,pivot);
    } else e->event=w->trial;
    e->model=w->model;COPY_METADATA(e,m);
    return SCM_EVIDENCE_OK;
}

int scm_compact_evidence_seal(scm_compact_evidence *e,scm_compact_evidence_workspace *w)
{
    int status;
    if(!e || !e->config || !w)return SCM_EVIDENCE_ERR_ARGUMENT;
    if(!e->event.samples)return SCM_EVIDENCE_OK;
    COPY_METADATA(&w->metadata,e);
    status=stage_seal(e,w);if(status)return status;
    e->history=w->trial;memset(&e->event,0,sizeof(e->event));e->event.dim=e->history.dim;
    COPY_METADATA(e,&w->metadata);
    return SCM_EVIDENCE_OK;
}

int scm_compact_evidence_snapshot(const scm_compact_evidence *e,scm_evidence_factor *out,
    scm_compact_evidence_workspace *w)
{
    int status;
    if(!e || !out || !w)return SCM_EVIDENCE_ERR_ARGUMENT;
    w->trial=e->history;status=merge(&w->trial,&e->event,w->row);
    if(status)return status;
    *out=w->trial;return SCM_EVIDENCE_OK;
}

int scm_compact_evidence_snapshot_into(const scm_compact_evidence *e,
    scm_evidence_factor *out,double row[SCM_EVIDENCE_AUG])
{
    if(!e || !out || !row)return SCM_EVIDENCE_ERR_ARGUMENT;
    *out=e->history;return merge(out,&e->event,row);
}

int scm_compact_evidence_check_candidate(const scm_compact_evidence *e,const double *delta)
{
    double theta[SCM_MAX_THETA],alpha[SCM_MAX_ALPHA],zlo,zhi,q,u,slope;
    int i,n,nt,na;
    if(!e || !e->config || !delta)return SCM_EVIDENCE_ERR_ARGUMENT;
    n=e->config->modes;nt=scm_model_ntheta(n);na=scm_model_nalpha(n);
    if(!nt)return SCM_EVIDENCE_ERR_ARGUMENT;
    for(i=0;i<nt+na;i++) {
        if(!isfinite(delta[i]))return SCM_EVIDENCE_ERR_NONFINITE;
        if(fabs(delta[i])>e->config->radius[i]+1e-12)return SCM_EVIDENCE_ERR_RADIUS;
    }
    for(i=0;i<nt;i++)theta[i]=e->config->theta[i]+e->config->scale[i]*delta[i];
    for(i=0;i<na;i++)alpha[i]=e->config->alpha[i]+e->config->scale[nt+i]*delta[nt+i];
    if(!parameters_valid(n,theta,alpha))return SCM_EVIDENCE_ERR_DOMAIN;
    q=exp(theta[n+3]);zlo=theta[n+2]-e->charge_max_Ah/q;zhi=theta[n+2]-e->charge_min_Ah/q;
    if(scm_ocv_eval(&e->config->ocv,zlo,&u,&slope) ||
       scm_ocv_eval(&e->config->ocv,zhi,&u,&slope))return SCM_EVIDENCE_ERR_DOMAIN;
    return SCM_EVIDENCE_OK;
}

#undef COPY_METADATA
