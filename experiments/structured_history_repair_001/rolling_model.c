#include "rolling_model.h"
#include <math.h>
#include <string.h>

typedef char rm_query_size[(sizeof(lab_query_state)==224) ? 1 : -1];
typedef char rm_jet_size[(sizeof(ch_jet)==376) ? 1 : -1];

static int point_valid(const double *x)
{
    unsigned i;
    if(!x)return CH_ERR_ARGUMENT;
    for(i=0;i<CH_DIM;i++) {
        if(!isfinite(x[i]))return CH_ERR_NONFINITE;
        if(x[i]<ch_lower[i] || x[i]>ch_upper[i])return CH_ERR_DOMAIN;
    }
    return CH_OK;
}

static int sample_valid(double dt,double I,double V)
{
    if(!isfinite(dt) || !isfinite(I) || !isfinite(V))return CH_ERR_NONFINITE;
    return dt>=0. && dt<=1. && fabs(I)<=.25 ? CH_OK : CH_ERR_DOMAIN;
}

static int physical_valid(const double *x,double z,const double *f,
                          const double *a,double hb,double ha)
{
    double h=hb+ha*x[15],v;unsigned i;
    if(!isfinite(z) || !isfinite(h))return CH_ERR_NONFINITE;
    if(z<0. || z>1. || h< -1. || h>1.)return CH_ERR_DOMAIN;
    for(i=0;i<3;i++) {
        v=x[7+i]*f[i]+x[12+i]*a[i];
        if(!isfinite(v))return CH_ERR_NONFINITE;
        if(fabs(v)>.25)return CH_ERR_DOMAIN;
    }
    return CH_OK;
}

/* No scm_model_row or temporary model-state object: two scalar outputs only. */
static int ocv(double z,double *u,double *slope)
{
    int status=scm_ocv_eval(NULL,z,u,slope);
    if(status==SCM_OK)return CH_OK;
    if(status==SCM_ERR_DOMAIN)return CH_ERR_DOMAIN;
    if(status==SCM_ERR_NONFINITE)return CH_ERR_NONFINITE;
    return CH_ERR_ARGUMENT;
}

static double prediction(double u,double I,const double *x,const double *f,
                         const double *a,double hb,double ha)
{
    unsigned i;double mu=u;
    /* Preserve scm_model_predict/old compact row summation order. */
    mu+=(-I)*x[6];
    for(i=0;i<3;i++)mu+=(-f[i])*x[7+i];
    mu+=(-hb)*x[10];
    for(i=0;i<3;i++)mu+=(-a[i])*x[12+i];
    mu+=(-ha)*(x[10]*x[15]);
    return mu;
}

static int set_constants(scm_model_state *m,const double *x)
{
    unsigned i;
    m->modes=3;
    for(i=0;i<5;i++)m->theta[i]=x[i];
    m->theta[5]=x[11];m->theta[6]=x[5];
    for(i=0;i<3;i++) {
        m->tau[i]=exp(x[i]);
        if(!isfinite(m->tau[i]) || !(m->tau[i]>0.))return CH_ERR_NONFINITE;
    }
    for(i=0;i<2;i++) {
        m->gamma[i]=exp(x[3+i]);
        if(!isfinite(m->gamma[i]) || !(m->gamma[i]>0.))return CH_ERR_NONFINITE;
    }
    m->z0=x[11];m->Q=exp(x[5]);
    return isfinite(m->Q) && m->Q>0. ? CH_OK : CH_ERR_NONFINITE;
}

#if SH_ANALYTIC_ATTENUATION
static double attenuation(double q,unsigned derivative)
{
    double a=exp(-q);
    if(a==0. || !isfinite(q))return 0.;
    return derivative==0?a:derivative==1?q*a:q*(q-1.)*a;
}
static void analytic_attenuation(ch_jet *j)
{
    scm_model_state *m=&j->model;unsigned i;double q0,q1;
    for(i=0;i<3;i++) {
        double q=m->elapsed/m->tau[i];
        m->a[i]=attenuation(q,0);m->da[i]=attenuation(q,1);
    }
    q0=m->gamma[0]*SH_POSITIVE_CHARGE(j);q1=m->gamma[1]*SH_NEGATIVE_CHARGE(j);
    m->ha=exp(-(q0+q1));
    m->dha[0]=m->ha==0.?0.:-q0*m->ha;m->dha[1]=m->ha==0.?0.:-q1*m->ha;
    j->ddha[0]=m->ha==0.?0.:q0*(q0-1.)*m->ha;
    j->ddha[1]=m->ha==0.?0.:q0*q1*m->ha;
    j->ddha[2]=m->ha==0.?0.:q1*(q1-1.)*m->ha;
}
#endif

/* A jet must have been constructed by these kernels at the declared origin.
 * Coherent theta/z0 are checked without re-evaluating five unchanged rates on
 * every sample. Constructors always set rate fields from those theta values.
 */
static int jet_valid(const ch_jet *j,const double *origin)
{
    const scm_model_state *m;unsigned i;int status;
    if(!j)return CH_ERR_ARGUMENT;
    status=point_valid(origin);if(status)return status;m=&j->model;
    if(m->modes!=3 || m->z0!=origin[11] || m->theta[5]!=origin[11] ||
       m->theta[6]!=origin[5])return CH_ERR_ARGUMENT;
    if(!isfinite(m->Q) || !(m->Q>0.) || !isfinite(m->charge_Ah) ||
       !isfinite(m->elapsed))return CH_ERR_NONFINITE;
    if(m->elapsed<0.)return CH_ERR_DOMAIN;
    for(i=0;i<5;i++)if(m->theta[i]!=origin[i])return CH_ERR_ARGUMENT;
    for(i=0;i<3;i++) {
        if(!isfinite(m->tau[i]) || !(m->tau[i]>0.) ||
           !isfinite(m->f[i]) || !isfinite(m->a[i]) ||
           !isfinite(m->df[i]) || !isfinite(m->da[i]) ||
           !isfinite(j->ddf[i]) || !isfinite(j->dda[i]) ||
           !isfinite(j->ddhb[i]) || !isfinite(j->ddha[i]))return CH_ERR_NONFINITE;
    }
    if(!isfinite(m->hb) || !isfinite(m->ha))return CH_ERR_NONFINITE;
    for(i=0;i<2;i++)if(!isfinite(m->gamma[i]) || !(m->gamma[i]>0.) ||
                         !isfinite(m->dhb[i]) || !isfinite(m->dha[i]))
        return CH_ERR_NONFINITE;
#if SH_ANALYTIC_ATTENUATION
    if(SH_POSITIVE_CHARGE(j)<0. || SH_NEGATIVE_CHARGE(j)<0.)return CH_ERR_DOMAIN;
#endif
    return physical_valid(origin,m->z0-m->charge_Ah/m->Q,m->f,m->a,m->hb,m->ha);
}

static double uni(double v,double dv,double ddv,double d)
{
    return v+dv*d+.5*ddv*d*d;
}

static double bi(double v,const double *dv,const double *ddv,double d0,double d1)
{
    return v+dv[0]*d0+dv[1]*d1+.5*ddv[0]*d0*d0+
           ddv[1]*d0*d1+.5*ddv[2]*d1*d1;
}

int rm_init_jet(ch_jet *out,const double x[CH_DIM])
{
    unsigned i;int status;
    if(!out)return CH_ERR_ARGUMENT;
    status=point_valid(x);if(status)return status;
    memset(out,0,sizeof(*out));
    status=set_constants(&out->model,x);if(status)return status;
    for(i=0;i<3;i++)out->model.a[i]=1.;
    out->model.ha=1.;
    return jet_valid(out,x);
}

int rm_transport(const ch_jet *boundary,const double old_origin[CH_DIM],
                 const double point[CH_DIM],ch_jet *out)
{
    scm_model_state *m;double d,d0,d1,hb;unsigned i;int status;
#if !SH_ANALYTIC_ATTENUATION
    double ha;
#endif
    if(!out)return CH_ERR_ARGUMENT;
    status=jet_valid(boundary,old_origin);if(status)return status;
    status=point_valid(point);if(status)return status;
    if(out!=boundary)*out=*boundary;
    m=&out->model;
    for(i=0;i<3;i++) {
        d=point[i]-old_origin[i];
        m->f[i]=uni(m->f[i],m->df[i],out->ddf[i],d);
        m->df[i]+=out->ddf[i]*d;
#if !SH_ANALYTIC_ATTENUATION
        m->a[i]=uni(m->a[i],m->da[i],out->dda[i],d);
        m->da[i]+=out->dda[i]*d;
#endif
    }
    d0=point[3]-old_origin[3];d1=point[4]-old_origin[4];
    hb=bi(m->hb,m->dhb,out->ddhb,d0,d1);
#if !SH_ANALYTIC_ATTENUATION
    ha=bi(m->ha,m->dha,out->ddha,d0,d1);
#endif
    m->dhb[0]+=out->ddhb[0]*d0+out->ddhb[1]*d1;
    m->dhb[1]+=out->ddhb[1]*d0+out->ddhb[2]*d1;
#if !SH_ANALYTIC_ATTENUATION
    m->dha[0]+=out->ddha[0]*d0+out->ddha[1]*d1;
    m->dha[1]+=out->ddha[1]*d0+out->ddha[2]*d1;
    m->ha=ha;
#endif
    m->hb=hb;
    status=set_constants(m,point);if(status)return status;
#if SH_ANALYTIC_ATTENUATION
    analytic_attenuation(out);
#endif
    return jet_valid(out,point);
}

static int query_valid(const lab_query_state *s,const double *point)
{
    unsigned i;
    if(!s)return CH_ERR_ARGUMENT;
    if(!isfinite(s->charge_Ah) || !isfinite(s->inverse_Q) ||
       !(s->inverse_Q>0.) || !isfinite(s->z) || !isfinite(s->slope) ||
       !isfinite(s->mu) || !isfinite(s->hb) || !isfinite(s->ha))
        return CH_ERR_NONFINITE;
    for(i=0;i<3;i++)if(!isfinite(s->f[i]) || !isfinite(s->a[i]) ||
                         !isfinite(s->df[i]) || !isfinite(s->da[i]) ||
                         !isfinite(s->tau[i]) || !(s->tau[i]>0.))
        return CH_ERR_NONFINITE;
    for(i=0;i<2;i++)if(!isfinite(s->gamma[i]) || !(s->gamma[i]>0.) ||
                         !isfinite(s->dhb[i]) || !isfinite(s->dha[i]))
        return CH_ERR_NONFINITE;
    return physical_valid(point,s->z,s->f,s->a,s->hb,s->ha);
}

int rm_query_init(lab_query_state *out,const ch_jet *boundary,
                  const double old_origin[CH_DIM],const double point[CH_DIM])
{
    const scm_model_state *m;double d,d0,d1,Q,u;unsigned i;int status;
    if(!out)return CH_ERR_ARGUMENT;
    status=jet_valid(boundary,old_origin);if(status)return status;
    status=point_valid(point);if(status)return status;m=&boundary->model;
    for(i=0;i<3;i++) {
        d=point[i]-old_origin[i];
        out->f[i]=uni(m->f[i],m->df[i],boundary->ddf[i],d);
#if SH_ANALYTIC_ATTENUATION
        out->a[i]=attenuation(m->elapsed/exp(point[i]),0);
#else
        out->a[i]=uni(m->a[i],m->da[i],boundary->dda[i],d);
#endif
        out->df[i]=m->df[i]+boundary->ddf[i]*d;
#if SH_ANALYTIC_ATTENUATION
        out->da[i]=attenuation(m->elapsed/exp(point[i]),1);
#else
        out->da[i]=m->da[i]+boundary->dda[i]*d;
#endif
        out->tau[i]=exp(point[i]);
    }
    d0=point[3]-old_origin[3];d1=point[4]-old_origin[4];
    out->hb=bi(m->hb,m->dhb,boundary->ddhb,d0,d1);
#if !SH_ANALYTIC_ATTENUATION
    out->ha=bi(m->ha,m->dha,boundary->ddha,d0,d1);
#endif
    out->dhb[0]=m->dhb[0]+boundary->ddhb[0]*d0+boundary->ddhb[1]*d1;
    out->dhb[1]=m->dhb[1]+boundary->ddhb[1]*d0+boundary->ddhb[2]*d1;
#if SH_ANALYTIC_ATTENUATION
    {
        double q0=exp(point[3])*SH_POSITIVE_CHARGE(boundary);
        double q1=exp(point[4])*SH_NEGATIVE_CHARGE(boundary);
        out->ha=exp(-(q0+q1));
        out->dha[0]=out->ha==0.?0.:-q0*out->ha;out->dha[1]=out->ha==0.?0.:-q1*out->ha;
    }
#else
    out->dha[0]=m->dha[0]+boundary->ddha[0]*d0+boundary->ddha[1]*d1;
    out->dha[1]=m->dha[1]+boundary->ddha[1]*d0+boundary->ddha[2]*d1;
#endif
    out->gamma[0]=exp(point[3]);out->gamma[1]=exp(point[4]);
    Q=exp(point[5]);out->inverse_Q=1./Q;out->charge_Ah=m->charge_Ah;
    out->z=point[11]-out->charge_Ah/Q;
    status=ocv(out->z,&u,&out->slope);if(status)return status;
    out->mu=prediction(u,0.,point,out->f,out->a,out->hb,out->ha);
    return query_valid(out,point);
}

int rm_query_step(lab_query_state *s,const double point[CH_DIM],
                  const adc12_reading *reading)
{
    double dt,I,q,e,om,de,oldf,olda,oldb,sign,u,Q;unsigned i,k;int status;
    if(!s || !reading)return CH_ERR_ARGUMENT;
    status=point_valid(point);if(status)return status;
    status=query_valid(s,point);if(status)return status;
    if(!isfinite(reading->temperature_C))return CH_ERR_NONFINITE;
    dt=reading->dt_s;I=reading->current_A;
    status=sample_valid(dt,I,reading->voltage_V);if(status)return status;
    s->charge_Ah+=I*dt/3600.;
    Q=exp(point[5]);s->z=point[11]-s->charge_Ah/Q;
    if(!isfinite(s->charge_Ah))return CH_ERR_NONFINITE;
    status=ocv(s->z,&u,&s->slope);if(status)return status;
    for(i=0;i<3;i++) {
        q=dt/s->tau[i];e=exp(-q);om=-expm1(-q);
        de=isfinite(q)?q*e:0.;oldf=s->f[i];olda=s->a[i];
        s->f[i]=e*oldf+om*I;s->a[i]=e*olda;
        s->df[i]=e*s->df[i]+de*(oldf-I);s->da[i]=e*s->da[i]+de*olda;
    }
    if(I!=0. && dt!=0.) {
        k=I>0.?0u:1u;sign=I>0.?1.:-1.;
        q=s->gamma[k]*(fabs(I)/3600.)*dt;
        if(isnan(q))return CH_ERR_NONFINITE;
        e=exp(-q);om=-expm1(-q);de=isfinite(q)?-q*e:0.;
        oldb=s->hb;olda=s->ha;s->hb=e*oldb+om*sign;s->ha=e*olda;
        for(i=0;i<2;i++) {
            s->dhb[i]=e*s->dhb[i]+(i==k?de*(oldb-sign):0.);
            s->dha[i]=e*s->dha[i]+(i==k?de*olda:0.);
        }
    }
    s->mu=prediction(u,I,point,s->f,s->a,s->hb,s->ha);
    return query_valid(s,point);
}

double rm_query_derivative(const lab_query_state *s,const double point[CH_DIM],
                           const adc12_reading *reading,unsigned coordinate)
{
    double d;unsigned i;
    if(!s || !point || !reading || coordinate>=CH_DIM)return NAN;
    if(coordinate<3) {
        i=coordinate;d=(-s->df[i])*point[7+i]+(-s->da[i])*point[12+i];
    } else if(coordinate<5) {
        i=coordinate-3;d=(-s->dhb[i])*point[10]+(-s->dha[i])*(point[10]*point[15]);
    } else if(coordinate==5)d=s->slope*(s->charge_Ah*s->inverse_Q);
    else if(coordinate==6)d=-reading->current_A;
    else if(coordinate<10)d=-s->f[coordinate-7];
    else if(coordinate==10)d=-s->hb-s->ha*point[15];
    else if(coordinate==11)d=s->slope;
    else if(coordinate<15)d=-s->a[coordinate-12];
    else d=-s->ha*point[10];
    return isfinite(d)?d:NAN;
}

int rm_merge_step(ch_jet *j,const double origin[CH_DIM],const scm_sample *sample,
                  double sigma_V,double row[CH_AUG])
{
    scm_model_state *m;double dt,I,q,e,om,de,dde,oldf,olda,oldb,old_df,old_da;
    double sign,z,u,slope,second;unsigned i,k,p,a,b;int status;
    if(!j || !sample || !row)return CH_ERR_ARGUMENT;
    status=jet_valid(j,origin);if(status)return status;
    status=sample_valid(sample->dt,sample->current,sample->voltage);if(status)return status;
    if(!isfinite(sigma_V))return CH_ERR_NONFINITE;
    if(!(sigma_V>0.))return CH_ERR_DOMAIN;
    m=&j->model;dt=sample->dt;I=sample->current;
    m->charge_Ah+=I*dt/3600.;m->elapsed+=dt;
#if SH_ANALYTIC_ATTENUATION
    if(I>0.)SH_POSITIVE_CHARGE(j)+=I*dt/3600.;
    else SH_NEGATIVE_CHARGE(j)+=(-I)*dt/3600.;
#endif
    if(!isfinite(m->charge_Ah) || !isfinite(m->elapsed))return CH_ERR_NONFINITE;
    z=m->z0-m->charge_Ah/m->Q;
    status=ocv(z,&u,&slope);if(status)return status;
    second=tanh(8.*(z-.5));second=-10.24*second*(1.-second*second);
    for(i=0;i<3;i++) {
        q=dt/m->tau[i];e=exp(-q);om=-expm1(-q);
        de=isfinite(q)?q*e:0.;dde=isfinite(q)?q*(q-1.)*e:0.;
        oldf=m->f[i];olda=m->a[i];old_df=m->df[i];old_da=m->da[i];
        j->ddf[i]=e*j->ddf[i]+2.*de*old_df+dde*(oldf-I);
#if !SH_ANALYTIC_ATTENUATION
        j->dda[i]=e*j->dda[i]+2.*de*old_da+dde*olda;
#endif
        m->f[i]=e*oldf+om*I;m->a[i]=e*olda;
        m->df[i]=e*old_df+de*(oldf-I);m->da[i]=e*old_da+de*olda;
    }
    if(I!=0. && dt!=0.) {
        k=I>0.?0u:1u;sign=I>0.?1.:-1.;
        q=m->gamma[k]*(fabs(I)/3600.)*dt;
        if(isnan(q))return CH_ERR_NONFINITE;
        e=exp(-q);om=-expm1(-q);de=isfinite(q)?-q*e:0.;
        dde=isfinite(q)?q*(q-1.)*e:0.;oldb=m->hb;olda=m->ha;
        /* Keep first derivatives untouched until all second derivatives have
         * used them; no local two-vector or model-row scratch is required. */
        for(p=0;p<3;p++) {
            a=p==2?1u:0u;b=p==0?0u:1u;
            j->ddhb[p]=e*j->ddhb[p]+(a==k?de*m->dhb[b]:0.)+
                (b==k?de*m->dhb[a]:0.)+(a==k && b==k?dde*(oldb-sign):0.);
            j->ddha[p]=e*j->ddha[p]+(a==k?de*m->dha[b]:0.)+
                (b==k?de*m->dha[a]:0.)+(a==k && b==k?dde*olda:0.);
        }
        m->hb=e*oldb+om*sign;m->ha=e*olda;
        for(i=0;i<2;i++) {
            m->dhb[i]=e*m->dhb[i]+(i==k?de*(oldb-sign):0.);
            m->dha[i]=e*m->dha[i]+(i==k?de*olda:0.);
        }
    }
#if SH_ANALYTIC_ATTENUATION
    analytic_attenuation(j);
#endif
    status=jet_valid(j,origin);if(status)return status;
    for(i=0;i<CH_AUG;i++)row[i]=0.;
    for(i=0;i<3;i++) {
        double sd=ch_public_sd[i],sr=ch_public_sd[7+i],sv=ch_public_sd[12+i],dd_a;
#if SH_ANALYTIC_ATTENUATION
        dd_a=attenuation(m->elapsed/m->tau[i],2);
#else
        dd_a=j->dda[i];
#endif
        row[2*i]=-.5*j->ddf[i]*sd*sd*sr/sigma_V;
        row[2*i+1]=-.5*dd_a*sd*sd*sv/sigma_V;
        row[15+2*i]=-m->df[i]*sd*sr/sigma_V;
        row[16+2*i]=-m->da[i]*sd*sv/sigma_V;
        row[27+2*i]=-m->f[i]*sr/sigma_V;
        row[28+2*i]=-m->a[i]*sv/sigma_V;
    }
    for(i=0;i<3;i++) {
        a=i==2?4u:3u;b=i==0?3u:4u;
        q=(a==b?.5:1.)*ch_public_sd[a]*ch_public_sd[b]/sigma_V;
        row[6+i]=-j->ddhb[i]*q*ch_public_sd[10];
        row[9+i]=-j->ddha[i]*q*SH_U_SD;
    }
    for(i=0;i<2;i++) {
        row[21+i]=-m->dhb[i]*ch_public_sd[3+i]*ch_public_sd[10]/sigma_V;
        row[23+i]=-m->dha[i]*ch_public_sd[3+i]*SH_U_SD/sigma_V;
    }
    row[33]=-m->hb*ch_public_sd[10]/sigma_V;row[34]=-m->ha*SH_U_SD/sigma_V;
    row[35]=-I*ch_public_sd[6]/sigma_V;
    row[12]=.5*second*ch_public_sd[11]*ch_public_sd[11]/sigma_V;
    row[13]=-second*m->charge_Ah*ch_public_sd[11]*SH_INVERSE_Q_SD/sigma_V;
    row[14]=.5*second*m->charge_Ah*m->charge_Ah*SH_INVERSE_Q_SD*SH_INVERSE_Q_SD/sigma_V;
    row[25]=slope*ch_public_sd[11]/sigma_V;
    row[26]=-slope*m->charge_Ah*SH_INVERSE_Q_SD/sigma_V;
    row[36]=(u-sample->voltage)/sigma_V;
    for(i=0;i<CH_AUG;i++)if(!isfinite(row[i]))return CH_ERR_NONFINITE;
    return CH_OK;
}
