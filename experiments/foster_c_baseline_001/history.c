/* Generic likelihood encoding/conditioning. No plant, load or aging rule. */
#include "baseline.h"
#include <math.h>
#include <string.h>
#include <float.h>
_Static_assert(sizeof(double)==8 && sizeof(float)==4 && DBL_MANT_DIG==53 && FLT_MANT_DIG==24,"IEEE binary32/64 required");
static void put(unsigned char **p,double v,int width) {
    uint64_t u=0;
    if(width==8)memcpy(&u,&v,8);
    else {float f=(float)v;uint32_t s;memcpy(&s,&f,4);u=s;}
    for(int i=0;i<width;i++){*(*p)++=(unsigned char)(u&255);u>>=8;}
}
static double get(const unsigned char **p,int width) {
    uint64_t u=0;for(int i=0;i<width;i++)u|=(uint64_t)*(*p)++<<(8*i);
    if(width==8){double v;memcpy(&v,&u,8);return v;}
    uint32_t s=(uint32_t)u;float f;memcpy(&f,&s,4);return f;
}
int fb_token(const double anchor[16],const FBPhysical *ph,const double *obs,int n,int encoding,unsigned char *token) {
    double a[289]={0},c=0;unsigned char *p=token;int i,j,width;
    if(n<1||n>16||(encoding!=4&&encoding!=8))return FB_INPUT;
    width=encoding;*p++=(unsigned char)(width==8?'8':'4');
    for(i=0;i<n;i++) {
        if(!(obs[5*i+4]>0)||!isfinite(obs[5*i+4]))return FB_INPUT;
        for(j=0;j<16;j++)a[i*17+j]=ph->J[i*16+j]/obs[5*i+4];
        a[i*17+16]=(ph->v[i]-obs[5*i+3])/obs[5*i+4];
        c+=log(obs[5*i+4]);
    }
    c+=n*.5*log(2*3.14159265358979323846);
    if(fb_qr(a))return FB_NUMERIC;
    for(i=0;i<16;i++) {if(!isfinite(anchor[i]))return FB_NUMERIC;put(&p,anchor[i],8);}
    for(i=0;i<16;i++) {if(!isfinite(ph->end[i]))return FB_NUMERIC;put(&p,ph->end[i],8);}
    if(!isfinite(c))return FB_NUMERIC;
    put(&p,c,8);
    for(i=0;i<17;i++)for(j=i;j<17;j++) {
        if(width==4&&fabs(a[i*17+j])>FLT_MAX)return FB_NUMERIC;
        put(&p,a[i*17+j],width);
    }
    for(i=0;i<256;i++) {
        if(!isfinite(ph->F[i])||(width==4&&fabs(ph->F[i])>FLT_MAX))return FB_NUMERIC;
        put(&p,ph->F[i],width);
    }
    return (int)(p-token);
}
int fb_history(const FBMessage *in,const unsigned char *token,size_t length,FBMessage *out) {
    double anchor[16],end[16],F[256],a[289]={0},B[272],C[256],r[17],w[16],m[16],root[256],c,inc=0;
    const unsigned char *p=token;int i,j,k,width;
    if(length<1||(*p!='4'&&*p!='8'))return FB_FORMAT;
    width=*p++=='8'?8:4;if(length!=(size_t)(265+409*width))return FB_FORMAT;
    for(i=0;i<16;i++){anchor[i]=get(&p,8);if(!isfinite(anchor[i])||!isfinite(in->mean[i]))return FB_NUMERIC;}
    for(i=0;i<16;i++){end[i]=get(&p,8);if(!isfinite(end[i]))return FB_NUMERIC;}
    c=get(&p,8);if(!isfinite(c)||!isfinite(in->logZ))return FB_NUMERIC;
    for(i=0;i<17;i++)for(j=i;j<17;j++){a[i*17+j]=get(&p,width);if(!isfinite(a[i*17+j]))return FB_NUMERIC;}
    for(i=0;i<256;i++){F[i]=get(&p,width);if(!isfinite(F[i])||!isfinite(in->root[i]))return FB_NUMERIC;}
    for(i=0;i<17;i++) {
        r[i]=a[i*17+16];for(k=0;k<16;k++)r[i]+=a[i*17+k]*(in->mean[k]-anchor[k]);
        for(j=0;j<16;j++){double s=0;for(k=0;k<16;k++)s+=a[i*17+k]*in->root[k*16+j];B[i*16+j]=s;}
    }
    for(i=0;i<16;i++) {
        w[i]=0;for(k=0;k<17;k++)w[i]-=B[k*16+i]*r[k];
        for(j=0;j<16;j++){double s=i==j?1.:0.;for(k=0;k<17;k++)s+=B[k*16+i]*B[k*16+j];C[i*16+j]=s;}
    }
    if(fb_cholesky(C))return FB_NUMERIC;
    for(i=0;i<16;i++){for(k=0;k<i;k++)w[i]-=C[i*16+k]*w[k];w[i]/=C[i*16+i];}
    for(i=15;i>=0;i--){for(k=i+1;k<16;k++)w[i]-=C[k*16+i]*w[k];w[i]/=C[i*16+i];}
    for(i=0;i<16;i++) {
        m[i]=in->mean[i];for(k=0;k<16;k++)m[i]+=in->root[i*16+k]*w[k];
        for(j=0;j<16;j++){double s=in->root[i*16+j];for(k=0;k<j;k++)s-=C[j*16+k]*root[i*16+k];root[i*16+j]=s/C[j*16+j];}
        inc+=w[i]*w[i]+2*log(C[i*16+i]);
    }
    for(i=0;i<17;i++){double s=r[i];for(k=0;k<16;k++)s+=B[i*16+k]*w[k];inc+=s*s;}
    for(i=0;i<16;i++) {
        out->mean[i]=end[i];for(k=0;k<16;k++)out->mean[i]+=F[i*16+k]*(m[k]-anchor[k]);
        if(!isfinite(out->mean[i]))return FB_NUMERIC;
        for(j=0;j<16;j++){double s=0;for(k=0;k<16;k++)s+=F[i*16+k]*root[k*16+j];out->root[i*16+j]=s;if(!isfinite(s))return FB_NUMERIC;}
    }
    out->logZ=in->logZ-c-.5*inc;return isfinite(out->logZ)?FB_OK:FB_NUMERIC;
}
