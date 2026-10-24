#include "scm_model.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(c,m) do{if(!(c)){fprintf(stderr,"FAIL %s\n",m);failures++;}}while(0)
static const scm_sample history[]={
 {0,.04,0},{.003,.04,0},{.1,.04,0},{1.7,.04,0},{9,.04,0},{13,.017,0},
 {71,0,0},{.002,-.06,0},{.09,-.06,0},{3,-.06,0},{21,-.026,0},
 {100,0,0},{16,.08,0},{300,.005,0},{40,-.04,0},{8,.02,0}};
#define NS (sizeof(history)/sizeof(history[0]))

static int trace(int n,const double *theta,const double *alpha,
                 double *y,double jac[NS][SCM_MAX_THETA])
{
    scm_model_state s;scm_model_row r;size_t k;int e=scm_model_init(&s,n,theta);
    if(e)return e;
    for(k=0;k<NS;k++){
        e=scm_model_step(&s,NULL,history[k].dt,history[k].current,&r);if(e)return e;
        e=scm_model_predict(&r,n,alpha,&y[k],jac?jac[k]:NULL);if(e)return e;
    }
    return SCM_OK;
}

static void check_dimension(int n,double *equivalence,double *derivative)
{
    double theta[SCM_MAX_THETA]={0},alpha[SCM_MAX_ALPHA]={0};
    double yp[NS],ym[NS],y[NS],jac[NS][SCM_MAX_THETA],tp[SCM_MAX_THETA],tm[SCM_MAX_THETA];
    scm_physical p;scm_physical_state s;
    double v,e,fd,eps=1e-5;size_t k;int i,nt=scm_model_ntheta(n);
    memset(&p,0,sizeof(p));memset(&s,0,sizeof(s));
    p.modes=n;p.R0=.15;p.H=.027;p.gamma_plus=2200;p.gamma_minus=1300;p.Q=.0647;
    s.z=.61;s.h=-.37;alpha[0]=p.R0;alpha[1+n]=p.H;alpha[2+2*n]=p.H*s.h;
    for(i=0;i<n;i++){
        const double fast_tau[]={.05,.5,5};
        p.R[i]=.21+.11*i;p.tau[i]=n==3?fast_tau[i]:(i?48:4.5);
        s.v[i]=(i==1?-.007:.011)*(i+1);
        theta[i]=log(p.tau[i]);alpha[1+i]=p.R[i];alpha[2+n+i]=s.v[i];
    }
    theta[n]=log(p.gamma_plus);theta[n+1]=log(p.gamma_minus);
    theta[n+2]=s.z;theta[n+3]=log(p.Q);
    CHECK(trace(n,theta,alpha,y,jac)==SCM_OK,"affine trace");
    for(k=0;k<NS;k++){
        CHECK(scm_physical_step(&p,&s,NULL,history[k].dt,history[k].current,&v)==SCM_OK,"physical trace");
        e=fabs(v-y[k]);if(e>*equivalence)*equivalence=e;
        CHECK(e<4e-14,"physical and affine output equality");
    }
    for(i=0;i<nt;i++){
        memcpy(tp,theta,sizeof(tp));memcpy(tm,theta,sizeof(tm));tp[i]+=eps;tm[i]-=eps;
        CHECK(trace(n,tp,alpha,yp,NULL)==SCM_OK,"positive derivative perturbation");
        CHECK(trace(n,tm,alpha,ym,NULL)==SCM_OK,"negative derivative perturbation");
        for(k=0;k<NS;k++){
            fd=(yp[k]-ym[k])/(2*eps);e=fabs(fd-jac[k][i]);if(e>*derivative)*derivative=e;
            CHECK(e<2e-8,"analytic nonlinear derivative finite difference");
        }
    }
}

static void check_domains(void)
{
    const double z[]={0,.3,.7,1},u[]={3,3.3,3.8,4.2},badz[]={0,.3,.3,1};
    scm_ocv c={4,z,u},bad={4,badz,u};scm_model_state s,before;scm_model_row r;
    double value,slope,theta[]={log(3),log(2000),log(1000),.5,log(.06)};
    CHECK(scm_ocv_validate(&c)==SCM_OK,"valid PWL table");
    CHECK(scm_ocv_validate(&bad)!=SCM_OK,"duplicate labels rejected");
    CHECK(scm_ocv_eval(&c,.5,&value,&slope)==SCM_OK,"PWL query");
    CHECK(fabs(value-3.55)<1e-14&&fabs(slope-1.25)<1e-14,"PWL interpolation and slope");
    CHECK(scm_ocv_eval(&c,1.001,&value,&slope)==SCM_ERR_DOMAIN,"PWL no extrapolation");
    CHECK(scm_model_init(&s,1,theta)==SCM_OK,"state init");before=s;
    CHECK(scm_model_step(&s,&c,3600,1,&r)==SCM_ERR_DOMAIN,"SOC violation rejected");
    CHECK(memcmp(&s,&before,sizeof(s))==0,"failure leaves state unchanged");
}

static void check_35Hz(double *endpoint_error)
{
    scm_physical p={3,.15,{.21,.32,.43},{.05,.5,5},.027,2200,1300,.0647};
    scm_physical_state fine={.61,{.011,-.014,.033},-.37},coarse=fine;
    const double dt=1.0/35.0;double vf=0,vc=0,e;int k,i;
    /* 3500 nominal ADC samples advance state through 100 s. A final endpoint
     * check against one exact dwell is independent of sampling frequency. */
    for(k=0;k<3500;k++)CHECK(scm_physical_step(&p,&fine,NULL,dt,.002,&vf)==SCM_OK,"35Hz physical step");
    CHECK(scm_physical_step(&p,&coarse,NULL,100,.002,&vc)==SCM_OK,"one exact dwell");
    *endpoint_error=fabs(vf-vc);CHECK(*endpoint_error<2e-11,"35Hz vs exact dwell voltage");
    CHECK(fabs(fine.z-coarse.z)<2e-11&&fabs(fine.h-coarse.h)<2e-11,"35Hz carried SOC and hysteresis");
    for(i=0;i<3;i++){e=fabs(fine.v[i]-coarse.v[i]);CHECK(e<2e-13,"35Hz carried Foster states");}
    coarse=fine;
    CHECK(scm_physical_step(&p,&fine,NULL,11,0,&vf)==SCM_OK,"true rest");
    CHECK(fine.h==coarse.h&&fine.z==coarse.z,"rest freezes SOC and h exactly");
    CHECK(fabs(fine.v[2]-coarse.v[2]*exp(-11/p.tau[2]))<1e-15,"rest relaxes slow polarization");
}

int main(void)
{
    double eq=0,deriv=0,stream=0;int n;
    for(n=1;n<=3;n++)check_dimension(n,&eq,&deriv);
    check_domains();check_35Hz(&stream);
    printf("{\"test\":\"scm_model_reconstructed_3RC\",\"failures\":%d,"
           "\"modes_tested\":[1,2,3],\"max_physical_design_difference_V\":%.17g,"
           "\"max_derivative_absolute_error\":%.17g,\"35Hz_endpoint_difference_V\":%.17g,"
           "\"model_state_bytes\":%zu,\"row_bytes\":%zu}\n",failures,eq,deriv,stream,
           sizeof(scm_model_state),sizeof(scm_model_row));
    return failures?1:0;
}
