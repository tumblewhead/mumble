#include "compact_history.h"
#include <float.h>
#include <math.h>
#include <string.h>

/* Source constants match the already-qualified public-prior export. All are
 * read-only; no per-bank copy, alternate prior or componentwise conditioning.
 */
const double ch_public_mean[CH_DIM] = {
    -3.0484125313829042, -.7458274383888583, 1.90333124488516,
    5.0106352940962555, 5.703782474656201, -2.8134107167600364,
    .1, .1, .1, .1, .024, .68, 0., 0., 0., 0.
};
const double ch_public_sd[CH_DIM] = {
    .664699061636066, .664699061636066, .8647934172782233,
    1.5821241788613198, 1.5821241788613198, .347557011337284,
    .2886751345948129, .2886751345948129, .2886751345948129,
    .2886751345948129, .02886751345948129, .21650635094610968,
    .046188021535170064, .046188021535170064, .046188021535170064,
    .5773502691896258
};
const double ch_lower[CH_DIM] = {
    -4.199705077879927, -1.8971199848858813, .40546510810816438,
    1.6094379124341003, 1.6094379124341003, -3.5065578973199818,
    0., 0., 0., 0., 0., .2, -.08, -.08, -.08, -1.
};
const double ch_upper[CH_DIM] = {
    -1.8971199848858813, .40546510810816438, 3.4011973816621555,
    7.0900768357760917, 7.0900768357760917, -2.3025850929940455,
    1., 1., 1., 1., .1, .95, .08, .08, .08, 1.
};
const unsigned char ch_pair[CH_PAIRS][2] = {
    {0,0},{0,7},{0,12}, {1,1},{1,8},{1,13}, {2,2},{2,9},{2,14},
    {3,3},{3,4},{4,4}, {3,10},{3,15},{4,10},{4,15}, {10,15},
    {11,11},{5,11},{5,5}
};

typedef char ch_double_is_binary64[(sizeof(double)==8 && DBL_MANT_DIG==53 &&
                                  DBL_MAX_EXP==1024) ? 1 : -1];
typedef char ch_core_budget[(sizeof(ch_context)<=8112) ? 1 : -1];
typedef char ch_complete_planning_budget[(sizeof(ch_operational_layout)+
    CH_OWN_STACK_CAP_BYTES+CH_RUNTIME_IRQ_CALLER_RESERVE_BYTES<=10240) ? 1 : -1];

typedef struct { double sum, correction; } ch_sum;

static int sum_add(ch_sum *a,double x)
{
    double n,e;
    if(!isfinite(x))return CH_ERR_NONFINITE;
    n=a->sum+x;
    if(!isfinite(n))return CH_ERR_NONFINITE;
    e=fabs(a->sum)>=fabs(x)?(a->sum-n)+x:(x-n)+a->sum;
    a->correction+=e;a->sum=n;
    return isfinite(a->correction) && isfinite(a->sum+a->correction)?CH_OK:CH_ERR_NONFINITE;
}

static double sum_value(const ch_sum *a) { return a->sum+a->correction; }

size_t ch_qr_index(unsigned r,unsigned c)
{
    return (size_t)r*CH_AUG-(size_t)r*(r-1u)/2u+(c-r);
}

size_t ch_packed_index(unsigned r,unsigned c)
{
    unsigned t;if(c>r){t=r;r=c;c=t;}
    return (size_t)r*(r+1u)/2u+c;
}

static double qr(const ch_bank *b,unsigned r,unsigned c)
{
    return c<r?0.:b->upper[ch_qr_index(r,c)];
}

static int point_support(const ch_bank *b,const double *x,double *minimum)
{
    double lo=DBL_MAX,Q,z0,z1;unsigned i;
    for(i=0;i<CH_DIM;i++) {
        if(!isfinite(x[i]))return CH_ERR_NONFINITE;
        lo=fmin(lo,fmin(x[i]-ch_lower[i],ch_upper[i]-x[i]));
    }
    Q=exp(x[5]);
    if(!isfinite(Q) || !(Q>0))return CH_ERR_NONFINITE;
    z0=x[11]-b->charge_max_Ah/Q;
    z1=x[11]-b->charge_min_Ah/Q;
    if(!isfinite(z0) || !isfinite(z1))return CH_ERR_NONFINITE;
    lo=fmin(lo,fmin(z0,1.-z1));
    if(minimum)*minimum=lo;
    return lo>=0.?CH_OK:CH_ERR_DOMAIN;
}

static int input_valid(const ch_context *c,const unsigned char *id,uint64_t index)
{
    double charge,z;
    if(!c || !id)return CH_ERR_ARGUMENT;
    if(!c->bank.available)return CH_ERR_UNAVAILABLE;
    if(memcmp(id,c->bank.source_id,32))return CH_ERR_SOURCE;
    if(index!=c->bank.next_index)return CH_ERR_ORDER;
    if(index==UINT64_MAX || c->bank.model_steps==UINT64_MAX ||
       c->bank.qr_rows==UINT64_MAX)return CH_ERR_OVERFLOW;
    if(!isfinite(c->sample.dt) || !isfinite(c->sample.current) ||
       !isfinite(c->sample.voltage) || !isfinite(c->sample.voltage/CH_SIGMA))
        return CH_ERR_NONFINITE;
    if(c->sample.dt<0 || c->sample.dt>1. || fabs(c->sample.current)>.25)
        return CH_ERR_DOMAIN;
    charge=c->bank.jet.model.charge_Ah+c->sample.current*c->sample.dt/3600.;
    z=c->bank.jet.model.z0-charge/c->bank.jet.model.Q;
    if(!isfinite(charge) || !isfinite(z))return CH_ERR_NONFINITE;
    return z>=0. && z<=1.?CH_OK:CH_ERR_DOMAIN;
}

int ch_init(ch_context *c,const unsigned char id[32],const double origin[CH_DIM])
{
    unsigned i;int status;
    if(!c || !id || !origin)return CH_ERR_ARGUMENT;
    for(i=0;i<CH_DIM;i++)if(!isfinite(origin[i]) || origin[i]<ch_lower[i] ||
                            origin[i]>ch_upper[i])return CH_ERR_DOMAIN;
    /* Init inputs must not alias the destination, as documented for config
     * backing objects throughout the original component interfaces. */
    memset(c,0,sizeof(*c));
    memcpy(c->bank.origin,origin,sizeof(c->bank.origin));
    memcpy(c->bank.estimate,origin,sizeof(c->bank.estimate));
    memcpy(c->bank.source_id,id,32);
    for(i=0;i<5;i++)c->workspace.ingest.row[i]=origin[i];
    c->workspace.ingest.row[5]=origin[11];
    c->workspace.ingest.row[6]=origin[5];
    status=scm_model_init(&c->bank.jet.model,3,c->workspace.ingest.row);
    if(status){c->bank.last_error=status;return status;}
    c->bank.available=1;return CH_OK;
}

/* Same actual-step ordering as scm_model_step; signed second derivatives are
 * propagated alongside, not substituted into the source model recurrence.
 * The stored row represents (mu-V)/sigma + J*S*d/sigma + quadratic terms.
 */
static int advance_jet(ch_jet *j,const double *x,const scm_sample *sample,double *row)
{
    scm_model_state *m=&j->model;
    double dt=sample->dt,I=sample->current,q,e,om,de,dde;
    double oldf,olda,oldb,old_df,old_da,sign,z,u,slope,second,w,mu,h0=x[15],H=x[10];
    double hb_first[2],ha_first[2];
    unsigned i,k,p;int status;
    m->charge_Ah+=I*dt/3600.;m->elapsed+=dt;
    if(!isfinite(m->charge_Ah) || !isfinite(m->elapsed))return CH_ERR_NONFINITE;
    z=m->z0-m->charge_Ah/m->Q;
    status=scm_ocv_eval(NULL,z,&u,&slope);if(status)return status;
    second=tanh(8.*(z-.5));second=-10.24*second*(1.-second*second);
    for(i=0;i<3;i++) {
        q=dt/m->tau[i];e=exp(-q);om=-expm1(-q);
        de=isfinite(q)?q*e:0.;dde=isfinite(q)?q*(q-1.)*e:0.;
        oldf=m->f[i];olda=m->a[i];old_df=m->df[i];old_da=m->da[i];
        j->ddf[i]=e*j->ddf[i]+2.*de*old_df+dde*(oldf-I);
        j->dda[i]=e*j->dda[i]+2.*de*old_da+dde*olda;
        m->f[i]=e*oldf+om*I;m->a[i]=e*olda;
        m->df[i]=e*old_df+de*(oldf-I);m->da[i]=e*old_da+de*olda;
    }
    if(I!=0. && dt!=0.) {
        k=I>0.?0u:1u;sign=I>0.?1.:-1.;
        q=m->gamma[k]*(fabs(I)/3600.)*dt;
        if(isnan(q))return CH_ERR_NONFINITE;
        e=exp(-q);om=-expm1(-q);de=isfinite(q)?-q*e:0.;
        dde=isfinite(q)?q*(q-1.)*e:0.;oldb=m->hb;olda=m->ha;
        hb_first[0]=m->dhb[0];hb_first[1]=m->dhb[1];
        ha_first[0]=m->dha[0];ha_first[1]=m->dha[1];
        for(p=0;p<3;p++) {
            unsigned a=p==2?1u:0u,b=p==0?0u:1u;
            j->ddhb[p]=e*j->ddhb[p]+(a==k?de*hb_first[b]:0.)+
                (b==k?de*hb_first[a]:0.)+(a==k && b==k?dde*(oldb-sign):0.);
            j->ddha[p]=e*j->ddha[p]+(a==k?de*ha_first[b]:0.)+
                (b==k?de*ha_first[a]:0.)+(a==k && b==k?dde*olda:0.);
        }
        m->hb=e*oldb+om*sign;m->ha=e*olda;
        for(i=0;i<2;i++) {
            m->dhb[i]=e*hb_first[i]+(i==k?de*(oldb-sign):0.);
            m->dha[i]=e*ha_first[i]+(i==k?de*olda:0.);
        }
    }
    mu=u;mu+=(-I)*x[6];
    for(i=0;i<3;i++)mu+=(-m->f[i])*x[7+i];
    mu+=(-m->hb)*H;
    for(i=0;i<3;i++)mu+=(-m->a[i])*x[12+i];
    mu+=(-m->ha)*(H*h0);
    for(i=0;i<CH_AUG;i++)row[i]=0.;
    for(i=0;i<3;i++) {
        row[i]=(-m->df[i])*x[7+i]+(-m->da[i])*x[12+i];
        row[7+i]=-m->f[i];row[12+i]=-m->a[i];
        row[16+3*i]=(-j->ddf[i])*x[7+i]+(-j->dda[i])*x[12+i];
        row[17+3*i]=-m->df[i];row[18+3*i]=-m->da[i];
    }
    for(i=0;i<2;i++) {
        row[3+i]=(-m->dhb[i])*H+(-m->dha[i])*(H*h0);
        row[28+2*i]=-m->dhb[i]-m->dha[i]*h0;
        row[29+2*i]=-m->dha[i]*H;
    }
    for(i=0;i<3;i++)row[25+i]=(-j->ddhb[i])*H+(-j->ddha[i])*(H*h0);
    row[6]=-I;row[10]=-m->hb-m->ha*h0;row[15]=-m->ha*H;
    w=m->charge_Ah/m->Q;row[5]=slope*w;row[11]=slope;
    row[32]=-m->ha;row[33]=second;row[34]=second*w;
    row[35]=second*w*w-slope*w;
    for(i=0;i<CH_DIM;i++)row[i]=row[i]*ch_public_sd[i]/CH_SIGMA;
    for(i=0;i<CH_PAIRS;i++) {
        unsigned a=ch_pair[i][0],b=ch_pair[i][1];
        row[16+i]=(a==b?.5:1.)*row[16+i]*ch_public_sd[a]*ch_public_sd[b]/CH_SIGMA;
    }
    row[36]=(mu-sample->voltage)/CH_SIGMA;
    for(i=0;i<CH_AUG;i++)if(!isfinite(row[i]))return CH_ERR_NONFINITE;
    return CH_OK;
}

int ch_prepare(ch_context *c,const unsigned char id[32],uint64_t index)
{
    int status=input_valid(c,id,index);if(status)return status;
    c->workspace.ingest.prospective=c->bank.jet;
    return advance_jet(&c->workspace.ingest.prospective,c->bank.origin,&c->sample,
                       c->workspace.ingest.row);
}

static int qr_insert(ch_bank *b,double *row)
{
    unsigned i,k;
    for(i=0;i<CH_AUG;i++)if(!isfinite(row[i]))return CH_ERR_NONFINITE;
    for(i=0;i<CH_AUG;i++) {
        size_t ii=ch_qr_index(i,i);
        double a=b->upper[ii],v=row[i],scale,aa,bb,h,cs,sn,r;
        if(!isfinite(a))return CH_ERR_NONFINITE;
        if(v==0.)continue;
        scale=fmax(fabs(a),fabs(v));aa=a/scale;bb=v/scale;
        h=hypot(aa,bb);cs=aa/h;sn=bb/h;r=scale*h;
        if(!isfinite(r) || !(r>0.))return CH_ERR_NONFINITE;
        b->upper[ii]=r;row[i]=0.;
        for(k=i+1;k<CH_AUG;k++) {
            size_t ik=ch_qr_index(i,k);double old=b->upper[ik],tail=row[k];
            b->upper[ik]=cs*old+sn*tail;row[k]=-sn*old+cs*tail;
            if(!isfinite(b->upper[ik]) || !isfinite(row[k]))return CH_ERR_NONFINITE;
        }
    }
    return CH_OK;
}

static int latch(ch_bank *b,int status)
{
    b->available=0;b->last_error=status;return status;
}

int ch_push(ch_context *c,const unsigned char id[32],uint64_t index)
{
    int status=input_valid(c,id,index);if(status)return status;
    c->workspace.ingest.prospective=c->bank.jet;
    ++c->bank.model_steps;
    status=advance_jet(&c->workspace.ingest.prospective,c->bank.origin,&c->sample,
                       c->workspace.ingest.row);
    if(status)return latch(&c->bank,status);
    status=qr_insert(&c->bank,c->workspace.ingest.row);
    if(status)return latch(&c->bank,status);
    c->bank.jet=c->workspace.ingest.prospective;
    c->bank.charge_min_Ah=fmin(c->bank.charge_min_Ah,c->bank.jet.model.charge_Ah);
    c->bank.charge_max_Ah=fmax(c->bank.charge_max_Ah,c->bank.jet.model.charge_Ah);
    ++c->bank.next_index;++c->bank.qr_rows;return CH_OK;
}

static double displacement(const ch_bank *b,const double *x,unsigned i)
{
    return (x[i]-b->origin[i])/ch_public_sd[i];
}

/* Monomials are generated on demand: no second 37-element vector or factor. */
static double feature(const ch_bank *b,const double *x,unsigned column,int kind)
{
    if(column<16)return displacement(b,x,column);
    if(column==36)return 1.;
    if(kind==CH_AFFINE)return 0.;
    column-=16;
    return displacement(b,x,ch_pair[column][0])*displacement(b,x,ch_pair[column][1]);
}

static int residual_row(const ch_bank *b,const double *x,unsigned row,int kind,
                        double *value,double *absolute)
{
    ch_sum sum={0,0},abs_sum={0,0};unsigned k;
    for(k=row;k<CH_AUG;k++) {
        double product=qr(b,row,k)*feature(b,x,k,kind);
        if(sum_add(&sum,product) || sum_add(&abs_sum,fabs(product)))return CH_ERR_NONFINITE;
    }
    *value=sum_value(&sum);*absolute=sum_value(&abs_sum);return CH_OK;
}

static double row_derivative(const ch_bank *b,const double *x,unsigned row,
                             unsigned coordinate,int kind)
{
    ch_sum sum={0,0};unsigned k;
    if(sum_add(&sum,qr(b,row,coordinate)))return NAN;
    if(kind==CH_QUARTIC)for(k=0;k<CH_PAIRS;k++) {
        unsigned a=ch_pair[k][0],d=ch_pair[k][1];double coefficient=qr(b,row,16+k);
        if(a==coordinate && sum_add(&sum,coefficient*displacement(b,x,d)))return NAN;
        if(d==coordinate && sum_add(&sum,coefficient*displacement(b,x,a)))return NAN;
    }
    return sum_value(&sum)/ch_public_sd[coordinate];
}

static double precision(unsigned i)
{
    double sd=i==5?.20951093757861336:ch_public_sd[i];
    return 1./(sd*sd);
}

/* Two equal-weight common-covariance kernels differ only in logQ. Computing
 * both normalizers explicitly preserves their offsets. No support mass is
 * guessed, and the prior is never folded into an observation row.
 */
static int add_prior(ch_context *c,const double *x,int curvature,int mode,int derivatives)
{
    const double means[2]={-3.0907210901048416,-2.536100343415231};
    ch_sum common={0,0},normal={0,0};unsigned i;
    double q0,q1,l0,l1,m,logsum,w1,w0,dp,cost;
    if(c->bank.prior_evaluations==UINT64_MAX)return CH_ERR_OVERFLOW;
    ++c->bank.prior_evaluations;
    for(i=0;i<CH_DIM;i++) {
        double sd=i==5?.20951093757861336:ch_public_sd[i];
        if(sum_add(&normal,log(sd*sd)))return CH_ERR_NONFINITE;
        if(i!=5 && sum_add(&common,(x[i]-ch_public_mean[i])*
                          (x[i]-ch_public_mean[i])*precision(i)))return CH_ERR_NONFINITE;
    }
    q0=x[5]-means[0];q1=x[5]-means[1];
    l0=-.5*q0*q0*precision(5);l1=-.5*q1*q1*precision(5);
    m=fmax(l0,l1);logsum=m+log(exp(l0-m)+exp(l1-m));
    w1=exp(l1-logsum);w0=exp(l0-logsum);
    cost=.5*sum_value(&common)+.5*sum_value(&normal)+
         8.*log(2.*3.141592653589793238462643383279502884)+log(2.)-logsum;
    if(!isfinite(cost) || !isfinite(w0) || !isfinite(w1))return CH_ERR_NONFINITE;
    c->result.prior_cost=cost;c->result.total_cost=c->result.likelihood_cost+cost;
    c->result.flags|=CH_FLAG_PRIOR_INCLUDED;
    if(mode==CH_PRIOR_MAJORIZER)c->result.flags|=CH_FLAG_PRIOR_MAJORIZER;
    if(derivatives)for(i=0;i<CH_DIM;i++) {
        double g=(x[i]-ch_public_mean[i])*precision(i),h=precision(i);
        if(i==5) {
            dp=(means[0]-means[1])*precision(i);
            g=q0*precision(i)+w1*dp;
            if(mode==CH_EXACT_PRIOR)h-=w0*w1*dp*dp;
        }
        c->workspace.query.gradient[i]+=g;
        if(curvature!=CH_NO_CURVATURE)c->workspace.query.packed[ch_packed_index(i,i)]+=h;
        if(!isfinite(c->workspace.query.gradient[i]) ||
           (curvature!=CH_NO_CURVATURE &&
            !isfinite(c->workspace.query.packed[ch_packed_index(i,i)])))return CH_ERR_NONFINITE;
    }
    return isfinite(c->result.total_cost)?CH_OK:CH_ERR_NONFINITE;
}

int ch_endpoint(ch_context *c)
{
    const ch_bank *b;const scm_model_state *m;const double *x;
    unsigned i,p;double tau_delta,g0,g1,dh,minimum;int status,approx=0;
    if(!c)return CH_ERR_ARGUMENT;
    b=&c->bank;if(!b->available)return CH_ERR_UNAVAILABLE;m=&b->jet.model;
    x=c->workspace.query.point;
    status=point_support(b,x,&minimum);
    if(status)return status;
    c->result.detail.endpoint.min_support_slack=minimum;
    c->result.detail.endpoint.SOC=x[11]-m->charge_Ah/exp(x[5]);
    for(i=0;i<CH_DIM;i++)if(x[i]!=b->origin[i])approx=1;
    c->result.flags&=~(CH_FLAG_ENDPOINT_APPROXIMATE|CH_FLAG_ENDPOINT_INVALID);
    if(approx)c->result.flags|=CH_FLAG_ENDPOINT_APPROXIMATE;
    minimum=fmin(c->result.detail.endpoint.SOC,1.-c->result.detail.endpoint.SOC);
    for(i=0;i<3;i++) {
        double dR=x[7+i]-b->origin[7+i],dv=x[12+i]-b->origin[12+i];
        double R=b->origin[7+i],v=b->origin[12+i],value;
        tau_delta=x[i]-b->origin[i];
        value=R*m->f[i]+v*m->a[i]+(R*m->df[i]+v*m->da[i])*tau_delta+
            m->f[i]*dR+m->a[i]*dv+
            .5*(R*b->jet.ddf[i]+v*b->jet.dda[i])*tau_delta*tau_delta+
            m->df[i]*tau_delta*dR+m->da[i]*tau_delta*dv;
        c->result.detail.endpoint.v[i]=value;
        if(!isfinite(value))return CH_ERR_NONFINITE;
        minimum=fmin(minimum,.25-fabs(value));
    }
    g0=x[3]-b->origin[3];g1=x[4]-b->origin[4];dh=x[15]-b->origin[15];
    c->result.detail.endpoint.h=m->hb+m->ha*b->origin[15]+m->ha*dh+
        (m->dhb[0]+b->origin[15]*m->dha[0])*g0+
        (m->dhb[1]+b->origin[15]*m->dha[1])*g1+
        m->dha[0]*g0*dh+m->dha[1]*g1*dh;
    for(p=0;p<3;p++) {
        double product=p==0?g0*g0:p==1?g0*g1:g1*g1;
        c->result.detail.endpoint.h+=(p==1?1.:.5)*
            (b->jet.ddhb[p]+b->origin[15]*b->jet.ddha[p])*product;
    }
    if(!isfinite(c->result.detail.endpoint.h) ||
       !isfinite(c->result.detail.endpoint.SOC))return CH_ERR_NONFINITE;
    minimum=fmin(minimum,1.-fabs(c->result.detail.endpoint.h));
    c->result.detail.endpoint.min_endpoint_slack=minimum;
    if(minimum<0)c->result.flags|=CH_FLAG_ENDPOINT_INVALID;
    return CH_OK;
}

int ch_query(ch_context *c,int kind,int curvature,int prior)
{
    ch_sum cost={0,0},absolute={0,0};unsigned r,i,j,k;double slack;int status;
    if(!c || (kind!=CH_AFFINE && kind!=CH_QUARTIC) || curvature<0 || curvature>2 ||
       prior<0 || prior>2)return CH_ERR_ARGUMENT;
    if(!c->bank.available)return CH_ERR_UNAVAILABLE;
    status=point_support(&c->bank,c->workspace.query.point,&slack);if(status)return status;
    if(c->bank.query_evaluations==UINT64_MAX)return CH_ERR_OVERFLOW;
    ++c->bank.query_evaluations;memset(&c->result,0,sizeof(c->result));
    for(i=0;i<CH_DIM;i++)c->workspace.query.gradient[i]=0.;
    for(i=0;i<CH_PACKED;i++)c->workspace.query.packed[i]=0.;
    for(r=0;r<CH_AUG;r++) {
        double residual,abs_row;
        status=residual_row(&c->bank,c->workspace.query.point,r,kind,&residual,&abs_row);
        if(status)return status;
        if(sum_add(&cost,.5*residual*residual) || sum_add(&absolute,.5*abs_row*abs_row))
            return CH_ERR_NONFINITE;
        for(i=0;i<CH_DIM;i++) {
            double d=row_derivative(&c->bank,c->workspace.query.point,r,i,kind);
            c->workspace.query.row_gradient[i]=d;
            c->workspace.query.gradient[i]+=residual*d;
            if(!isfinite(d) || !isfinite(c->workspace.query.gradient[i]))return CH_ERR_NONFINITE;
        }
        if(curvature!=CH_NO_CURVATURE) {
            for(i=0;i<CH_DIM;i++)for(j=0;j<=i;j++)
                c->workspace.query.packed[ch_packed_index(i,j)]+=
                    c->workspace.query.row_gradient[i]*c->workspace.query.row_gradient[j];
            if(curvature==CH_TRUE_HESSIAN && kind==CH_QUARTIC)for(k=0;k<CH_PAIRS;k++) {
                unsigned a=ch_pair[k][0],d=ch_pair[k][1];
                c->workspace.query.packed[ch_packed_index(a,d)]+=
                    residual*(a==d?2.:1.)*qr(&c->bank,r,16+k)/
                    (ch_public_sd[a]*ch_public_sd[d]);
            }
        }
    }
    for(i=0;i<CH_PACKED;i++)if(!isfinite(c->workspace.query.packed[i]))return CH_ERR_NONFINITE;
    c->result.likelihood_cost=sum_value(&cost);c->result.total_cost=sum_value(&cost);
    c->result.cost_absolute_scale=sum_value(&absolute);
    c->result.flags=CH_FLAG_FEASIBLE|CH_FLAG_COST_AVAILABLE;
    if(prior){status=add_prior(c,c->workspace.query.point,curvature,prior,1);if(status)return status;}
    return ch_endpoint(c);
}

/* Cost-only trial query preserves the proposal vectors in the phase union. */
static int cost_query(ch_context *c)
{
    ch_sum cost={0,0},absolute={0,0};unsigned r;double slack;int status;
    status=point_support(&c->bank,c->workspace.query.point,&slack);if(status)return status;
    if(c->bank.query_evaluations==UINT64_MAX)return CH_ERR_OVERFLOW;
    ++c->bank.query_evaluations;memset(&c->result,0,sizeof(c->result));
    for(r=0;r<CH_AUG;r++) {
        double residual,abs_row;
        status=residual_row(&c->bank,c->workspace.query.point,r,CH_QUARTIC,&residual,&abs_row);
        if(status)return status;
        if(sum_add(&cost,.5*residual*residual) || sum_add(&absolute,.5*abs_row*abs_row))
            return CH_ERR_NONFINITE;
    }
    c->result.likelihood_cost=sum_value(&cost);c->result.total_cost=sum_value(&cost);
    c->result.cost_absolute_scale=sum_value(&absolute);
    c->result.flags=CH_FLAG_FEASIBLE|CH_FLAG_COST_AVAILABLE;
    status=add_prior(c,c->workspace.query.point,CH_NO_CURVATURE,CH_EXACT_PRIOR,0);
    if(status)return status;
    return ch_endpoint(c);
}

/* All guards below address arithmetic on the computed sketch/prior operands.
 * They are not a bound on omitted model derivatives, libm error, ADC noise or
 * continuous posterior mass. Their counts are fixed before canonical use.
 * Every nonnegative operation in an allowance is rounded outward explicitly.
 */
static double up(double x) { return nextafter(x,INFINITY); }
static double add_up(double a,double b) { return up(a+b); }
static double mul_up(double a,double b) { return up(a*b); }
static double gamma_up(unsigned n)
{
    double nu=(double)n*0x1p-53;
    return up(nu/nextafter(1.-nu,-INFINITY));
}
static double allowance(unsigned n,double scale)
{
    return add_up(mul_up(gamma_up(n),scale),mul_up((double)n,0x0.0000000000001p-1022));
}

static int cholesky_solve(ch_workspace *w)
{
    unsigned i,j,k;ch_sum s;
    for(i=0;i<CH_DIM;i++)for(j=0;j<=i;j++) {
        double value;
        s.sum=w->query.packed[ch_packed_index(i,j)];s.correction=0.;
        for(k=0;k<j;k++)if(sum_add(&s,-w->query.packed[ch_packed_index(i,k)]*
                                      w->query.packed[ch_packed_index(j,k)]))return CH_UNRESOLVED;
        value=sum_value(&s);
        if(i==j) {
            if(!isfinite(value) || !(value>0.))return CH_UNRESOLVED;
            value=sqrt(value);
        } else value/=w->query.packed[ch_packed_index(j,j)];
        if(!isfinite(value))return CH_UNRESOLVED;
        w->query.packed[ch_packed_index(i,j)]=value;
    }
    for(i=0;i<CH_DIM;i++) {
        s.sum=w->query.row_gradient[i];s.correction=0.;
        for(j=0;j<i;j++)if(sum_add(&s,-w->query.packed[ch_packed_index(i,j)]*
                                      w->query.row_gradient[j]))return CH_UNRESOLVED;
        w->query.row_gradient[i]=sum_value(&s)/w->query.packed[ch_packed_index(i,i)];
        if(!isfinite(w->query.row_gradient[i]))return CH_UNRESOLVED;
    }
    for(i=CH_DIM;i-- >0;) {
        s.sum=w->query.row_gradient[i];s.correction=0.;
        for(j=i+1;j<CH_DIM;j++)if(sum_add(&s,-w->query.packed[ch_packed_index(j,i)]*
                                            w->query.row_gradient[j]))return CH_UNRESOLVED;
        w->query.row_gradient[i]=sum_value(&s)/w->query.packed[ch_packed_index(i,i)];
        if(!isfinite(w->query.row_gradient[i]))return CH_UNRESOLVED;
    }
    return CH_OK;
}

/* Reevaluate only the compact metric's directional quadratic after the
 * in-place factorization, so an additional packed matrix is unnecessary.
 * No original model, prior function or observation is reevaluated here.
 * Fixed diagonal prior precision is part of optimizer geometry only.
 */
static int metric_quadratic(const ch_context *c,double *value,double *absolute)
{
    ch_sum total={0,0},scale={0,0};unsigned r,i;
    for(r=0;r<CH_AUG;r++) {
        ch_sum dot={0,0},abs_dot={0,0};
        for(i=0;i<CH_DIM;i++) {
            double product=row_derivative(&c->bank,c->bank.estimate,r,i,CH_QUARTIC)*
                           c->workspace.query.row_gradient[i];
            if(sum_add(&dot,product) || sum_add(&abs_dot,fabs(product)))return CH_ERR_NONFINITE;
        }
        if(sum_add(&total,sum_value(&dot)*sum_value(&dot)) ||
           sum_add(&scale,sum_value(&abs_dot)*sum_value(&abs_dot)))return CH_ERR_NONFINITE;
    }
    for(i=0;i<CH_DIM;i++) {
        double d=c->workspace.query.row_gradient[i],product=precision(i)*d*d;
        if(sum_add(&total,product) || sum_add(&scale,fabs(product)))return CH_ERR_NONFINITE;
    }
    *value=sum_value(&total);*absolute=sum_value(&scale);return CH_OK;
}

static void step_record(ch_context *c,unsigned round,unsigned fraction,
                        double s,double As,double prediction,double Ap,
                        double delta,double Acost,double required,double Acombine,double alpha)
{
    c->result.round=round;c->result.fraction=fraction;
    c->result.detail.step.slope=s;c->result.detail.step.slope_allowance=As;
    c->result.detail.step.model_decrease=prediction;c->result.detail.step.model_allowance=Ap;
    c->result.detail.step.cost_decrease=delta;c->result.detail.step.cost_allowance=Acost;
    c->result.detail.step.armijo_required=required;
    c->result.detail.step.combine_allowance=Acombine;c->result.detail.step.alpha=alpha;
}

int ch_refine(ch_context *c,unsigned max_rounds,ch_trace_callback callback,void *opaque)
{
    unsigned round,i,j,f;int status;
    if(!c || max_rounds==0 || max_rounds>CH_MAX_ROUNDS)return CH_ERR_ARGUMENT;
    if(!c->bank.available)return CH_ERR_UNAVAILABLE;
    for(round=0;round<max_rounds;round++) {
        double base_cost,base_prior,base_abs,max_step=0.,length,cap=1.;
        double s,As,q,Aq,prediction,Ap,scale;ch_sum dot={0,0},abs_dot={0,0};
        int accepted=0;
        if(c->bank.proposal_rounds==UINT64_MAX) {
            c->result.stop_reason=CH_STOP_COUNTER;return CH_UNRESOLVED;
        }
        ++c->bank.proposal_rounds;
        for(i=0;i<CH_DIM;i++)c->workspace.query.point[i]=c->bank.estimate[i];
        status=ch_query(c,CH_QUARTIC,CH_GN,CH_PRIOR_MAJORIZER);
        if(status || (c->result.flags&CH_FLAG_ENDPOINT_INVALID)) {
            c->result.stop_reason=CH_STOP_QUERY;return CH_UNRESOLVED;
        }
        base_cost=c->result.total_cost;base_prior=c->result.prior_cost;
        base_abs=c->result.cost_absolute_scale;
        /* One outer scale product per packed entry preserves exact stored
         * symmetry. No objective scaling, ridge, clipping or PSD repair. */
        for(i=0;i<CH_DIM;i++) {
            for(j=0;j<=i;j++)c->workspace.query.packed[ch_packed_index(i,j)]*=
                ch_public_sd[i]*ch_public_sd[j];
            c->workspace.query.row_gradient[i]=-c->workspace.query.gradient[i]*ch_public_sd[i];
        }
        status=cholesky_solve(&c->workspace);
        if(status){c->result.stop_reason=CH_STOP_METRIC;return CH_UNRESOLVED;}
        for(i=0;i<CH_DIM;i++) {
            max_step=fmax(max_step,fabs(c->workspace.query.row_gradient[i]));
            /* Rounding allowance for represented a + S*u, not support slack
             * relaxation. Raw represented step/support are checked below.
             * Eight epsilon units cover the multiply/add/subtract/divide
             * chain with |a|/S amplification; cap is strictly inward. */
            cap=fmin(cap,nextafter(1.-8.*DBL_EPSILON*
                (1.+fabs(c->bank.estimate[i])/ch_public_sd[i]),0.));
        }
        if(!isfinite(max_step) || !(cap>0.)) {
            c->result.stop_reason=CH_STOP_DIRECTION;return CH_UNRESOLVED;
        }
        length=max_step>cap?cap/max_step:1.;
        for(i=0;i<CH_DIM;i++) {
            double candidate=c->bank.estimate[i]+(length*c->workspace.query.row_gradient[i])*
                             ch_public_sd[i];
            double d=candidate-c->bank.estimate[i],product=c->workspace.query.gradient[i]*d;
            if(!isfinite(candidate) || fabs(d/ch_public_sd[i])>1. ||
               sum_add(&dot,product) || sum_add(&abs_dot,fabs(product))) {
                c->result.stop_reason=CH_STOP_DIRECTION;return CH_UNRESOLVED;
            }
            c->workspace.query.delta[i]=candidate; /* preserve represented full trial */
            c->workspace.query.row_gradient[i]=d;  /* represented original-x direction */
            c->workspace.query.point[i]=candidate;
        }
        s=-sum_value(&dot);As=allowance(256,sum_value(&abs_dot));
        status=metric_quadratic(c,&q,&scale);
        if(status){c->result.stop_reason=CH_STOP_DIRECTION;return CH_UNRESOLVED;}
        Aq=allowance(32768,scale);prediction=s-.5*q;
        Ap=add_up(add_up(As,mul_up(.5,Aq)),allowance(16,fabs(s)+.5*fabs(q)));
        step_record(c,round,UINT32_MAX,s,As,prediction,Ap,0.,0.,0.,0.,1.);
        c->result.flags&=~(CH_FLAG_ACCEPTED|CH_FLAG_DIRECTION_ADMITTED|CH_FLAG_FEASIBLE);
        if(point_support(&c->bank,c->workspace.query.point,NULL)==CH_OK)
            c->result.flags|=CH_FLAG_FEASIBLE;
        if(isfinite(s) && isfinite(As) && isfinite(prediction) && isfinite(Ap) &&
           s>As && prediction>Ap)c->result.flags|=CH_FLAG_DIRECTION_ADMITTED;
        if(callback)callback(c,opaque);
        if(!(c->result.flags&CH_FLAG_DIRECTION_ADMITTED)) {
            c->result.stop_reason=CH_STOP_DIRECTION;return CH_UNRESOLVED;
        }
        for(f=0;f<CH_FRACTIONS;f++) {
            double alpha=ldexp(1.,-(int)f),delta=0.,Acost=0.,required=0.,Acombine=0.;
            for(i=0;i<CH_DIM;i++)c->workspace.query.point[i]=f==0?
                c->workspace.query.delta[i]:c->bank.estimate[i]+alpha*c->workspace.query.row_gradient[i];
            status=point_support(&c->bank,c->workspace.query.point,NULL);
            if(status) {
                memset(&c->result,0,sizeof(c->result));
                step_record(c,round,f,s,As,prediction,Ap,0.,0.,0.,0.,alpha);
                if(callback)callback(c,opaque);
                continue;
            }
            status=cost_query(c);
            if(status) {
                c->result.stop_reason=CH_STOP_QUERY;return CH_UNRESOLVED;
            }
            delta=base_cost-c->result.total_cost;
            Acost=add_up(allowance(16384,add_up(base_abs,c->result.cost_absolute_scale)),
                         allowance(256,add_up(fabs(base_prior),fabs(c->result.prior_cost))));
            Acost=add_up(Acost,allowance(16,add_up(fabs(base_cost),fabs(c->result.total_cost))));
            required=mul_up(.25,mul_up(alpha,add_up(s,As)));
            Acombine=allowance(32,add_up(add_up(fabs(delta),Acost),required));
            step_record(c,round,f,s,As,prediction,Ap,delta,Acost,required,Acombine,alpha);
            if(isfinite(delta) && isfinite(Acost) && isfinite(required) && isfinite(Acombine) &&
               !(c->result.flags&CH_FLAG_ENDPOINT_INVALID) &&
               delta>Acost && delta-Acost>required+Acombine) {
                if(c->bank.accepted_steps==UINT64_MAX) {
                    c->result.stop_reason=CH_STOP_COUNTER;return CH_UNRESOLVED;
                }
                for(i=0;i<CH_DIM;i++)c->bank.estimate[i]=c->workspace.query.point[i];
                ++c->bank.accepted_steps;c->result.flags|=CH_FLAG_ACCEPTED;accepted=1;
            }
            if(callback)callback(c,opaque);
            if(accepted)break;
        }
        if(!accepted){c->result.stop_reason=CH_STOP_NO_TRIAL;return CH_UNRESOLVED;}
    }
    c->result.stop_reason=CH_STOP_ROUND_LIMIT;return CH_UNRESOLVED;
}
