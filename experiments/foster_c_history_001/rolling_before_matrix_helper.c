#include "baseline.h"
#ifndef FB_OPT_STAGE
#define FB_OPT_STAGE 3
#endif
#if FB_OPT_STAGE < 1 || FB_OPT_STAGE > 3
#error "FB_OPT_STAGE must be 1, 2 or 3"
#endif
#include <math.h>
#include <string.h>
#ifdef FB_PROFILE
#include <time.h>
#endif

double fb_now(void) {
#ifdef FB_PROFILE
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;
#else
    return 0;
#endif
}
static int evaluate(FBContext *s,const double *x,int n,FBPhysical *p) {
    double t=fb_now();s->profile.model_calls++;
#if FB_MODEL_STAGE >= 2
    int r=foster_predict_cached(x,s->obs,n,s->config.cal,s->phase.fit.thermal,p->v,p->J,p->end,p->F);
#else
    int r=foster_predict(x,s->obs,n,s->config.cal,p->v,p->J,p->end,p->F);
#endif
    s->profile.model_s+=fb_now()-t;if(!r)s->profile.model_success++;
    return r?FB_MODEL:FB_OK;
}
static int latent(FBContext *s,const double *w,FBPhysical *p,double *r,double *cost) {
    double x[16];int i,j;
    for(i=0;i<16;i++){x[i]=s->message.mean[i];for(j=0;j<16;j++)x[i]+=s->message.root[i*16+j]*w[j];}
    if(evaluate(s,x,s->pending,p))return FB_MODEL;
    s->evaluations++;s->profile.fit_evaluations++;*cost=0;
    for(i=0;i<16;i++)*cost+=w[i]*w[i];
    for(i=0;i<s->pending;i++){r[i]=(p->v[i]-s->obs[i*5+3])/s->obs[i*5+4];*cost+=r[i]*r[i];}
    *cost*=.5;return isfinite(*cost)?FB_OK:FB_NUMERIC;
}
/* The fitter precision is I+B^T B. Preserve every cross term; no jitter.
 * Exported for independent residual qualification of the changed solver. */
int fb_spd_solve(double a[256],double b[16]) {
    if(fb_cholesky(a))return FB_NUMERIC;
    for(int i=0;i<16;i++) {
        for(int j=0;j<i;j++)b[i]-=a[i*16+j]*b[j];
        b[i]/=a[i*16+i];
    }
    for(int i=15;i>=0;i--) {
        for(int j=i+1;j<16;j++)b[i]-=a[j*16+i]*b[j];
        b[i]/=a[i*16+i];if(!isfinite(b[i]))return FB_NUMERIC;
    }
    return FB_OK;
}
static void precision(const double *B,int n,double P[256]) {
    for(int i=0;i<16;i++) {
#if FB_OPT_STAGE >= 3
        /* Cholesky reads the lower triangle and clears the upper triangle. */
        int columns=i+1;
#else
        int columns=16;
#endif
        for(int j=0;j<columns;j++) {
            double z=i==j?1.:0.;
            for(int k=0;k<n;k++)z+=B[k*16+i]*B[k*16+j];
            P[i*16+j]=z;
        }
    }
}
static int fit(FBContext *s) {
    /* Matrix scratch is dead before the first physical line-search trial. */
    double *B=s->phase.fit.transient.matrices.B,*P=s->phase.fit.transient.matrices.P;
    double g[16],step[16],trial[16],res[16],cost;int i,j,k,r;
    memset(s->w,0,sizeof(s->w));s->evaluations=0;s->rounds=0;s->stop=FB_ROUND_LIMIT;
    /* fb_flush just evaluated this exact incoming mean and window.
     * Reuse all outputs, including derivatives; counts now describe actual calls. */
#if FB_MODEL_STAGE < 2
    s->phase.fit.current=s->before;
#endif
    s->cost=0;
    for(i=0;i<s->pending;i++) {
        s->residual[i]=(s->phase.fit.current.v[i]-s->obs[i*5+3])/s->obs[i*5+4];
        s->cost+=s->residual[i]*s->residual[i];
    }
    s->cost*=.5;if(!isfinite(s->cost))return FB_NUMERIC;
    for(int iteration=0;iteration<s->config.rounds;iteration++) {
        double maxg=0,maxstep=0;s->rounds=iteration+1;s->profile.rounds++;
        for(i=0;i<s->pending;i++)for(j=0;j<16;j++) {
            double z=0;for(k=0;k<16;k++)z+=s->phase.fit.current.J[i*16+k]*s->message.root[k*16+j];
            B[i*16+j]=z/s->obs[5*i+4];
        }
        for(i=0;i<16;i++) {
            g[i]=s->w[i];for(k=0;k<s->pending;k++)g[i]+=B[k*16+i]*s->residual[k];
            if(!isfinite(g[i]))return FB_NUMERIC;
            maxg=fmax(maxg,fabs(g[i]));step[i]=-g[i];

        }
#if FB_OPT_STAGE == 1
        precision(B,s->pending,P);
#endif
        if(maxg<=s->config.gradient_tol){s->stop=FB_GRADIENT;break;}
#if FB_OPT_STAGE >= 2
        precision(B,s->pending,P);
#endif
#if FB_OPT_STAGE >= 3
        if(fb_spd_solve(P,step))return FB_NUMERIC;
#else
        if(fb_solve(P,step))return FB_NUMERIC;
#endif
        for(i=0;i<16;i++)maxstep=fmax(maxstep,fabs(step[i]));
        if(maxstep<=s->config.step_tol){s->stop=FB_STEP;break;}
        int accepted=0;
        for(int power=0;power<s->config.fractions;power++) {
            s->profile.trials++;
            for(i=0;i<16;i++)trial[i]=s->w[i]+ldexp(step[i],-power);
            r=latent(s,trial,&s->phase.fit.transient.trial,res,&cost);
            if(r==FB_MODEL)continue;
            if(r)return r;
            if(cost<s->cost) {
                memcpy(s->w,trial,sizeof(trial));memcpy(s->residual,res,(size_t)s->pending*sizeof(double));
                s->phase.fit.current=s->phase.fit.transient.trial;s->cost=cost;accepted=1;break;
            }
        }
        if(!accepted){s->stop=FB_NO_DESCENT;break;}
    }
    for(i=0;i<16;i++){s->anchor[i]=s->message.mean[i];for(j=0;j<16;j++)s->anchor[i]+=s->message.root[i*16+j]*s->w[j];}
    return FB_OK;
}
int fb_init(FBContext *s,const FBConfig *c,const FBMessage *m,uint64_t source_id) {
    if(!s||!c||!m||c->rounds<1||c->rounds>100||c->fractions<1||c->fractions>32||
       (c->encoding!=4&&c->encoding!=8)||!isfinite(c->gradient_tol)||c->gradient_tol<0||
       !isfinite(c->step_tol)||c->step_tol<0)return FB_INPUT;
    for(int i=0;i<14;i++)if(!isfinite(c->cal[i]))return FB_INPUT;
    for(int i=0;i<16;i++)if(!isfinite(m->mean[i]))return FB_INPUT;
    for(int i=0;i<256;i++)if(!isfinite(m->root[i]))return FB_INPUT;
    if(!isfinite(m->logZ))return FB_INPUT;
    memset(s,0,sizeof(*s));s->config=*c;s->message=*m;s->source_id=source_id;
    int r=evaluate(s,m->mean,0,&s->phase.fit.current);memset(&s->profile,0,sizeof(s->profile));return r;
}
int fb_offer(FBContext *s,uint64_t index,const double obs[5]) {
    if(index!=s->next_index)return FB_ORDER;
    if(s->pending>=16)return FB_FULL;
    for(int i=0;i<5;i++)if(!isfinite(obs[i]))return FB_INPUT;
    if(obs[0]<0||obs[0]>1||obs[4]<=0)return FB_INPUT;
    double ticks=round(obs[0]*1050);
    if(fabs(ticks/1050-obs[0])>1e-12||s->next_index==UINT64_MAX||s->ticks>UINT64_MAX-(uint64_t)ticks)return FB_INPUT;
    memcpy(s->obs+5*s->pending,obs,5*sizeof(double));s->pending++;s->next_index++;s->ticks+=(uint64_t)ticks;
    return s->pending==16?fb_flush(s):FB_OK;
}
int fb_flush(FBContext *s) {
    int r;double t,ss=0;
    if(!s->pending)return FB_OK;
    t=fb_now();
#if FB_MODEL_STAGE >= 2
    FBPhysical *initial=&s->phase.fit.current;
    r=foster_thermal(s->obs,s->pending,s->config.cal,s->phase.fit.thermal);
    if(r){s->profile.before_s+=fb_now()-t;return FB_MODEL;}
#else
    FBPhysical *initial=&s->before;
#endif
    r=evaluate(s,s->message.mean,s->pending,initial);
    s->profile.before_s+=fb_now()-t;if(r)return r;
    for(int i=0;i<s->pending;i++){double v=(initial->v[i]-s->obs[5*i+3])/s->obs[5*i+4];ss+=v*v;}
    s->initial_rms=sqrt(ss/s->pending);
    t=fb_now();r=fit(s);s->profile.fit_s+=fb_now()-t;if(r)return r;
    ss=0;for(int i=0;i<s->pending;i++)ss+=s->residual[i]*s->residual[i];s->fitted_rms=sqrt(ss/s->pending);
    t=fb_now();r=fb_token(s->anchor,&s->phase.fit.current,s->obs,s->pending,s->config.encoding,s->token);
    s->profile.token_s+=fb_now()-t;if(r<0)return r;s->token_bytes=r;
    t=fb_now();/* Serialized token no longer refers to fit buffers; history owns phase now. */
    r=fb_history_work(&s->message,s->token,(size_t)s->token_bytes,&s->candidate,&s->phase.history);
    s->profile.history_s+=fb_now()-t;if(r)return r;
    t=fb_now();r=evaluate(s,s->candidate.mean,0,&s->phase.fit.transient.trial);s->profile.domain_s+=fb_now()-t;if(r)return r;
    /* No fallible operation after this point. Commit and acknowledge together.
     * This synchronous integration has no external prepare/commit message race. */
    s->message=s->candidate;s->retired_index=s->next_index;s->retired_ticks=s->ticks;
    s->generation++;s->pending=0;s->profile.tokens++;s->profile.stops[s->stop]++;
    return FB_RETIRED;
}
size_t fb_context_bytes(void){return sizeof(FBContext);}
size_t fb_profile_bytes(void){return sizeof(FBProfile);}
void fb_get_message(const FBContext *s,double out[273]) {
    memcpy(out,s->message.mean,16*sizeof(double));memcpy(out+16,s->message.root,256*sizeof(double));out[272]=s->message.logZ;
}
void fb_get_profile(const FBContext *s,FBProfile *out){*out=s->profile;}
static void output(const FBContext *s,double *out) {
    for(int i=0;i<16;i++){double v=0;out[i]=s->message.mean[i];for(int j=0;j<16;j++)v+=s->message.root[i*16+j]*s->message.root[i*16+j];out[16+i]=sqrt(v);}
    out[32]=s->message.logZ;out[33]=(double)s->retired_index;out[34]=s->stop;out[35]=s->evaluations;
}
int fb_replay(FBContext *s,const double *obs,size_t n,double *out,size_t capacity,size_t *written) {
    size_t need=n/16+(n%16+(size_t)s->pending+15)/16;
    *written=0;if(capacity<need)return FB_FULL;
    for(size_t i=0;i<n;i++) {
        int r=fb_offer(s,s->next_index,obs+5*i);if(r<0)return r;
        if(r==FB_RETIRED){output(s,out+36*(*written));(*written)++;}
    }
    int r=fb_flush(s);if(r<0)return r;
    if(r==FB_RETIRED){output(s,out+36*(*written));(*written)++;}
    return FB_OK;
}
