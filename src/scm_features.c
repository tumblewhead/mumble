#include "scm_features.h"
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static double norm(const double *x,size_t n,size_t stride)
{
    size_t i; double scale=0,ssq=1;
    for(i=0;i<n;i++) {
        double a=fabs(x[i*stride]);
        if(!isfinite(a)) return NAN;
        if(a!=0) {
            if(scale<a) {double r=scale/a;ssq=1+ssq*r*r;scale=a;}
            else {double r=a/scale;ssq+=r*r;}
        }
    }
    return scale==0?0:scale*sqrt(ssq);
}
static double dot(const double *x,const double *y,size_t n,size_t stride)
{
    size_t i; double s=0,c=0;
    for(i=0;i<n;i++) {double v=x[i]*y[i*stride]-c,t=s+v;c=(t-s)-v;s=t;}
    return s;
}
int scm_features_init(scm_feature_basis *b,size_t n,size_t cap,double rt,double at)
{
    size_t cells;
    if(!b) return SCM_FEATURES_ERR_ARGUMENT;
    memset(b,0,sizeof(*b));
    if(!n||!cap||!isfinite(rt)||!isfinite(at)||rt<0||at<0)
        return SCM_FEATURES_ERR_ARGUMENT;
    if(cap>n)cap=n;
    if(n>SIZE_MAX/cap||n*cap>SIZE_MAX-n)return SCM_FEATURES_ERR_ARGUMENT;
    cells=n*cap+n;
    if(cells>(SIZE_MAX-sizeof(*b))/sizeof(double))return SCM_FEATURES_ERR_ARGUMENT;
    b->q=(double*)malloc(n*cap*sizeof(double));
    b->work=(double*)malloc(n*sizeof(double));
    if(!b->q||!b->work){free(b->q);free(b->work);memset(b,0,sizeof(*b));return SCM_FEATURES_ERR_ALLOCATION;}
    b->n=n;b->capacity=cap;b->relative_tolerance=rt;b->absolute_tolerance=at;
    b->allocated_bytes=sizeof(*b)+cells*sizeof(double);
    return 0;
}
void scm_features_reset(scm_feature_basis *b)
{
    if(!b)return;
    b->rank=0;b->columns_seen=0;b->columns_rejected=0;
    b->max_discarded_norm=0;b->max_discarded_relative_norm=0;
}
void scm_features_free(scm_feature_basis *b)
{
    if(!b)return;
    free(b->q);free(b->work);memset(b,0,sizeof(*b));
}
int scm_features_add(scm_feature_basis *b,const double *column,size_t stride)
{
    size_t i,j,pass;double original,remainder,threshold;
    if(!b||!column||!stride||!b->n||!b->q||!b->work||b->rank>b->capacity)
        return SCM_FEATURES_ERR_ARGUMENT;
    if(b->n-1>SIZE_MAX/stride)return SCM_FEATURES_ERR_ARGUMENT;
    original=norm(column,b->n,stride);
    if(!isfinite(original))return SCM_FEATURES_ERR_NONFINITE;
    for(i=0;i<b->n;i++)b->work[i]=column[i*stride];
    for(pass=0;pass<2;pass++)for(j=0;j<b->rank;j++) {
        const double *q=b->q+j*b->n;double coefficient=dot(q,b->work,b->n,1);
        if(!isfinite(coefficient))return SCM_FEATURES_ERR_NONFINITE;
        for(i=0;i<b->n;i++)b->work[i]-=coefficient*q[i];
    }
    remainder=norm(b->work,b->n,1);
    if(!isfinite(remainder))return SCM_FEATURES_ERR_NONFINITE;
    threshold=fmax(b->absolute_tolerance,b->relative_tolerance*original);
    if(remainder<=threshold||remainder==0) {
        double r=original>0?remainder/original:0;
        b->columns_seen++;b->columns_rejected++;
        b->max_discarded_norm=fmax(b->max_discarded_norm,remainder);
        b->max_discarded_relative_norm=fmax(b->max_discarded_relative_norm,r);
        return 0;
    }
    if(b->rank>=b->capacity)return SCM_FEATURES_ERR_CAPACITY;
    for(i=0;i<b->n;i++)b->q[b->rank*b->n+i]=b->work[i]/remainder;
    b->rank++;b->columns_seen++;return 1;
}
int scm_features_build(scm_feature_basis *b,const double *a,size_t k,size_t stride)
{
    size_t j;int r;
    if(!b||!b->n||!b->q||(k&&(!a||stride<k)))return SCM_FEATURES_ERR_ARGUMENT;
    scm_features_reset(b);
    for(j=0;j<k;j++){r=scm_features_add(b,a+j,stride);if(r<0){scm_features_reset(b);return r;}}
    return 0;
}
void scm_features_project(const scm_feature_basis *b,const double *x,size_t stride,double *z)
{
    size_t j;for(j=0;j<b->rank;j++)z[j]=dot(b->q+j*b->n,x,b->n,stride);
}
void scm_features_project_matrix(const scm_feature_basis *b,const double *a,size_t k,size_t stride,double *out)
{
    size_t j,c;for(j=0;j<b->rank;j++)for(c=0;c<k;c++)out[j*k+c]=dot(b->q+j*b->n,a+c,b->n,stride);
}
void scm_features_expand(const scm_feature_basis *b,const double *z,double *out)
{
    size_t i,j;for(i=0;i<b->n;i++)out[i]=0;
    for(j=0;j<b->rank;j++)for(i=0;i<b->n;i++)out[i]+=b->q[j*b->n+i]*z[j];
}
size_t scm_features_payload_bytes(const scm_feature_basis *b){return b?b->rank*sizeof(double):0;}
double scm_features_orthogonality_error(const scm_feature_basis *b)
{
    size_t j,k;double maximum=0;
    for(j=0;j<b->rank;j++)for(k=0;k<=j;k++) {
        double v=dot(b->q+j*b->n,b->q+k*b->n,b->n,1)-(j==k?1:0);
        maximum=fmax(maximum,fabs(v));
    }
    return maximum;
}
