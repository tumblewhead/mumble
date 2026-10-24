/* Host reference estimator, reconstructed and extended for the 35 Hz study.
 * Fixed-temperature electrical specialization, not the complete SCM relation.
 * Variable projection: constrained linear amplitudes and nonlinear outer LM.
 */
#include "scm_estimator.h"
#include "scm_features.h"
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define P SCM_MAX_ALPHA
#define T SCM_MAX_THETA
#define D SCM_MAX_PARAMETERS
#define K (2*P)
#define NC (2*P+2)
#define CMAX (1+P+T+P*T)
#define ANCHORS 5
typedef struct {size_t start,n,offset;scm_feature_basis basis;} word;
struct scm_problem {
    const scm_sample *samples;
    size_t n,m,nwords;
    int modes,nt,na,cd;
    scm_method method;scm_ocv ocv;
    double sigma,*center,*y,*rows;
    word *words;
    double scale[P],lower[P],upper[P],tscale[T],A[NC][P],b[NC];
    int nc;
    double physical_time,charge;
    unsigned excitation;
    int linked_soc;
    double linked_soc_value;
    size_t basis_bytes,setup_peak;
    double basis_seconds,basis_orth,basis_discard;
};
static double clamp(double x,double l,double h){return fmax(l,fmin(h,x));}
static double dot(const double *a,const double *b,int n){double v=0;int i;for(i=0;i<n;i++)v+=a[i]*b[i];return v;}

/* Partial-pivot Gaussian elimination for the small scaled KKT/LM systems. */
static int solve(int n,const double *a,const double *b,double *x){
    double z[K][K+1],largest=0;int i,j,k,p;
    if(n<1||n>K)return -1;
    for(i=0;i<n;i++){for(j=0;j<n;j++){z[i][j]=a[i*n+j];largest=fmax(largest,fabs(z[i][j]));}z[i][n]=b[i];}
    for(k=0;k<n;k++){
        p=k;for(i=k+1;i<n;i++)if(fabs(z[i][k])>fabs(z[p][k]))p=i;
        if(fabs(z[p][k])<1e-14*fmax(largest,1e-100))return -1;
        if(p!=k)for(j=k;j<=n;j++){double t=z[p][j];z[p][j]=z[k][j];z[k][j]=t;}
        for(i=k+1;i<n;i++){double f=z[i][k]/z[k][k];for(j=k;j<=n;j++)z[i][j]-=f*z[k][j];}
    }
    for(i=n-1;i>=0;i--){double v=z[i][n];for(j=i+1;j<n;j++)v-=z[i][j]*x[j];x[i]=v/z[i][i];if(!isfinite(x[i]))return -1;}
    return 0;
}
const char *scm_method_name(scm_method m){return m==SCM_FULL?"full":m==SCM_TANGENT?"tangent":"hybrid";}
void scm_theta_bounds(int n,double *lo,double *hi){
    int i;
    for(i=0;i<n;i++){
        if(n==3){static const double l[3]={.015,.15,1.5},h[3]={.15,1.5,30};lo[i]=log(l[i]);hi[i]=log(h[i]);}
        else {lo[i]=log(i?.8:.015);hi[i]=log(i?180.:30.);}
    }
    lo[n]=lo[n+1]=log(5.);hi[n]=hi[n+1]=log(1200.);
    lo[n+2]=.2;hi[n+2]=.95;lo[n+3]=log(.03);hi[n+3]=log(.10);
}
void scm_default_theta(int n,int s,double *t){
    static const double f[8]={.5,.2,.8,.35,.65,.1,.9,.45};
    static const double gp[8]={150,35,600,300,80,900,450,250};
    static const double gm[8]={300,800,30,500,120,700,200,400};
    static const double z[8]={.68,.50,.85,.75,.60,.90,.80,.65};
    static const double q[8]={.06,.045,.085,.055,.075,.095,.04,.07};
    double lo[T],hi[T];int i;s%=8;scm_theta_bounds(n,lo,hi);
    for(i=0;i<n;i++)t[i]=lo[i]+f[s]*(hi[i]-lo[i]);
    t[n]=log(gp[s]);t[n+1]=log(gm[s]);t[n+2]=z[s];t[n+3]=log(q[s]);
}
void scm_fit_options_default(scm_fit_options *o){if(o){memset(o,0,sizeof(*o));o->starts=4;o->max_iterations=120;}}

static int evaluate_rows(scm_problem *p,const double *theta){
    scm_model_state st;scm_model_row r;size_t i,w=0,k,j;
    if(scm_model_init(&st,p->modes,theta))return -1;
    if(p->method!=SCM_FULL)memset(p->rows,0,p->m*(size_t)p->cd*sizeof(double));
    for(i=0;i<p->n;i++){
        double v[CMAX];int c=0,a,t;
        if(scm_model_step(&st,&p->ocv,p->samples[i].dt,p->samples[i].current,&r))return -1;
        if(p->linked_soc)r.docv[p->modes+3]-=p->charge/exp(theta[p->modes+3])*r.docv[p->modes+2];
        v[c++]=r.ocv-(p->center?p->center[i]:0.);
        for(a=0;a<p->na;a++)v[c++]=r.X[a];
        for(t=0;t<p->nt;t++)v[c++]=r.docv[t];
        for(t=0;t<p->nt;t++)for(a=0;a<p->na;a++)v[c++]=r.dX[t][a];
        if(p->method==SCM_FULL)memcpy(p->rows+i*p->cd,v,p->cd*sizeof(double));
        else {
            word *b;size_t local;
            while(w+1<p->nwords&&i>=p->words[w].start+p->words[w].n)w++;
            b=&p->words[w];local=i-b->start;
            for(j=0;j<b->basis.rank;j++){
                double q=b->basis.q[j*b->n+local],*out=p->rows+(b->offset+j)*p->cd;
                for(k=0;k<(size_t)p->cd;k++)out[k]+=q*v[k];
            }
        }
    }
    return 0;
}

static int make_features(scm_problem *p){
    int anchors=p->method==SCM_TANGENT?1:ANCHORS,a;
    size_t i,j,k,w,cols=(size_t)(1+p->na+p->nt)*anchors;
    size_t frozen=0,base=0,rawbytes=p->n*cols*sizeof(double);
    double *raw=NULL,*column=NULL,theta[T],alpha[P]={0};clock_t begin=clock();
    p->center=malloc(p->n*sizeof(double));raw=calloc(p->n*cols,sizeof(double));column=malloc(p->n*sizeof(double));
    if(!raw||!column||!p->center)goto fail;
    alpha[0]=.12;for(a=0;a<p->modes;a++)alpha[1+a]=.2;
    alpha[1+p->modes]=.025;alpha[2+2*p->modes]=.005;
    for(a=0;a<anchors;a++){
        scm_model_state st;scm_model_row r;double mu,jac[T];size_t off=(size_t)a*(1+p->na+p->nt);
        scm_default_theta(p->modes,a,theta);if(scm_model_init(&st,p->modes,theta))goto fail;
        for(i=0;i<p->n;i++){
            double *v=raw+i*cols+off;
            if(scm_model_step(&st,&p->ocv,p->samples[i].dt,p->samples[i].current,&r))goto fail;
            if(scm_model_predict(&r,p->modes,alpha,&mu,jac))goto fail;
            v[0]=mu;for(k=0;k<(size_t)p->na;k++)v[1+k]=r.X[k];
            for(k=0;k<(size_t)p->nt;k++)v[1+p->na+k]=jac[k]*p->tscale[k];
            if(a==0)p->center[i]=mu;
        }
    }
    p->nwords=1;
    for(i=1;i<p->n;i++)if(p->samples[i].current!=p->samples[i-1].current||p->samples[i].dt!=p->samples[i-1].dt)p->nwords++;
    p->words=calloc(p->nwords,sizeof(word));if(!p->words)goto fail;
    w=0;
    for(i=1;i<p->n;i++)if(p->samples[i].current!=p->samples[i-1].current||p->samples[i].dt!=p->samples[i-1].dt){p->words[w].n=i-p->words[w].start;w++;p->words[w].start=i;}
    p->words[w].n=p->n-p->words[w].start;p->m=0;
    base=sizeof(*p)+p->n*sizeof(scm_sample)+2*p->n*sizeof(double)+rawbytes+p->nwords*sizeof(word);
    for(w=0;w<p->nwords;w++){
        word *b=&p->words[w];size_t cap=(size_t)(anchors*(p->na+p->nt)+anchors),live;
        if(scm_features_init(&b->basis,b->n,cap,1e-9,1e-11))goto fail;
        live=base+frozen+b->basis.allocated_bytes-sizeof(scm_feature_basis);
        if(live>p->setup_peak)p->setup_peak=live;
        for(j=0;j<b->n;j++)column[j]=1.;
        if(scm_features_add(&b->basis,column,1)<0)goto fail;
        for(a=1;a<anchors;a++){
            size_t off=(size_t)a*(1+p->na+p->nt);
            for(j=0;j<b->n;j++)column[j]=raw[(b->start+j)*cols+off]-raw[(b->start+j)*cols];
            if(scm_features_add(&b->basis,column,1)<0)goto fail;
        }
        for(a=0;a<anchors;a++)for(k=1;k<(size_t)(1+p->na+p->nt);k++)if(scm_features_add(&b->basis,raw+b->start*cols+(size_t)a*(1+p->na+p->nt)+k,cols)<0)goto fail;
        b->offset=p->m;p->m+=b->basis.rank;
        p->basis_orth=fmax(p->basis_orth,scm_features_orthogonality_error(&b->basis));
        p->basis_discard=fmax(p->basis_discard,b->basis.max_discarded_norm);
        {
            size_t wanted=b->n*b->basis.rank*sizeof(double);double *q;
            live=base+frozen+b->basis.allocated_bytes-sizeof(scm_feature_basis)+wanted;
            if(live>p->setup_peak)p->setup_peak=live;
            q=realloc(b->basis.q,wanted);if(q){b->basis.q=q;b->basis.capacity=b->basis.rank;}
        }
        free(b->basis.work);b->basis.work=NULL;
        b->basis.allocated_bytes=sizeof(scm_feature_basis)+b->n*b->basis.capacity*sizeof(double);
        frozen+=b->n*b->basis.capacity*sizeof(double);p->basis_bytes+=b->basis.allocated_bytes;
    }
    p->basis_bytes+=p->nwords*(sizeof(word)-sizeof(scm_feature_basis));
    p->y=malloc(p->m*sizeof(double));if(!p->y)goto fail;
    if(base+frozen+p->m*sizeof(double)>p->setup_peak)p->setup_peak=base+frozen+p->m*sizeof(double);
    for(w=0;w<p->nwords;w++){
        word *b=&p->words[w];for(j=0;j<b->n;j++)column[j]=p->samples[b->start+j].voltage-p->center[b->start+j];
        scm_features_project(&b->basis,column,1,p->y+b->offset);
    }
    free(raw);free(column);p->basis_seconds=(double)(clock()-begin)/CLOCKS_PER_SEC;return 0;
fail:free(raw);free(column);return -1;
}

static void constraints(scm_problem *p){
    int i,h=1+p->modes,u=2+2*p->modes;
    memset(p->A,0,sizeof(p->A));p->nc=0;
    for(i=0;i<p->na;i++){
        int c=p->nc++;p->A[c][i]=1;p->b[c]=p->upper[i]/p->scale[i];
        c=p->nc++;p->A[c][i]=-1;p->b[c]=-p->lower[i]/p->scale[i];
    }
    p->A[p->nc][u]=1;p->A[p->nc][h]=-1;p->b[p->nc++]=0;
    p->A[p->nc][u]=-1;p->A[p->nc][h]=-1;p->b[p->nc++]=0;
}
scm_problem *scm_problem_create(const scm_sample *s,size_t n,int modes,double sigma,const scm_ocv *ocv,scm_method method){
    scm_problem *p;size_t i;int j;
    if(!s||!n||n>SIZE_MAX/(CMAX*sizeof(double))||modes<1||modes>SCM_MAX_MODES||!(sigma>0)||!isfinite(sigma)||method<0||method>2)return NULL;
    if(ocv&&scm_ocv_validate(ocv))return NULL;
    p=calloc(1,sizeof(*p));if(!p)return NULL;
    p->samples=s;p->n=p->m=n;p->modes=modes;p->nt=modes+4;p->na=2*modes+3;p->cd=1+p->na+p->nt+p->na*p->nt;p->sigma=sigma;p->method=method;
    if(ocv)p->ocv=*ocv;
    for(i=0;i<n;i++){
        if(!isfinite(s[i].dt)||s[i].dt<0||!isfinite(s[i].current)||!isfinite(s[i].voltage))goto fail;
        p->physical_time+=s[i].dt;p->charge+=s[i].dt*s[i].current/3600.;
        if(s[i].current>0)p->excitation|=1u;
        if(s[i].current<0)p->excitation|=2u;
    }
    for(j=0;j<p->nt;j++)p->tscale[j]=j==modes+2?.1:1.;
    for(j=0;j<p->na;j++){p->scale[j]=j<=modes?.2:.03;p->lower[j]=j<=modes+1?0:-.08;p->upper[j]=j<=modes?1:j==modes+1?.1:.08;}
    p->lower[2+2*modes]=-.1;p->upper[2+2*modes]=.1;constraints(p);
    if(method==SCM_FULL){p->y=malloc(n*sizeof(double));if(!p->y)goto fail;for(i=0;i<n;i++)p->y[i]=s[i].voltage;}
    else if(make_features(p))goto fail;
    p->rows=malloc(p->m*(size_t)p->cd*sizeof(double));if(!p->rows)goto fail;
    return p;
fail:scm_problem_destroy(p);return NULL;
}
void scm_problem_destroy(scm_problem *p){size_t w;if(!p)return;if(p->words)for(w=0;w<p->nwords;w++)scm_features_free(&p->words[w].basis);free(p->words);free(p->center);free(p->y);free(p->rows);free(p);}

static int linear_qp(const scm_problem *p,const double *H,const double *g,double *beta,int *active_out,double *kkt){
    int active[P],nw=0,it,i,j,k,na=p->na;double hs=1;
    for(i=0;i<na;i++)hs=fmax(hs,H[i*na+i]);
    for(i=0;i<na;i++)beta[i]=clamp(beta[i],p->lower[i]/p->scale[i],p->upper[i]/p->scale[i]);
    {
        int h=1+p->modes,u=2+2*p->modes;
        double umax=fmin(p->upper[u]/p->scale[u],p->upper[h]/p->scale[h]);
        double umin=fmax(p->lower[u]/p->scale[u],-p->upper[h]/p->scale[h]);
        if(umin>umax)return -1;
        beta[u]=clamp(beta[u],umin,umax);
        beta[h]=fmax(beta[h],fabs(beta[u]));
        if(beta[h]>p->upper[h]/p->scale[h]+1e-12)return -1;
    }
    for(it=0;it<250;it++){
        double a[K*K]={0},rhs[K]={0},sol[K]={0},grad[P],norm=0,step=1;int dim=na+nw,block=-1;
        for(i=0;i<na;i++){
            grad[i]=(dot(H+i*na,beta,na)+g[i])/hs;rhs[i]=-grad[i];
            for(j=0;j<na;j++)a[i*dim+j]=H[i*na+j]/hs;
            a[i*dim+i]+=1e-12;
        }
        for(k=0;k<nw;k++)for(j=0;j<na;j++)a[j*dim+na+k]=a[(na+k)*dim+j]=p->A[active[k]][j];
        if(solve(dim,a,rhs,sol)){if(nw){nw--;continue;}return -1;}
        for(i=0;i<na;i++)norm=fmax(norm,fabs(sol[i]));
        if(norm<1e-9){
            double minlambda=-1e-9;int remove=-1;
            for(k=0;k<nw;k++)if(sol[na+k]<minlambda){minlambda=sol[na+k];remove=k;}
            if(remove<0){
                double err=0;for(i=0;i<na;i++){double e=grad[i];for(k=0;k<nw;k++)e+=p->A[active[k]][i]*sol[na+k];err=fmax(err,fabs(e));}
                *active_out=nw;*kkt=err;return 0;
            }
            for(k=remove;k+1<nw;k++)active[k]=active[k+1];
            nw--;
            continue;
        }
        for(k=0;k<p->nc;k++){
            double den=dot(p->A[k],sol,na),slack=p->b[k]-dot(p->A[k],beta,na);int present=0;
            for(j=0;j<nw;j++)if(active[j]==k)present=1;
            if(!present&&den>1e-12&&slack/den<step){step=fmax(0.,slack/den);block=k;}
        }
        for(i=0;i<na;i++)beta[i]+=step*sol[i];
        if(block>=0&&nw<na){
            double Q[P][P];int nr=0,independent=0;
            for(k=0;k<=nw;k++){
                double v[P],nn;int idx=k==nw?block:active[k];memcpy(v,p->A[idx],na*sizeof(double));
                for(j=0;j<nr;j++){double d=dot(v,Q[j],na);for(i=0;i<na;i++)v[i]-=d*Q[j][i];}
                nn=sqrt(dot(v,v,na));if(nn>1e-10){for(i=0;i<na;i++)Q[nr][i]=v[i]/nn;nr++;if(k==nw)independent=1;}
            }
            if(independent)active[nw++]=block;
        }
    }
    *active_out=nw;*kkt=1;return -1;
}
static int inner(scm_problem *p,double *alpha,double *H,double *cost,int *active,double *kkt){
    double g[P]={0},beta[P]={0};size_t r;int i,j,na=p->na;
    memset(H,0,na*na*sizeof(double));
    for(r=0;r<p->m;r++){
        const double *v=p->rows+r*p->cd;double d=(v[0]-p->y[r])/p->sigma,x[P];
        for(i=0;i<na;i++)x[i]=v[1+i]*p->scale[i]/p->sigma;
        for(i=0;i<na;i++){g[i]+=x[i]*d;for(j=0;j<=i;j++)H[i*na+j]+=x[i]*x[j];}
    }
    for(i=0;i<na;i++)for(j=0;j<i;j++)H[j*na+i]=H[i*na+j];
    for(i=0;i<na;i++)beta[i]=i<=p->modes?.5:i==1+p->modes?.8:0.;
    if(linear_qp(p,H,g,beta,active,kkt))return -1;
    for(i=0;i<na;i++)alpha[i]=beta[i]*p->scale[i];
    *cost=0;
    for(r=0;r<p->m;r++){const double *v=p->rows+r*p->cd;double d=(v[0]+dot(v+1,alpha,na)-p->y[r])/p->sigma;*cost+=.5*d*d;}
    return isfinite(*cost)?0:-1;
}
static int null_basis(const scm_problem *p,const double *alpha,double Z[P][P]){
    double A[P][P],beta[P];int nr=0,nf=0,i,j,k;
    for(i=0;i<p->na;i++)beta[i]=alpha[i]/p->scale[i];
    for(k=0;k<p->nc;k++)if(p->b[k]-dot(p->A[k],beta,p->na)<1e-7){
        double v[P],n;memcpy(v,p->A[k],p->na*sizeof(double));
        for(j=0;j<nr;j++){double d=dot(v,A[j],p->na);for(i=0;i<p->na;i++)v[i]-=d*A[j][i];}
        n=sqrt(dot(v,v,p->na));if(n>1e-9&&nr<p->na){for(i=0;i<p->na;i++)A[nr][i]=v[i]/n;nr++;}
    }
    for(k=0;k<p->na;k++){
        double v[P]={0},n;v[k]=1;
        for(j=0;j<nr;j++){double d=dot(v,A[j],p->na);for(i=0;i<p->na;i++)v[i]-=d*A[j][i];}
        for(j=0;j<nf;j++){double d=dot(v,Z[j],p->na);for(i=0;i<p->na;i++)v[i]-=d*Z[j][i];}
        n=sqrt(dot(v,v,p->na));if(n>1e-9){for(i=0;i<p->na;i++)Z[nf][i]=v[i]/n;nf++;}
    }
    return nf;
}
static void system_matrix(scm_problem *p,const double *alpha,const double *Haa,double *H,double *g,double *joint){
    double Hta[T*P]={0},Z[P][P],A[P*P]={0},C[T*P]={0};int nt=p->nt,na=p->na,np=nt+na,i,j,a,b,nf;size_t r;
    memset(H,0,nt*nt*sizeof(double));memset(g,0,nt*sizeof(double));
    for(r=0;r<p->m;r++){
        const double *v=p->rows+r*p->cd;double resid=(v[0]+dot(v+1,alpha,na)-p->y[r])/p->sigma,J[T],X[P];
        for(i=0;i<nt;i++)J[i]=(v[1+na+i]+dot(v+1+na+nt+i*na,alpha,na))*p->tscale[i]/p->sigma;
        for(a=0;a<na;a++)X[a]=v[1+a]*p->scale[a]/p->sigma;
        for(i=0;i<nt;i++){g[i]+=J[i]*resid;for(j=0;j<=i;j++)H[i*nt+j]+=J[i]*J[j];for(a=0;a<na;a++)Hta[i*na+a]+=J[i]*X[a];}
    }
    for(i=0;i<nt;i++)for(j=0;j<i;j++)H[j*nt+i]=H[i*nt+j];
    if(joint){
        memset(joint,0,np*np*sizeof(double));
        for(i=0;i<nt;i++)for(j=0;j<nt;j++)joint[i*np+j]=H[i*nt+j];
        for(i=0;i<na;i++)for(j=0;j<na;j++)joint[(nt+i)*np+nt+j]=Haa[i*na+j];
        for(i=0;i<nt;i++)for(j=0;j<na;j++)joint[i*np+nt+j]=joint[(nt+j)*np+i]=Hta[i*na+j];
    }
    nf=null_basis(p,alpha,Z);
    for(a=0;a<nf;a++)for(b=0;b<nf;b++)for(i=0;i<na;i++)for(j=0;j<na;j++)A[a*nf+b]+=Z[a][i]*Haa[i*na+j]*Z[b][j];
    for(i=0;i<nt;i++)for(a=0;a<nf;a++)for(j=0;j<na;j++)C[i*nf+a]+=Hta[i*na+j]*Z[a][j];
    if(nf){double scale=0;for(a=0;a<nf;a++)scale=fmax(scale,A[a*nf+a]);for(a=0;a<nf;a++)A[a*nf+a]+=1e-12*fmax(scale,1.);}
    for(j=0;j<nt&&nf;j++){double x[P]={0};if(!solve(nf,A,C+j*nf,x))for(i=0;i<nt;i++)H[i*nt+j]-=dot(C+i*nf,x,nf);}
    for(i=0;i<nt;i++){H[i*nt+i]=fmax(H[i*nt+i],1e-12);for(j=0;j<i;j++){double v=.5*(H[i*nt+j]+H[j*nt+i]);H[i*nt+j]=H[j*nt+i]=v;}}
}
static double raw_cost(const scm_problem *p,const double *theta,const double *alpha){
    scm_model_state st;scm_model_row r;size_t i;double cost=0,mu;
    if(scm_model_init(&st,p->modes,theta))return INFINITY;
    for(i=0;i<p->n;i++){double d;if(scm_model_step(&st,&p->ocv,p->samples[i].dt,p->samples[i].current,&r))return INFINITY;scm_model_predict(&r,p->modes,alpha,&mu,NULL);d=(mu-p->samples[i].voltage)/p->sigma;cost+=.5*d*d;}
    return cost;
}
static int impose_link(scm_problem *p,double *theta,const double *lo,const double *hi){
    if(p->linked_soc){int z=p->modes+2;theta[z]=p->linked_soc_value+p->charge/exp(theta[p->modes+3]);if(theta[z]<lo[z]||theta[z]>hi[z])return -1;}
    return 0;
}

int scm_fit(scm_problem *p,const scm_fit_options *in,scm_fit_result *out){
    scm_fit_options o;double lo[T],hi[T],savedlo[P],savedhi[P];int s,i,j,nt,na,total=0,evals=0,converged=0,rc=0;double best=INFINITY,maxkkt=0;clock_t begin=clock();
    if(!p||!out)return -1;
    scm_fit_options_default(&o);if(in)o=*in;
    if(o.starts<1||o.starts>100||o.max_iterations<1)return -1;
    nt=p->nt;na=p->na;scm_theta_bounds(p->modes,lo,hi);
    for(i=0;i<nt;i++)if((o.fixed_mask&(1u<<i))&&(!isfinite(o.fixed_theta[i])||o.fixed_theta[i]<lo[i]||o.fixed_theta[i]>hi[i]))return -1;
    for(i=0;i<na;i++)if((o.fixed_alpha_mask&(1u<<i))&&(!isfinite(o.fixed_alpha[i])||o.fixed_alpha[i]<p->lower[i]||o.fixed_alpha[i]>p->upper[i]))return -1;
    if(o.has_current_soc&&(!isfinite(o.current_soc)||o.current_soc<0||o.current_soc>1||(o.fixed_mask&(1u<<(p->modes+2)))))return -1;
    memcpy(savedlo,p->lower,sizeof(savedlo));memcpy(savedhi,p->upper,sizeof(savedhi));
    for(i=0;i<na;i++)if(o.fixed_alpha_mask&(1u<<i))p->lower[i]=p->upper[i]=o.fixed_alpha[i];
    constraints(p);p->linked_soc=o.has_current_soc;p->linked_soc_value=o.current_soc;
    if(p->linked_soc)o.fixed_mask|=1u<<(p->modes+2);
    memset(out,0,sizeof(*out));
    for(s=0;s<o.starts;s++){
        double t[T],alpha[P],Haa[P*P],cost,H[T*T],g[T],lambda=1e-3,pg=INFINITY,kkt=0;int active=0,status=1,reason=2,it=0;
        if(s==0&&o.has_initial)memcpy(t,o.initial_theta,nt*sizeof(double));else scm_default_theta(p->modes,s-(o.has_initial&&s>0),t);
        for(i=0;i<nt;i++){t[i]=clamp(t[i],lo[i],hi[i]);if(o.fixed_mask&(1u<<i))t[i]=o.fixed_theta[i];}
        if(impose_link(p,t,lo,hi))continue;
        evals++;if(evaluate_rows(p,t)||inner(p,alpha,Haa,&cost,&active,&kkt))continue;maxkkt=fmax(maxkkt,kkt);
        for(it=0;it<o.max_iterations;it++){
            double A[T*T],rhs[T],step[T]={0},candidate[T],ca[P],cH[P*P],cc,k2=0,norm=0,pred=0;int active2=0,accepted=0,tries;
            system_matrix(p,alpha,Haa,H,g,NULL);pg=0;
            for(i=0;i<nt;i++){double q=g[i];if((t[i]<=lo[i]+1e-10&&q>0)||(t[i]>=hi[i]-1e-10&&q<0)||(o.fixed_mask&(1u<<i)))q=0;pg=fmax(pg,fabs(q)/sqrt(fmax(H[i*nt+i],1.)));}
            if(pg<2e-6){status=0;reason=0;break;}
            for(tries=0;tries<18;tries++){
                memcpy(A,H,nt*nt*sizeof(double));for(i=0;i<nt;i++){A[i*nt+i]+=lambda*fmax(H[i*nt+i],1.);rhs[i]=-g[i];}
                for(i=0;i<nt;i++)if(o.fixed_mask&(1u<<i)){for(j=0;j<nt;j++)A[i*nt+j]=A[j*nt+i]=0;A[i*nt+i]=1;rhs[i]=0;}
                if(solve(nt,A,rhs,step)){lambda*=10;continue;}
                norm=0;for(i=0;i<nt;i++){candidate[i]=clamp(t[i]+step[i]*p->tscale[i],lo[i],hi[i]);step[i]=(candidate[i]-t[i])/p->tscale[i];norm=fmax(norm,fabs(step[i]));}
                if(impose_link(p,candidate,lo,hi)){lambda*=10;continue;}
                pred=-dot(g,step,nt);for(i=0;i<nt;i++)for(j=0;j<nt;j++)pred-=.5*step[i]*H[i*nt+j]*step[j];
                evals++;
                if(!evaluate_rows(p,candidate)&&!inner(p,ca,cH,&cc,&active2,&k2)&&cc<cost){
                    double improvement=cost-cc,rho=improvement/fmax(pred,1e-30);
                    memcpy(t,candidate,nt*sizeof(double));memcpy(alpha,ca,na*sizeof(double));memcpy(Haa,cH,na*na*sizeof(double));cost=cc;active=active2;
                    maxkkt=fmax(maxkkt,k2);lambda*=rho>.75?.3:rho<.25?2.:1.;lambda=fmax(lambda,1e-12);accepted=1;
                    if((improvement<1e-10*(1+cost)&&norm<1e-5)||norm<1e-9){status=0;reason=1;}
                    break;
                }
                lambda*=10;if(lambda>1e14)break;
            }
            if(!accepted){status=pg<2e-4?0:2;reason=status==0?0:3;break;}
            if(status==0)break;
        }
        total+=it<o.max_iterations?it+1:o.max_iterations;if(status==0)converged++;
        if(cost<best){best=cost;memcpy(out->theta,t,nt*sizeof(double));memcpy(out->alpha,alpha,na*sizeof(double));out->status=status;out->termination_reason=reason;}
    }
    if(!isfinite(best)){rc=-2;goto done;}
    {
        double Haa[P*P],H[T*T],g[T],kkt=0;int active=0;
        evals++;if(evaluate_rows(p,out->theta)||inner(p,out->alpha,Haa,&best,&active,&kkt)){rc=-3;goto done;}
        system_matrix(p,out->alpha,Haa,H,g,out->joint_normal);out->active_linear_constraints=active;maxkkt=fmax(maxkkt,kkt);
        for(i=0;i<nt;i++){double q=g[i];if((out->theta[i]<=lo[i]+1e-10&&q>0)||(out->theta[i]>=hi[i]-1e-10&&q<0)||(o.fixed_mask&(1u<<i)))q=0;out->projected_gradient=fmax(out->projected_gradient,fabs(q)/sqrt(fmax(H[i*nt+i],1.)));}
    }
    out->objective=best;out->objective_full=raw_cost(p,out->theta,out->alpha);out->voltage_rmse=p->sigma*sqrt(2*out->objective_full/p->n);
    out->elapsed_cpu_s=(double)(clock()-begin)/CLOCKS_PER_SEC;out->starts=o.starts;out->converged_starts=converged;out->iterations=total;out->evaluations=evals;out->max_inner_kkt=maxkkt;
    for(i=0;i<nt;i++){if(out->theta[i]-lo[i]<1e-6||hi[i]-out->theta[i]<1e-6)out->active_outer_bounds++;out->coordinate_scales[i]=p->tscale[i];}
    for(i=0;i<na;i++)out->coordinate_scales[nt+i]=p->scale[i];
    if(!(p->excitation&1u))out->unexcited_theta_mask|=1u<<p->modes;
    if(!(p->excitation&2u))out->unexcited_theta_mask|=1u<<(p->modes+1);
    out->elapsed_physical_s=p->physical_time;out->charge_Ah=p->charge;
    out->samples=p->n;out->features=p->m;out->blocks=p->nwords;out->data_bytes=p->n*sizeof(scm_sample);out->basis_bytes=p->basis_bytes;
    out->payload_bytes=p->m*sizeof(double);out->workspace_bytes=p->m*(size_t)p->cd*sizeof(double);
    out->retained_bytes=sizeof(*p)+out->data_bytes+out->basis_bytes+out->payload_bytes+out->workspace_bytes+(p->center?p->n*sizeof(double):0);
    out->setup_peak_bytes=p->setup_peak>out->retained_bytes?p->setup_peak:out->retained_bytes;
    out->basis_seconds=p->basis_seconds;out->basis_max_orthogonality=p->basis_orth;out->max_discarded_column_norm=p->basis_discard;
done:
    memcpy(p->lower,savedlo,sizeof(savedlo));memcpy(p->upper,savedhi,sizeof(savedhi));constraints(p);p->linked_soc=0;
    return rc;
}
