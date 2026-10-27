#include "features.h"
#include <math.h>
#include <stdint.h>

/* amp: physical coordinate,17=H*h0,16=unit. a/b: seven nonlinear coordinates.
 * All amplitude scales are fixed public scales, never fitted-center values. */
typedef struct { unsigned char amp,degree,a,b; } term;
static const term terms[37]={
 {7,2,0,0},{12,2,0,0},{8,2,1,1},{13,2,1,1},{9,2,2,2},{14,2,2,2},
 {10,2,3,3},{10,2,3,4},{10,2,4,4},{17,2,3,3},{17,2,3,4},{17,2,4,4},
 {16,2,5,5},{16,2,5,6},{16,2,6,6},
 {7,1,0,0},{12,1,0,0},{8,1,1,1},{13,1,1,1},{9,1,2,2},{14,1,2,2},
 {10,1,3,3},{10,1,4,4},{17,1,3,3},{17,1,4,4},{16,1,5,5},{16,1,6,6},
 {7,0,0,0},{12,0,0,0},{8,0,0,0},{13,0,0,0},{9,0,0,0},{14,0,0,0},
 {10,0,0,0},{17,0,0,0},{6,0,0,0},{16,0,0,0}
};
size_t sh_index(unsigned r,unsigned c) { return (size_t)r*37-(size_t)r*(r-1)/2+c-r; }
static double coordinate(const double *o,const double *x,unsigned i)
{
    if(i<5)return (x[i]-o[i])/ch_public_sd[i];
    if(i==5)return (x[11]-o[11])/ch_public_sd[11];
    return (exp(-x[5])-exp(-o[5]))/SH_INVERSE_Q_SD;
}
static double tangent(const double *x,unsigned i,unsigned j)
{
    if(i<5)return j==i?1./ch_public_sd[i]:0.;
    if(i==5)return j==11?1./ch_public_sd[11]:0.;
    return j==5?-exp(-x[5])/SH_INVERSE_Q_SD:0.;
}
static double amplitude(const double *x,unsigned i)
{
    if(i==16)return 1.;
    if(i==17)return x[10]*x[15]/SH_U_SD;
    return x[i]/ch_public_sd[i];
}
static double amplitude_tangent(const double *x,unsigned i,unsigned j)
{
    if(i==16)return 0.;
    if(i==17)return j==10?x[15]/SH_U_SD:j==15?x[10]/SH_U_SD:0.;
    return i==j?1./ch_public_sd[i]:0.;
}
double sh_feature(const double *o,const double *x,unsigned k)
{
    const term *t;
    if(!o || !x || k>=37)return NAN;
    t=terms+k;
    if(!t->degree)return amplitude(x,t->amp);
    if(t->degree==1)return amplitude(x,t->amp)*coordinate(o,x,t->a);
    return amplitude(x,t->amp)*coordinate(o,x,t->a)*coordinate(o,x,t->b);
}
double sh_feature_derivative(const double *o,const double *x,unsigned k,unsigned j)
{
    const term *t;double da,db,a,b,amp,damp;
    if(!o || !x || k>=37 || j>=16)return NAN;
    t=terms+k;damp=amplitude_tangent(x,t->amp,j);
    if(!t->degree)return damp;
    da=tangent(x,t->a,j);db=tangent(x,t->b,j);
    if(damp==0. && da==0. && db==0.)return 0.;
    amp=amplitude(x,t->amp);a=coordinate(o,x,t->a);
    if(t->degree==1)return damp*a+amp*da;
    b=coordinate(o,x,t->b);return damp*a*b+amp*(da*b+a*db);
}
int sh_shift(const double *o,const double *x,double s[7])
{
    unsigned i;if(!o || !x || !s)return CH_ERR_ARGUMENT;
    for(i=0;i<7;i++){s[i]=coordinate(o,x,i);if(!isfinite(s[i]))return CH_ERR_NONFINITE;}
    return CH_OK;
}
typedef struct { double value,correction; } sum;
static int add(sum *s,double v)
{
    double n=s->value+v;
    if(!isfinite(v) || !isfinite(n))return CH_ERR_NONFINITE;
    s->correction+=fabs(s->value)>=fabs(v)?(s->value-n)+v:(v-n)+s->value;s->value=n;
    return isfinite(s->correction) && isfinite(s->value+s->correction)?0:CH_ERR_NONFINITE;
}
static int translated(const double *r,const double *s,unsigned row,unsigned col,double *out)
{
    unsigned k;sum v={0,0};const term *t=terms+col;
    if(add(&v,r[sh_index(row,col)]))return CH_ERR_NONFINITE;
    for(k=row;k<27;k++) {
        const term *q=terms+k;double c;
        if(q->amp!=t->amp || q->degree<=t->degree)continue;
        c=r[sh_index(row,k)];
        if(t->degree==0) {
            if(add(&v,c*s[q->a]*(q->degree==2?s[q->b]:1.)))return CH_ERR_NONFINITE;
        } else {
            if(q->a==t->a && add(&v,c*s[q->b]))return CH_ERR_NONFINITE;
            if(q->b==t->a && add(&v,c*s[q->a]))return CH_ERR_NONFINITE;
        }
    }
    *out=v.value+v.correction;return CH_OK;
}
static int pass(double *r,const double *s,int mutate)
{
    unsigned row,col;double v;
    for(row=0;row<37;row++) {
        for(col=row>27?row:27;col<37;col++) {
            if(translated(r,s,row,col,&v))return CH_ERR_NONFINITE;
            if(mutate)r[sh_index(row,col)]=v;
        }
        for(col=row>15?row:15;col<27;col++) {
            if(translated(r,s,row,col,&v))return CH_ERR_NONFINITE;
            if(mutate)r[sh_index(row,col)]=v;
        }
    }
    return CH_OK;
}
int sh_translate(double r[703],const double s[7])
{
    unsigned i;uintptr_t a=(uintptr_t)r,b=(uintptr_t)s;
    if(!r || !s)return CH_ERR_ARGUMENT;
    if(a<=b?b-a<703*sizeof(double):a-b<7*sizeof(double))return CH_ERR_ARGUMENT;
    for(i=0;i<703;i++)if(!isfinite(r[i]))return CH_ERR_NONFINITE;
    for(i=0;i<7;i++)if(!isfinite(s[i]))return CH_ERR_NONFINITE;
    if(pass(r,s,0))return CH_ERR_NONFINITE;
    return pass(r,s,1);
}
