#include "baseline.h"
#include <math.h>
/* Deliberately ordinary dense implementations, no jitter or rank truncation. */
int fb_solve(double a[256],double b[16]) {
    int i,j,k,p;
    for(k=0;k<16;k++) {
        p=k; for(i=k+1;i<16;i++) if(fabs(a[i*16+k])>fabs(a[p*16+k]))p=i;
        if(!isfinite(a[p*16+k]) || a[p*16+k]==0)return FB_NUMERIC;
        if(p!=k) { for(j=0;j<16;j++){double t=a[k*16+j];a[k*16+j]=a[p*16+j];a[p*16+j]=t;}
            double t=b[k];b[k]=b[p];b[p]=t; }
        for(i=k+1;i<16;i++) {
            double f=a[i*16+k]/a[k*16+k];a[i*16+k]=0;
            for(j=k+1;j<16;j++)a[i*16+j]-=f*a[k*16+j];
            b[i]-=f*b[k];
        }
    }
    for(i=15;i>=0;i--){for(j=i+1;j<16;j++)b[i]-=a[i*16+j]*b[j];b[i]/=a[i*16+i];if(!isfinite(b[i]))return FB_NUMERIC;}
    return FB_OK;
}
int fb_cholesky(double a[256]) {
    int i,j,k;
    for(i=0;i<16;i++) {
        for(j=0;j<=i;j++) {
            double s=a[i*16+j];for(k=0;k<j;k++)s-=a[i*16+k]*a[j*16+k];
            if(j==i){if(!(s>0)||!isfinite(s))return FB_NUMERIC;a[i*16+j]=sqrt(s);}
            else a[i*16+j]=s/a[j*16+j];
        }
        for(j=i+1;j<16;j++)a[i*16+j]=0;
    }
    return FB_OK;
}
int fb_qr(double a[289]) {
    int i,j,k;
    for(k=0;k<17;k++) {
        double norm=0,alpha=a[k*17+k],beta,tau;
        for(i=k+1;i<17;i++)norm=hypot(norm,a[i*17+k]);
        if(norm==0)continue;
        beta=-copysign(hypot(alpha,norm),alpha);tau=(beta-alpha)/beta;
        for(i=k+1;i<17;i++)a[i*17+k]/=(alpha-beta);
        for(j=k+1;j<17;j++) {
            double dot=a[k*17+j];for(i=k+1;i<17;i++)dot+=a[i*17+k]*a[i*17+j];dot*=tau;
            a[k*17+j]-=dot;for(i=k+1;i<17;i++)a[i*17+j]-=a[i*17+k]*dot;
        }
        a[k*17+k]=beta;for(i=k+1;i<17;i++)a[i*17+k]=0;
    }
    for(i=0;i<289;i++)if(!isfinite(a[i]))return FB_NUMERIC;
    return FB_OK;
}
