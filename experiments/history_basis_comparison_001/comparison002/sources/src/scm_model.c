#include "scm_model.h"
#include <math.h>
#include <string.h>

int scm_model_ntheta(int n) { return n>=1 && n<=SCM_MAX_MODES ? n+4 : 0; }
int scm_model_nalpha(int n) { return n>=1 && n<=SCM_MAX_MODES ? 2*n+3 : 0; }

int scm_ocv_validate(const scm_ocv *c)
{
    size_t i;
    if(!c || c->n==0)return SCM_OK;
    if(c->n<2 || !c->z || !c->u)return SCM_ERR_ARGUMENT;
    for(i=0;i<c->n;i++) {
        if(!isfinite(c->z[i]) || !isfinite(c->u[i]))return SCM_ERR_NONFINITE;
        if(c->z[i]<0 || c->z[i]>1)return SCM_ERR_DOMAIN;
        if(i && (!(c->z[i]>c->z[i-1]) || c->u[i]<c->u[i-1]))return SCM_ERR_ARGUMENT;
    }
    return SCM_OK;
}

int scm_ocv_eval(const scm_ocv *c,double z,double *value,double *slope)
{
    size_t lo,hi,mid;
    double q;
    if(!value || !slope)return SCM_ERR_ARGUMENT;
    if(!isfinite(z))return SCM_ERR_NONFINITE;
    if(z<0 || z>1)return SCM_ERR_DOMAIN;
    if(!c || c->n==0) {
        q=tanh(8*(z-.5));
        *value=3+1.15*z+.08*q;
        *slope=1.15+.64*(1-q*q);
        return SCM_OK;
    }
    if(c->n<2 || !c->z || !c->u)return SCM_ERR_ARGUMENT;
    if(z<c->z[0] || z>c->z[c->n-1])return SCM_ERR_DOMAIN;
    lo=0;hi=c->n-1;
    while(hi-lo>1) { mid=lo+(hi-lo)/2;if(z>=c->z[mid])lo=mid;else hi=mid; }
    if(!(c->z[hi]>c->z[lo]))return SCM_ERR_ARGUMENT;
    *slope=(c->u[hi]-c->u[lo])/(c->z[hi]-c->z[lo]);
    *value=c->u[lo]+*slope*(z-c->z[lo]);
    return isfinite(*value)&&isfinite(*slope)?SCM_OK:SCM_ERR_NONFINITE;
}

int scm_model_init(scm_model_state *s,int n,const double *theta)
{
    scm_model_state t;
    int j,p=scm_model_ntheta(n);
    if(!s || !theta || !p)return SCM_ERR_ARGUMENT;
    memset(&t,0,sizeof(t));t.modes=n;
    for(j=0;j<p;j++) {if(!isfinite(theta[j]))return SCM_ERR_NONFINITE;t.theta[j]=theta[j];}
    for(j=0;j<n;j++) {
        t.tau[j]=exp(theta[j]);t.a[j]=1;
        if(!(t.tau[j]>0) || !isfinite(t.tau[j]))return SCM_ERR_DOMAIN;
    }
    t.gamma[0]=exp(theta[n]);t.gamma[1]=exp(theta[n+1]);
    t.z0=theta[n+2];t.Q=exp(theta[n+3]);t.ha=1;
    if(t.z0<0 || t.z0>1 || !(t.Q>0) || !isfinite(t.Q) ||
       !(t.gamma[0]>0) || !isfinite(t.gamma[0]) ||
       !(t.gamma[1]>0) || !isfinite(t.gamma[1]))return SCM_ERR_DOMAIN;
    *s=t;return SCM_OK;
}

int scm_model_step(scm_model_state *s,const scm_ocv *curve,
                   double dt,double I,scm_model_row *r)
{
    scm_model_state t;
    int i,j,n,k,status;
    double e,om,dlog,q,oldf,olda,oldb,sgn,dudz;
    if(!s || !r || !scm_model_ntheta(s->modes) || dt<0)return SCM_ERR_ARGUMENT;
    if(!isfinite(dt) || !isfinite(I))return SCM_ERR_NONFINITE;
    n=s->modes;t=*s;memset(r,0,sizeof(*r));
    t.charge_Ah+=I*dt/3600;t.elapsed+=dt;
    if(!isfinite(t.charge_Ah) || !isfinite(t.elapsed))return SCM_ERR_NONFINITE;
    r->z=t.z0-t.charge_Ah/t.Q;
    status=scm_ocv_eval(curve,r->z,&r->ocv,&dudz);
    if(status!=SCM_OK)return status;
    r->docv[n+2]=dudz;r->docv[n+3]=dudz*t.charge_Ah/t.Q;r->X[0]=-I;
    for(i=0;i<n;i++) {
        q=dt/t.tau[i];e=exp(-q);om=-expm1(-q);
        dlog=isfinite(q)?q*e:0;
        oldf=t.f[i];olda=t.a[i];
        t.f[i]=e*oldf+om*I;t.a[i]=e*olda;
        t.df[i]=e*t.df[i]+dlog*(oldf-I);
        t.da[i]=e*t.da[i]+dlog*olda;
        r->X[1+i]=-t.f[i];r->X[2+n+i]=-t.a[i];
        r->dX[i][1+i]=-t.df[i];r->dX[i][2+n+i]=-t.da[i];
    }
    if(I!=0 && dt!=0) {
        k=I>0?0:1;sgn=I>0?1:-1;
        q=t.gamma[k]*(fabs(I)/3600)*dt;
        if(isnan(q))return SCM_ERR_NONFINITE;
        e=exp(-q);om=-expm1(-q);dlog=isfinite(q)?-q*e:0;
        oldb=t.hb;olda=t.ha;t.hb=e*oldb+om*sgn;t.ha=e*olda;
        for(j=0;j<2;j++) {
            t.dhb[j]=e*t.dhb[j]+(j==k?dlog*(oldb-sgn):0);
            t.dha[j]=e*t.dha[j]+(j==k?dlog*olda:0);
        }
    }
    r->X[1+n]=-t.hb;r->X[2+2*n]=-t.ha;
    for(j=0;j<2;j++) {r->dX[n+j][1+n]=-t.dhb[j];r->dX[n+j][2+2*n]=-t.dha[j];}
    *s=t;return SCM_OK;
}

int scm_model_predict(const scm_model_row *r,int n,const double *alpha,
                      double *mu,double *jac)
{
    int i,j,p=scm_model_ntheta(n),m=scm_model_nalpha(n);
    double v;
    if(!r || !alpha || !mu || !p)return SCM_ERR_ARGUMENT;
    v=r->ocv;
    for(j=0;j<m;j++) {if(!isfinite(alpha[j]))return SCM_ERR_NONFINITE;v+=r->X[j]*alpha[j];}
    if(jac)for(i=0;i<p;i++) {
        jac[i]=r->docv[i];for(j=0;j<m;j++)jac[i]+=r->dX[i][j]*alpha[j];
        if(!isfinite(jac[i]))return SCM_ERR_NONFINITE;
    }
    if(!isfinite(v))return SCM_ERR_NONFINITE;
    *mu=v;return SCM_OK;
}

int scm_physical_step(const scm_physical *p,scm_physical_state *s,
                      const scm_ocv *curve,double dt,double I,double *V)
{
    scm_physical_state t;
    double e,om,q,sgn,u,slope;
    int i,status;
    if(!p || !s || !V || !scm_model_ntheta(p->modes) || dt<0)return SCM_ERR_ARGUMENT;
    if(!isfinite(dt) || !isfinite(I))return SCM_ERR_NONFINITE;
    if(!(p->Q>0) || !(p->gamma_plus>0) || !(p->gamma_minus>0) || p->H<0 || p->R0<0 ||
       !isfinite(p->Q) || !isfinite(p->gamma_plus) || !isfinite(p->gamma_minus) ||
       !isfinite(p->H) || !isfinite(p->R0) || s->h< -1 || s->h>1 || !isfinite(s->h))return SCM_ERR_DOMAIN;
    t=*s;t.z-=I*dt/(3600*p->Q);
    status=scm_ocv_eval(curve,t.z,&u,&slope);if(status!=SCM_OK)return status;
    for(i=0;i<p->modes;i++) {
        if(!(p->tau[i]>0) || p->R[i]<0 || !isfinite(p->tau[i]) ||
           !isfinite(p->R[i]) || !isfinite(t.v[i]))return SCM_ERR_DOMAIN;
        q=dt/p->tau[i];e=exp(-q);om=-expm1(-q);
        t.v[i]=e*t.v[i]+om*p->R[i]*I;u-=t.v[i];
    }
    if(I!=0 && dt!=0) {
        sgn=I>0?1:-1;q=(I>0?p->gamma_plus:p->gamma_minus)*(fabs(I)/3600)*dt;
        if(isnan(q))return SCM_ERR_NONFINITE;
        e=exp(-q);om=-expm1(-q);t.h=e*t.h+om*sgn;
    }
    u-=p->R0*I+p->H*t.h;
    if(!isfinite(u))return SCM_ERR_NONFINITE;
    *s=t;*V=u;return SCM_OK;
}
