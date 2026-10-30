/* Desktop-only exact-prefix likelihood. Caller owns ordered decoded history.
 * No saved estimates, compact bank, truth, prior or observation weights enter. */
#include "../../include/scm_model.h"
#include "../live_anchor_integration_001/host_input.h"
#include "../compact_nonlinear_history_001/compact_history.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

int desktop_decode(const unsigned char *bytes,uint64_t first,size_t n,double *out)
{
    size_t i;hp_observation o;hp_quantization_error e;
    adc12_raw_sample raw;adc12_reading d;
    for(i=0;i<n;i++) {
        if(hp_decode_record(bytes+32*i,&o) || hp_encode(first+i,&o,&raw,&e) ||
           adc12_convert(&raw,&hp_fixture_calibration,&d))return -1;
        out[3*i]=d.dt_s;out[3*i+1]=d.current_A;out[3*i+2]=d.voltage_V;
    }
    return 0;
}
int desktop_eval(const double *samples,size_t n,const double *x,int derivatives,
                 double *cost,double *gradient,double *metric,double *endpoint)
{
    scm_model_state m;scm_model_row row;double theta[7],alpha[9],jac[7],g[16];
    double sum=0.,correction=0.;size_t i;unsigned j,k;
    if(derivatives!=0 && derivatives!=1)return -2;
    for(j=0;j<16;j++)if(!isfinite(x[j]) || x[j]<ch_lower[j] || x[j]>ch_upper[j])return -3;
    for(j=0;j<5;j++)theta[j]=x[j];
    theta[5]=x[11];theta[6]=x[5];
    for(j=0;j<5;j++)alpha[j]=x[6+j];
    for(j=0;j<3;j++)alpha[5+j]=x[12+j];
    alpha[8]=x[10]*x[15];
    if(scm_model_init(&m,3,theta))return -4;
    memset(gradient,0,128);memset(metric,0,256*sizeof(double));
    for(i=0;i<n;i++) {
        double mu,r,v,t;
        if(!isfinite(samples[3*i+2]) || scm_model_step(&m,NULL,samples[3*i],samples[3*i+1],&row) ||
           scm_model_predict(&row,3,alpha,&mu,derivatives?jac:NULL))return -5;
        r=(mu-samples[3*i+2])/.001;v=.5*r*r;t=sum+v;
        correction+=fabs(sum)>=fabs(v)?(sum-t)+v:(v-t)+sum;sum=t;
        if(derivatives) {
            for(j=0;j<5;j++)g[j]=jac[j];
            g[5]=jac[6];g[11]=jac[5];g[6]=row.X[0];
            for(j=0;j<3;j++){g[7+j]=row.X[1+j];g[12+j]=row.X[5+j];}
            g[10]=row.X[4]+row.X[8]*x[15];g[15]=row.X[8]*x[10];
            for(j=0;j<16;j++)g[j]/=.001;
            for(j=0;j<16;j++) {
                gradient[j]+=r*g[j];
                for(k=0;k<=j;k++)metric[16*j+k]+=g[j]*g[k];
            }
        }
    }
    *cost=sum+correction;
    endpoint[0]=m.z0-m.charge_Ah/m.Q;
    for(j=0;j<3;j++)endpoint[j+1]=x[j+7]*m.f[j]+x[j+12]*m.a[j];
    endpoint[4]=m.hb+x[15]*m.ha;
    for(j=0;j<16;j++) {
        if(!isfinite(gradient[j]))return -6;
        for(k=0;k<=j;k++) {
            if(!isfinite(metric[16*j+k]))return -6;
            metric[16*k+j]=metric[16*j+k];
        }
    }
    return isfinite(*cost)?0:-6;
}
