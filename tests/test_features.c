/* Reconstructed tests: exercise representation consequences, not old receipts. */
#include "scm_features.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static int failures,checks;
static double max_ratio_error;
#define CHECK(c,m) do {checks++;if(!(c)){fprintf(stderr,"FAIL %s\n",m);failures++;}}while(0)
static double dot(const double *a,const double *b,size_t n)
{size_t i;double s=0;for(i=0;i<n;i++)s+=a[i]*b[i];return s;}
static void ratios(void)
{
    enum {N=96,K=4,C=4};
    scm_feature_basis b;double columns[N*K],d[C][N],y[N],z[K],zd[C][K],zm[K*K],zc[K],res[N];
    size_t i,j,k;double sigma2=1e-6,common;
    CHECK(scm_features_init(&b,N,K,1e-12,1e-15)==0,"init");
    for(i=0;i<N;i++) {
        double t=(double)i/(N-1),u=exp(-2.3*t),v=exp(-9.7*t);
        d[0][i]=0;d[1][i]=.00012*u;d[2][i]=-.0014*u+.0031*v;d[3][i]=.0021*u+.0009*v;
        y[i]=d[2][i]+.001*(.4*sin(53*t)+.2*cos(19*t));
        columns[i*K]=d[1][i];columns[i*K+1]=d[2][i];columns[i*K+2]=d[3][i];columns[i*K+3]=t*t;
    }
    CHECK(scm_features_build(&b,columns,K,K)==0,"build");
    CHECK(b.rank==3,"secants plus independent tangent rank");
    CHECK(scm_features_orthogonality_error(&b)<1e-13,"orthogonality");
    scm_features_project(&b,y,1,z);
    for(j=0;j<C;j++)scm_features_project(&b,d[j],1,zd[j]);
    for(j=0;j<C;j++)for(k=0;k<C;k++) {
        double full=(dot(d[j],y,N)-dot(d[k],y,N)-.5*(dot(d[j],d[j],N)-dot(d[k],d[k],N)))/sigma2;
        double compressed=(dot(zd[j],z,b.rank)-dot(zd[k],z,b.rank)-.5*(dot(zd[j],zd[j],b.rank)-dot(zd[k],zd[k],b.rank)))/sigma2;
        double error=fabs(full-compressed);max_ratio_error=fmax(max_ratio_error,error);
        CHECK(error<1e-9,"finite-family log likelihood ratios");
    }
    common=dot(y,y,N)-dot(z,z,b.rank);
    CHECK(common>0,"nonzero discarded common residual");
    for(j=0;j<C;j++) {
        double full=0,compressed=0;
        for(i=0;i<N;i++)full+=(y[i]-d[j][i])*(y[i]-d[j][i]);
        for(i=0;i<b.rank;i++)compressed+=(z[i]-zd[j][i])*(z[i]-zd[j][i]);
        CHECK(fabs(full-compressed-common)<1e-14,"common residual restores absolute objective");
    }
    scm_features_project_matrix(&b,columns,K,K,zm);
    for(j=0;j<K;j++){scm_features_project(&b,columns+j,K,zc);for(k=0;k<b.rank;k++)CHECK(fabs(zc[k]-zm[k*K+j])<1e-15,"strided projection");}
    scm_features_expand(&b,z,res);for(i=0;i<N;i++)res[i]=y[i]-res[i];
    CHECK(fabs(dot(res,res,N)-common)<1e-14,"residual energy");
    CHECK(scm_features_payload_bytes(&b)==b.rank*sizeof(double),"payload bytes");
    CHECK(b.allocated_bytes==sizeof(b)+N*(K+1)*sizeof(double),"basis allocation bytes");
    scm_features_free(&b);
}
static double repeat(size_t n)
{
    scm_feature_basis b;double *x=malloc(n*sizeof(double)),*y=malloc(n*sizeof(double)),z,d;size_t i;
    CHECK(x&&y,"repeat buffers");if(!x||!y)exit(2);
    CHECK(scm_features_init(&b,n,1,1e-12,0)==0,"repeat init");
    for(i=0;i<n;i++){x[i]=.002;y[i]=.003;}
    CHECK(scm_features_add(&b,x,1)==1,"repeat basis");
    scm_features_project(&b,x,1,&d);scm_features_project(&b,y,1,&z);
    CHECK(fabs(z-.003*sqrt((double)n))<1e-13,"projection retains sample count");
    scm_features_free(&b);free(x);free(y);return(d*z-.5*d*d)/1e-6;
}
static void errors(void)
{
    scm_feature_basis b;double u[]={1,0,0},almost[]={1,1e-12,0},v[]={0,1,0},invalid[]={0,NAN,0},a[]={1,0,0,1,0,0};
    CHECK(scm_features_init(&b,3,1,1e-10,1e-15)==0,"error init");
    CHECK(scm_features_add(&b,u,1)==1,"first direction");
    CHECK(scm_features_add(&b,almost,1)==0,"declared dependence tolerance");
    CHECK(fabs(b.max_discarded_norm-1e-12)<1e-25,"discarded norm");
    CHECK(scm_features_add(&b,v,1)==SCM_FEATURES_ERR_CAPACITY,"explicit capacity error");
    CHECK(b.rank==1,"add preserves prior basis");
    CHECK(scm_features_add(&b,invalid,1)==SCM_FEATURES_ERR_NONFINITE,"reject NaN");
    CHECK(scm_features_build(&b,a,2,2)==SCM_FEATURES_ERR_CAPACITY,"build propagates capacity error");
    CHECK(b.rank==0,"partial build reset");scm_features_free(&b);
    CHECK(scm_features_init(&b,0,1,0,0)==SCM_FEATURES_ERR_ARGUMENT,"zero rows rejected");scm_features_free(&b);
    CHECK(scm_features_init(&b,SIZE_MAX,SIZE_MAX,0,0)==SCM_FEATURES_ERR_ARGUMENT,"allocation overflow rejected");scm_features_free(&b);
}
int main(void)
{
    double a,b;ratios();errors();a=repeat(5);b=repeat(500);
    CHECK(fabs(b/a-100)<1e-10,"independent repeated evidence precision");
    printf("{\"test\":\"features_reconstructed\",\"checks\":%d,\"failures\":%d,\"max_pair_log_likelihood_ratio_error\":%.17g,\"repetition_count_ratio\":%.17g}\n",checks,failures,max_ratio_error,b/a);
    return failures?1:0;
}
