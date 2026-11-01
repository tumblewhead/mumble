#include "kernel.h"
#include <math.h>
#include <string.h>
#define MAGIC UINT64_C(0x465454414e473031)
static size_t ix(int i,int j) { return (size_t)(i*17-i*(i-1)/2+j-i); }
static int finite_array(const double *x,size_t n) {
    for(size_t i=0;i<n;i++)if(!isfinite(x[i]))return 0;
    return 1;
}
size_t ft_context_bytes(void) { return sizeof(FTContext); }
size_t ft_work_bytes(void) { return sizeof(FTWork); }
size_t ft_step_work_bytes(void) { return sizeof(FTStepWork); }
int ft_info(const FTContext *c,uint64_t *source,uint64_t *count) {
    if(c->magic!=MAGIC||!finite_array(c->factor,153)||!finite_array(c->anchor,16))return -1;
    *source=c->source;*count=c->count;return 0;
}
static void chart(const double *mean,const double *L,const double *w,double *x) {
    for(int i=0;i<16;i++) { x[i]=mean[i];for(int j=0;j<16;j++)x[i]+=L[16*i+j]*w[j]; }
}
static int basis(FTBasis *b,const double *x,const double *center,const double *half) {
    if(!finite_array(x,16)||!finite_array(center,5)||!finite_array(half,5))return -2;
    for(int i=0;i<11;i++){b->p[i]=exp(x[i+5]);if(!(b->p[i]>0)||!isfinite(b->p[i]))return -2;}
    for(int i=0;i<3;i++)b->gaps[i]=b->p[3+2*i];
    b->p[5]+=b->p[3];b->p[7]+=b->p[5];
    b->h=tanh(x[4]);double e=exp(-2*fabs(x[4]));b->dh=4*e/((1+e)*(1+e));
    for(int i=0;i<5;i++) {
        if(!(center[i]>0)||!(half[i]>0))return -2;
        double s=i<3?b->p[3+2*i]:b->p[9+i-3]/b->p[0];
        double t=log(s/center[i])/half[i];
        if(!isfinite(t)||fabs(t)>1+1e-12)return -3;
        b->T[i][0]=1;b->D[i][0]=0;b->T[i][1]=t;b->D[i][1]=1;
        for(int k=2;k<6;k++) {
            b->T[i][k]=2*t*b->T[i][k-1]-b->T[i][k-2];
            b->D[i][k]=2*b->T[i][k-1]+2*t*b->D[i][k-1]-b->D[i][k-2];
        }
    }
    return 0;
}
/* Direct row contraction with phi and Dphi: never allocate82x16 derivatives. */
static double project(const FTBasis *b,const double *x,const double *half,const double *row,double *g) {
    memset(g,0,16*sizeof(double));
    double q=1/b->p[0],r=row[0]*x[0]+row[1]*q+row[2]*b->p[1]+row[81];
    g[0]=row[0];g[5]=-row[1]*q;g[6]=row[2]*b->p[1];
    for(int i=0;i<3;i++) {
        double v=0,u=0,dv=0,du=0;int start=3+12*i;
        for(int k=0;k<6;k++) {
            v+=row[start+k]*b->T[i][k];u+=row[start+6+k]*b->T[i][k];
            dv+=row[start+k]*b->D[i][k];du+=row[start+6+k]*b->D[i][k];
        }
        double R=b->p[2+2*i];r+=x[1+i]*v+R*u;g[1+i]=v;g[7+2*i]=R*u;
        double slope=(x[1+i]*dv+R*du)/half[i];
        for(int k=0;k<=i;k++)g[8+2*k]+=slope*b->gaps[k]/b->p[3+2*i];
    }
    double a=0,dap=0,dam=0,c=0,dcp=0,dcm=0;int k=0;
    for(int i=0;i<6;i++)for(int j=0;j<6-i;j++,k++) {
        double t=b->T[3][i]*b->T[4][j],dp=b->D[3][i]*b->T[4][j],dm=b->T[3][i]*b->D[4][j];
        a+=row[39+k]*t;dap+=row[39+k]*dp;dam+=row[39+k]*dm;
        c+=row[60+k]*t;dcp+=row[60+k]*dp;dcm+=row[60+k]*dm;
    }
    double H=b->p[8],B=H*b->h,hv=H*a+B*c;
    r+=hv;g[13]=hv;g[4]=H*b->dh*c;
    g[14]=(H*dap+B*dcp)/half[3];g[15]=(H*dam+B*dcm)/half[4];g[5]-=g[14]+g[15];
    return r;
}
static int whiten(FTWork *w,const double *row,const double *half,const double *L) {
    w->bw[16]=project(&w->basis,w->x,half,row,w->gx);
    for(int j=0;j<16;j++){w->bw[j]=0;for(int i=0;i<16;i++)w->bw[j]+=w->gx[i]*L[16*i+j];}
    return finite_array(w->bw,17)?0:-4;
}
static int append(double *R,double *row) {
    for(int i=0;i<17;i++) {
        double a=R[ix(i,i)],b=row[i];if(b==0)continue;
        double h=hypot(a,b);if(!isfinite(h)||!(h>0))return -4;
        double c=a/h,s=b/h;R[ix(i,i)]=h;
        for(int j=i+1;j<17;j++) {double old=R[ix(i,j)];R[ix(i,j)]=c*old+s*row[j];row[j]=-s*old+c*row[j];}
    }
    return finite_array(R,153)?0:-4;
}
int ft_init(FTContext *c,FTWork *w,uint64_t source,uint64_t count,const double *mean,const double *L,const double *anchor,const double *root,const double *center,const double *half) {
    if(!finite_array(mean,16)||!finite_array(L,256)||!finite_array(anchor,16)||!finite_array(root,82*82))return -2;
    chart(mean,L,anchor,w->x);int status=basis(&w->basis,w->x,center,half);if(status)return status;
    memset(w->phase.trial,0,153*sizeof(double));
    for(int i=0;i<16;i++) {memset(w->bw,0,17*sizeof(double));w->bw[i]=1;w->bw[16]=anchor[i];if(append(w->phase.trial,w->bw))return -4;}
    for(int i=0;i<82;i++) {if(whiten(w,root+82*i,half,L)||append(w->phase.trial,w->bw))return -4;}
    memcpy(c->factor,w->phase.trial,sizeof(c->factor));memcpy(c->anchor,anchor,sizeof(c->anchor));
    c->source=source;c->count=count;c->magic=MAGIC;return 0;
}
int ft_update(FTContext *c,FTWork *w,uint64_t source,uint64_t first,const double *rows,size_t n,const double *mean,const double *L,const double *center,const double *half) {
    if(c->magic!=MAGIC||c->source!=source||c->count!=first||n>UINT64_MAX-first)return -1;
    if(n>4096||!finite_array(rows,n*82)||!finite_array(mean,16)||!finite_array(L,256))return -2;
    chart(mean,L,c->anchor,w->x);int status=basis(&w->basis,w->x,center,half);if(status)return status;
    memcpy(w->phase.trial,c->factor,sizeof(c->factor));
    for(size_t i=0;i<n;i++)if(whiten(w,rows+82*i,half,L)||append(w->phase.trial,w->bw))return -4;
    memcpy(c->factor,w->phase.trial,sizeof(c->factor));c->count+=n;return 0;
}
int ft_query(const FTContext *c,FTWork *w,uint64_t count,const double *mean,const double *L,const double *center,const double *half,const double *state,const double *p1,const double *p2,double *out) {
    if(c->magic!=MAGIC||c->count!=count)return -1;
    if(!finite_array(mean,16)||!finite_array(L,256)||!finite_array(state,111)||!finite_array(p1,36)||!finite_array(p2,21*36))return -2;
    double logdet=0,displacement=0;
    for(int i=15;i>=0;i--) {
        double d=c->factor[ix(i,i)];if(!(fabs(d)>0)||!isfinite(d))return -4;
        double s=-c->factor[ix(i,16)];for(int j=i+1;j<16;j++)s-=c->factor[ix(i,j)]*w->delta[j];
        w->delta[i]=s/d;out[i]=c->anchor[i]+w->delta[i];logdet+=2*log(fabs(d));
        displacement+=c->factor[ix(i,16)]*c->factor[ix(i,16)];
    }
    chart(mean,L,out,w->x);int status=basis(&w->basis,w->x,center,half);if(status)return status;
    double q=1/w->basis.p[0];if(w->x[0]-q*state[110]<0||w->x[0]-q*state[109]>1)return -3;
    memcpy(out+16,w->x,16*sizeof(double));memcpy(out+32,w->x,16*sizeof(double));
    double *inverse=w->phase.query.inverse,*origin=w->phase.query.origin;
    memset(inverse,0,256*sizeof(double));
    for(int col=0;col<16;col++)for(int i=15;i>=0;i--) {
        double s=i==col?1.:0.;for(int j=i+1;j<16;j++)s-=c->factor[ix(i,j)]*inverse[16*j+col];
        inverse[16*i+col]=s/c->factor[ix(i,i)];
    }
    for(int i=0;i<16;i++)for(int j=0;j<16;j++) {double s=0;for(int k=0;k<16;k++)s+=L[16*i+k]*inverse[16*k+j];origin[16*i+j]=s;}
    memcpy(out+48,origin,256*sizeof(double));
    for(int dynamic=0;dynamic<5;dynamic++) {
        memset(w->row,0,82*sizeof(double));
        if(dynamic==0){w->row[0]=1;w->row[1]=-state[108];}
        else if(dynamic<4) {
            int i=dynamic-1;
            for(int k=0;k<6;k++)for(int j=0;j<6;j++) {
                w->row[3+12*i+k]+=p1[6*k+j]*state[6*i+j];
                w->row[9+12*i+k]+=p1[6*k+j]*state[18+6*i+j];
            }
        } else for(int k=0;k<21;k++)for(int j=0;j<36;j++) {
            w->row[39+k]+=p2[36*k+j]*state[72+j];w->row[60+k]+=p2[36*k+j]*state[36+j];
        }
        double value=project(&w->basis,w->x,half,w->row,w->gx);
        if(dynamic==4) {
            double H=w->basis.p[8],h=value/H;if(!(h>-1&&h<1))return -3;
            for(int j=0;j<16;j++)w->gx[j]/=H;
            w->gx[13]-=h;
            for(int j=0;j<16;j++)w->gx[j]/=(1-h*h);
            value=atanh(h);
        }
        out[32+dynamic]=value;
        for(int j=0;j<16;j++) {double s=0;for(int k=0;k<16;k++)s+=w->gx[k]*origin[16*k+j];out[48+16*dynamic+j]=s;}
    }
    out[304]=.5*c->factor[ix(16,16)]*c->factor[ix(16,16)];out[305]=logdet;out[306]=sqrt(displacement);
    return finite_array(out,307)?0:-4;
}
int ft_projection(FTWork *w,const double *x,const double *row,const double *center,const double *half,double *out) {
    if(!finite_array(row,82))return -2;
    int status=basis(&w->basis,x,center,half);if(status)return status;
    out[16]=project(&w->basis,x,half,row,out);return finite_array(out,17)?0:-4;
}

/* Same response implementation as the field batch accumulator. Keeping this
 * function in a separate translation unit preserves its arithmetic ordering. */
int response_rows(const double *,size_t,const double *,int,int,const double *,
                  const double *,const double *,double *,double *);
int ft_step(FTContext *c,FTWork *w,FTStepWork *s,uint64_t source,uint64_t first,
            const double *obs,size_t n,uint64_t hz,int query,
            const double *mean,const double *L,const double *center,const double *half,
            const double *cal,const double *rates,const double *p1,const double *p2,double *state) {
    uint64_t actual_source,actual_count;
    if(ft_info(c,&actual_source,&actual_count)||actual_source!=source||actual_count!=first||n>UINT64_MAX-first)return -1;
    if(n<1||n>16||hz<1||hz>INT32_MAX||!finite_array(obs,5*n)||
       !finite_array(mean,16)||!finite_array(L,256)||!finite_array(state,111)||
       !finite_array(cal,14)||!finite_array(rates,30)||!finite_array(p1,36)||!finite_array(p2,756))return -2;
    s->ticks=0;s->query_status=0;
    for(size_t k=0;k<n;k++) {
        const double *o=obs+5*k;
        if(o[0]<0||o[0]>1||fabs(o[1])>.25||o[2]<15||o[2]>35||o[4]<=0)return -2;
        double ticks=nearbyint(o[0]*(double)hz);
        if(fabs(ticks/(double)hz-o[0])>1e-12)return -5;
        s->ticks+=(uint64_t)ticks;
    }
    chart(mean,L,c->anchor,w->x);
    int status=basis(&w->basis,w->x,center,half);if(status)return status;
    memcpy(w->phase.trial,c->factor,sizeof(c->factor));
    memcpy(s->state,state,sizeof(s->state));
    for(size_t k=0;k<n;k++) {
        status=response_rows(obs+5*k,1,cal,6,21,rates,p1,p2,s->state,w->row);
        if(status||!finite_array(w->row,82))return -4;
        if(whiten(w,w->row,half,L)||append(w->phase.trial,w->bw))return -4;
    }
    /* Validation/response/update failures leave both owned objects unchanged.
     * Query failure is different: retain the committed evidence for recovery. */
    memcpy(c->factor,w->phase.trial,sizeof(c->factor));c->count+=n;
    memcpy(state,s->state,sizeof(s->state));
    if(query)s->query_status=ft_query(c,w,c->count,mean,L,center,half,state,p1,p2,s->out);
    return 0;
}
