/* Frozen physical generator and independent original-rolling harness.
 * Generator truth output is never an input of run_legacy. */
#include "../../include/scm_model.h"
#include "../live_anchor_integration_001/rolling_engine.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static const adc12_calibration cal = {{1.5,1./1024.},{-.256,.000125},{-40.,.0625},1./35.};
static double uniform01(uint64_t *s) {
    *s=*s*UINT64_C(6364136223846793005)+UINT64_C(1442695040888963407);
    return ((double)(*s>>11)+.5)/9007199254740992.;
}
static int code(double x,double offset,double step) {
    double a=(x-offset)/step;
    if(!isfinite(a) || a<0 || a>4095)return -1;
    return (int)floor(a+.5);
}
static double decoded(double x,double offset,double step) {
    int c=code(x,offset,step);
    return c<0?NAN:offset+c*step;
}

int generate(int which,int n,double *obs,double *truth) {
    scm_physical p;
    scm_physical_state state;
    uint64_t rng=UINT64_C(7312051);
    double oldT=25.;int i,j;
    if(which<0 || which>3 || n<1)return -1;
    memset(&p,0,sizeof(p));memset(&state,0,sizeof(state));
    p.modes=3;state.z=.61;
    for(i=0;i<n;i++) {
        double dt=1./35.,t=(i+1)/35.,cycle=fmod(i/35.,160.),I=0.,V,u1,u2;
        double phase=fmax(0.,fmin(1.,(t-3600.)/10800.));
        double age=phase*phase*(3.-2.*phase);
        double T=which==3?decoded(25.+8.*sin(6.283185307179586*t/3600.),-40.,.0625):25.;
        double q=which==1?.0567:(which==3?.0576*(1.-.09*age):.06*(1.-(which==2?.1*age:0.)));
        double r=which==1?.107:(which==3?.104*(1.+.12*age):.1*(1.+(which==2?.12*age:0.)));
        double gq=which==3?.0013:0.,gr=which==3?-.006:0.;
        double f0=1.+gq*(oldT-25.),f1=1.+gq*(T-25.);
        double d=(f1-f0)/f0,inv=d==0?1.:log1p(d)/d;
        double sigma=which==3?.012:.001;
        double amp=.03;
        if(which==3) {
            int k=((int)floor(i/35./160.))%3;
            amp=k==0?.0125:(k==1?.025:.05);
        }
        if(i<5400*35 || i>=10800*35) {
            if(cycle<70)I=amp;
            else if(cycle>=80 && cycle<150)I=-amp;
        }
        I=decoded(I,-.256,.000125);
        p.Q=q*f0/inv;p.R0=r*(1.+gr*(T-25.));
        for(j=0;j<3;j++) {
            const double R[3]={.04,.08,.12},tau[3]={.05,.5,5.};
            const double roff[3]={1.08,.94,1.12},coff[3]={.91,1.07,.95};
            double rf=which==3?roff[j]*(1.+.1*age):1.;
            double cf=which==3?coff[j]*(1.-.08*age):1.;
            p.R[j]=R[j]*rf;p.tau[j]=tau[j]*rf*cf;
        }
        p.H=which==3?.0165:.015;
        p.gamma_plus=which==3?107.:100.;p.gamma_minus=which==3?142.:150.;
        if(scm_physical_step(&p,&state,0,dt,I,&V)!=SCM_OK)return i+1;
        u1=uniform01(&rng);u2=uniform01(&rng);
        obs[5*i]=dt;obs[5*i+1]=I;obs[5*i+2]=T;
        obs[5*i+3]=decoded(V+sigma*sqrt(-2.*log(u1))*cos(6.283185307179586*u2),1.5,1./1024.);
        obs[5*i+4]=sqrt(sigma*sigma+(1./1024.)*(1./1024.)/12.);
        if(!isfinite(obs[5*i+3]))return i+1;
        truth[6*i]=q*f1;truth[6*i+1]=p.R0;truth[6*i+2]=state.z;
        truth[6*i+3]=V;truth[6*i+4]=q;truth[6*i+5]=age;
        oldT=T;
    }
    return 0;
}

/* Output per16-record block: next_index,Q,R0,SOC,search_stop,accepted_steps.
 * Counters: status,committed_records,outputs,model_steps,context_bytes.
 * No truth, temperature compensation, prior changes or history feedback. */
int run_legacy(const double *obs,int n,const unsigned char id[32],double *out,double counters[5]) {
    re_context c;int status,i,k=0;
    memset(counters,0,5*sizeof(double));
    status=re_init(&c,id,&cal);
    if(status)goto done;
    for(i=0;i<n;i++) {
        adc12_raw_sample raw;
        int v=code(obs[5*i+3],1.5,1./1024.);
        int a=code(obs[5*i+1],-.256,.000125);
        int t=code(obs[5*i+2],-40.,.0625);
        if(obs[5*i]!=1./35. || v<0 || a<0 || t<0){status=-300;goto done;}
        raw.interval_ticks=1;raw.codes.voltage=(uint16_t)v;
        raw.codes.current=(uint16_t)a;raw.codes.temperature=(uint16_t)t;
        status=re_offer(&c,id,(uint64_t)i,&raw);if(status)goto done;
        status=re_admit(&c);if(status)goto done;
        if(c.inputs.block_count==16) {
            unsigned stop;
            status=re_process(&c,1);if(status)goto done;
            stop=c.core.result.evidence.stop_reason;
            memcpy(c.core.workspace.query.point,c.core.bank.estimate,16*sizeof(double));
            status=re_query(&c,0,1);if(status)goto done;
            out[6*k]=(double)c.core.bank.next_index;
            out[6*k+1]=exp(c.core.bank.estimate[5]);out[6*k+2]=c.core.bank.estimate[6];
            out[6*k+3]=c.core.result.evidence.detail.endpoint.SOC;
            out[6*k+4]=stop;out[6*k+5]=(double)c.core.bank.accepted_steps;k++;
        }
    }
done:
    counters[0]=status;counters[1]=(double)c.core.bank.next_index;counters[2]=k;
    counters[3]=(double)c.core.bank.model_steps;counters[4]=sizeof(c);
    return status;
}
