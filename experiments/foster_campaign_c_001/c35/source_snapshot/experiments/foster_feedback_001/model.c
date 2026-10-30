/* New user model: +Hh; normalized-throughput, dimensionless gamma.
 * Pure rolling-producer evaluation; no plant truth, fitter, history or RNG. */
#include <math.h>
#include <string.h>
#define D 16

/* x=z,v1,v2,v3,h,logQ,logR0,logR1,logtau1,logR2,loggap2,
 * logR3,loggap3,logH,loggamma+,loggamma-.
 * calibration: TrefK,OCVa,OCVb,11Arrhenius coefficients in physical order.
 * observations columnsdt,I,Tc,V,sigma;V/sigma are not read by this function.
 * J is n x16, endpoint is16, F is16x16. Return nonzero on domain failure. */
int foster_predict(const double x[D],const double *obs,int n,const double cal[14],
                   double *voltage,double *J,double endpoint[D],double F[D*D]) {
    double state[5],S[5][D],ref[11],der[11][D];int i,j,k;
    if(n<0 || cal[0]<=0 || cal[2]<=0)return -1;
    for(j=0;j<D;j++)if(!isfinite(x[j]))return -2;
    memcpy(state,x,5*sizeof(double));memset(S,0,sizeof(S));memset(der,0,sizeof(der));
    for(j=0;j<5;j++)S[j][j]=1.;
    for(j=0;j<11;j++){ref[j]=exp(x[j+5]);der[j][j+5]=ref[j];}
    /* Replace gap coordinates with cumulative ordered time constants. */
    ref[5]=ref[3]+ref[5];ref[7]=ref[5]+ref[7];
    for(j=0;j<D;j++){der[5][j]+=der[3][j];der[7][j]+=der[5][j];}
    for(j=0;j<11;j++)if(!isfinite(ref[j]) || ref[j]<=0)return -3;
    if(state[0]<0 || state[0]>1 || fabs(state[4])>1)return -4;
    for(i=0;i<n;i++) {
        double dt=obs[5*i],I=obs[5*i+1],T=obs[5*i+2]+273.15;
        double p[11],dp[11][D],d;
        if(!isfinite(dt)||dt<0||dt>1||!isfinite(I)||fabs(I)>.25||T<288.15||T>308.15)return -5;
        d=1./T-1./cal[0];
        for(k=0;k<11;k++) {
            double f=exp(cal[k+3]*d);p[k]=ref[k]*f;
            for(j=0;j<D;j++)dp[k][j]=der[k][j]*f;
        }
        if(!(p[3]<p[5] && p[5]<p[7]))return -6;
        d=I*dt/(3600*p[0]);state[0]-=d;
        for(j=0;j<D;j++)S[0][j]+=d*dp[0][j]/p[0];
        for(k=0;k<3;k++) {
            int ri=2+2*k,ti=ri+1;double old=state[k+1],a=dt/p[ti],e=exp(-a),one=-expm1(-a);
            for(j=0;j<D;j++) {
                double de=e*a*dp[ti][j]/p[ti];
                S[k+1][j]=e*S[k+1][j]+de*(old-p[ri]*I)+one*I*dp[ri][j];
            }
            state[k+1]=e*old+one*p[ri]*I;
        }
        if(I!=0.) {
            int gi=I>0?9:10;double sign=I>0?1.:-1.,old=state[4];
            double a=p[gi]*fabs(I)*dt/(3600*p[0]),e=exp(-a);
            for(j=0;j<D;j++) {
                double de=-e*a*(dp[gi][j]/p[gi]-dp[0][j]/p[0]);
                S[4][j]=e*S[4][j]+de*(old-sign);
            }
            state[4]=e*old-expm1(-a)*sign;
        }
        if(state[0]<0||state[0]>1||fabs(state[4])>1)return -7;
        voltage[i]=cal[1]+cal[2]*state[0]+p[8]*state[4]-I*p[1]-state[1]-state[2]-state[3];
        if(!isfinite(voltage[i]))return -8;
        for(j=0;j<D;j++) {
            J[i*D+j]=cal[2]*S[0][j]+dp[8][j]*state[4]+p[8]*S[4][j]-I*dp[1][j];
            for(k=1;k<=3;k++)J[i*D+j]-=S[k][j];
            if(!isfinite(J[i*D+j]))return -9;
        }
    }
    memcpy(endpoint,x,D*sizeof(double));memcpy(endpoint,state,5*sizeof(double));
    memset(F,0,D*D*sizeof(double));
    for(i=0;i<5;i++)for(j=0;j<D;j++)F[i*D+j]=S[i][j];
    for(i=5;i<D;i++)F[i*D+i]=1.;
    return 0;
}
