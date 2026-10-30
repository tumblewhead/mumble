/* Same Foster equations and continuous chart as the frozen model. Structural
 * physical derivatives only; statistical covariance is never sparsified. */
#include "baseline.h"
#include <math.h>
#include <string.h>

int foster_thermal(const double *obs,int n,const double *cal,double *factors) {
    if(n<0||n>FB_BLOCK||cal[0]<=0||cal[2]<=0)return -1;
    for(int i=0;i<n;i++) {
        double T=obs[5*i+2]+273.15;
        if(!isfinite(T)||T<288.15||T>308.15)return -5;
        double d=1./T-1./cal[0];
        for(int k=0;k<11;k++)factors[11*i+k]=exp(cal[k+3]*d);
    }
    return 0;
}
static int predict(const double *x,const double *obs,int n,const double *cal,
                   const double *factors,double *voltage,double *J,double *endpoint,double *F) {
    double state[5],S[5][16]={0},ref[11],gaps[3];
    if(n<0||cal[0]<=0||cal[2]<=0)return -1;
    for(int j=0;j<16;j++)if(!isfinite(x[j]))return -2;
    memcpy(state,x,5*sizeof(double));for(int j=0;j<5;j++)S[j][j]=1.;
    for(int j=0;j<11;j++)ref[j]=exp(x[j+5]);
    for(int k=0;k<3;k++)gaps[k]=ref[3+2*k];
    ref[5]=ref[3]+ref[5];ref[7]=ref[5]+ref[7];
    for(int j=0;j<11;j++)if(!isfinite(ref[j])||ref[j]<=0)return -3;
    if(state[0]<0||state[0]>1||fabs(state[4])>1)return -4;
    for(int i=0;i<n;i++) {
        double dt=obs[5*i],I=obs[5*i+1],T=obs[5*i+2]+273.15;
        double local[11],p[11],d;const double *f;
        if(!isfinite(dt)||dt<0||dt>1||!isfinite(I)||fabs(I)>.25||!isfinite(T)||T<288.15||T>308.15)return -5;
        if(factors)f=factors+11*i;
        else {
            d=1./T-1./cal[0];
            for(int k=0;k<11;k++)local[k]=exp(cal[k+3]*d);
            f=local;
        }
        for(int k=0;k<11;k++)p[k]=ref[k]*f[k];
        if(!(p[3]<p[5]&&p[5]<p[7]))return -6;
        d=I*dt/(3600*p[0]);state[0]-=d;
        /* Keep operation order of nonzero derivatives for close baseline parity. */
        S[0][5]+=d*p[0]/p[0];
        for(int k=0;k<3;k++) {
            int row=k+1,ri=2+2*k,ti=ri+1,rj=ri+5;
            double old=state[row],a=dt/p[ti],e=exp(-a),one=-expm1(-a);
            S[row][row]=e*S[row][row];
            S[row][rj]=e*S[row][rj]+one*I*p[ri];
            for(int g=0;g<=k;g++) {
                int j=8+2*g;double dp=gaps[g]*f[ti],de=e*a*dp/p[ti];
                S[row][j]=e*S[row][j]+de*(old-p[ri]*I);
            }
            state[row]=e*old+one*p[ri]*I;
        }
        if(I!=0.) {
            int gi=I>0?9:10;double sign=I>0?1.:-1.,old=state[4];
            double a=p[gi]*fabs(I)*dt/(3600*p[0]),e=exp(-a);
            S[4][4]=e*S[4][4];
            double de=-e*a*(0./p[gi]-p[0]/p[0]);
            S[4][5]=e*S[4][5]+de*(old-sign);
            for(int j=14;j<=15;j++) {
                de=-e*a*((j==gi+5?p[gi]:0.)/p[gi]-0./p[0]);
                S[4][j]=e*S[4][j]+de*(old-sign);
            }
            state[4]=e*old-expm1(-a)*sign;
        }
        if(state[0]<0||state[0]>1||fabs(state[4])>1)return -7;
        voltage[i]=cal[1]+cal[2]*state[0]+p[8]*state[4]-I*p[1]-state[1]-state[2]-state[3];
        if(!isfinite(voltage[i]))return -8;
        for(int j=0;j<16;j++) {
            J[16*i+j]=cal[2]*S[0][j]+(j==13?p[8]:0.)*state[4]+p[8]*S[4][j]-I*(j==6?p[1]:0.);
            for(int k=1;k<=3;k++)J[16*i+j]-=S[k][j];
            if(!isfinite(J[16*i+j]))return -9;
        }
    }
    memcpy(endpoint,x,16*sizeof(double));memcpy(endpoint,state,5*sizeof(double));
    memset(F,0,256*sizeof(double));
    for(int i=0;i<5;i++)for(int j=0;j<16;j++)F[16*i+j]=S[i][j];
    for(int i=5;i<16;i++)F[16*i+i]=1.;
    return 0;
}
int foster_predict(const double *x,const double *obs,int n,const double *cal,
                   double *voltage,double *J,double *endpoint,double *F) {
    return predict(x,obs,n,cal,0,voltage,J,endpoint,F);
}
int foster_predict_cached(const double *x,const double *obs,int n,const double *cal,
                          const double *factors,double *voltage,double *J,double *endpoint,double *F) {
    /* Cache is caller-owned and must match this observation block and calibration.
     * The rolling adapter always rebuilds it before every attempted retirement. */
    if(n<0||n>FB_BLOCK||(!factors&&n))return -1;
    return predict(x,obs,n,cal,factors,voltage,J,endpoint,F);
}
