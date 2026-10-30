#include "scm_model.h"
#include <math.h>
#include <stdint.h>

static double uniform01(uint64_t *s) {
    *s = *s * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    return ((double)(*s >> 11) + 0.5) / 9007199254740992.0;
}

static double temperature(double t) {
    return 25.0 + 8.0*sin(6.2831853071795864769*t/3600.0);
}

/* Truth is emitted only for scoring. The estimator receives obs alone. */
int generate_case(int stress, int count, double *obs, double *truth) {
    scm_physical p;
    scm_physical_state state;
    uint64_t rng = UINT64_C(291031067);
    double oldT=25.0;
    int i,j;
    p.modes=3; p.R0=.1; p.Q=.06; p.H=.015;
    p.gamma_plus=100.;p.gamma_minus=150.;
    p.R[0]=.04;p.R[1]=.08;p.R[2]=.12;
    p.tau[0]=.05;p.tau[1]=.5;p.tau[2]=5.;
    state.z=.61;state.h=0.;
    for(j=0;j<3;j++)state.v[j]=0.;
    for(i=0;i<count;i++) {
        double dt=1.0/35.0,t=(i+1)/35.0,T=temperature(t);
        double cycle=fmod(i/35.0,160.0),I=0.0,V,noise;
        double qref=(stress && i>=3600*35)?.051:.06;
        double rref=(stress && i>=3600*35)?.115:.1;
        double f0=1+.002*(oldT-25),f1=1+.002*(T-25);
        double ratio=(f1-f0)/f0;
        double inverse_factor=ratio==0?1.:log1p(ratio)/ratio;
        if(i<5400*35 || i>=10800*35) {
            if(cycle<70)I=.03;
            else if(cycle>=80 && cycle<150)I=-.03;
        }
        p.Q=qref*f0/inverse_factor;
        p.R0=rref*(1-.01*(T-25));
        if(scm_physical_step(&p,&state,0,dt,I,&V)!=SCM_OK)return i+1;
        noise=.004*sqrt(-2*log(uniform01(&rng)))*cos(6.2831853071795864769*uniform01(&rng));
        obs[5*i]=dt;obs[5*i+1]=I;obs[5*i+2]=T;obs[5*i+3]=V+noise;obs[5*i+4]=.004;
        truth[4*i]=qref*f1;truth[4*i+1]=p.R0;truth[4*i+2]=state.z;truth[4*i+3]=V;
        oldT=T;
    }
    return 0;
}
