/* Same Foster physics, with eta=atanh(h) as the hysteresis coordinate.
 * Joint covariance is retained. No clipping or evidence-dependent forgetting. */
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
    if(state[0]<0||state[0]>1||!isfinite(state[4]))return -4;
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
        if(I!=0. && dt!=0.) {
            int gi=I>0?9:10;double sign=I>0?1.:-1.;
            double a=p[gi]*fabs(I)*dt/(3600*p[0]);
            /* q=(1-sign*h)/2, q_next=q*exp(-a). Work in log(q):
             * this avoids atanh(tanh(eta)) at saturated physical h. */
            double t=2.*sign*state[4];
            double logq=-(fmax(t,0.)+log1p(exp(-fabs(t))));
            double lognext=logq-a,denom=-expm1(lognext);
            double sigmoid=t>=0.?1./(1.+exp(-t)):exp(t)/(1.+exp(t));
            double derivative=sigmoid/denom,da=sign*.5*a/denom;
            if(!isfinite(lognext)||!(denom>0.))return -8;
            S[4][4]*=derivative;
            S[4][5]=derivative*S[4][5]-da;
            for(int j=14;j<=15;j++)S[4][j]=derivative*S[4][j]+(j==gi+5?da:0.);
            state[4]=sign*.5*(log(denom)-lognext);
        }
        if(state[0]<0||state[0]>1||!isfinite(state[4]))return -7;
        double h=tanh(state[4]),eeta=exp(-2.*fabs(state[4]));
        double dh=4.*eeta/((1.+eeta)*(1.+eeta));
        voltage[i]=cal[1]+cal[2]*state[0]+p[8]*h-I*p[1]-state[1]-state[2]-state[3];
        if(!isfinite(voltage[i]))return -8;
        for(int j=0;j<16;j++) {
            J[16*i+j]=cal[2]*S[0][j]+(j==13?p[8]:0.)*h+p[8]*dh*S[4][j]-I*(j==6?p[1]:0.);
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
