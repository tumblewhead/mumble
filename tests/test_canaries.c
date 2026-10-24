/* Reconstructed electrical ambiguity tests. SCM Lemma B.21's common cubic OCV
 * is replaced by the common illustrative curve: equal SOC paths make it cancel.
 * These are forward witnesses, not a test that a point estimator retains every
 * compatible candidate, and not a full electrothermal ambiguity claim.
 */
#include "scm_model.h"
#include <math.h>
#include <stdio.h>
static int failures;
#define CHECK(c,m) do{if(!(c)){fprintf(stderr,"FAIL %s\n",m);failures++;}}while(0)

static void collision(double *prefix,double *rest)
{
    const double x=.02,R=x/256;
    scm_physical a={1,0,{0},{0},0,0,0,1},b;
    scm_physical_state sa={.5,{0},-1},sb;
    double va=0,vb=0,I,e;int dwell,k;
    a.R0=R;a.R[0]=R;a.tau[0]=1/log(2);a.H=x;a.gamma_plus=3600*log(2);a.gamma_minus=1700;
    b=a;b.tau[0]=1/log(4);sa.v[0]=R+x;sb=sa;sb.v[0]=R;sb.h=0;*prefix=0;
    for(dwell=0;dwell<2;dwell++){
        I=dwell?2:1;
        CHECK(scm_physical_step(&a,&sa,NULL,0,I,&va)==SCM_OK,"collision transition A");
        CHECK(scm_physical_step(&b,&sb,NULL,0,I,&vb)==SCM_OK,"collision transition B");
        e=fabs(va-vb);if(e>*prefix)*prefix=e;
        for(k=0;k<800;k++){
            CHECK(scm_physical_step(&a,&sa,NULL,.01,I,&va)==SCM_OK,"collision step A");
            CHECK(scm_physical_step(&b,&sb,NULL,.01,I,&vb)==SCM_OK,"collision step B");
            e=fabs(va-vb);if(e>*prefix)*prefix=e;
        }
    }
    CHECK(*prefix<5e-13,"two-dwell equality");
    CHECK(scm_physical_step(&a,&sa,NULL,1,0,&va)==SCM_OK,"collision rest A");
    CHECK(scm_physical_step(&b,&sb,NULL,1,0,&vb)==SCM_OK,"collision rest B");
    *rest=va-vb;CHECK(fabs(*rest+3.9061605930701404e-5)<5e-13,"predicted rest separation");
}

static void rest_ambiguity(double *error,double *hB,double *suffix)
{
    scm_physical a={1,.18,{.3},{4},.025,2000,1200,.06},b=a;
    scm_physical_state sa={.55,{0},0},sb={.558,{0},0};
    double ua,ub,slope,va=0,vb=0,e;int k;
    b.Q=.075;
    CHECK(scm_ocv_eval(NULL,sa.z,&ua,&slope)==SCM_OK,"rest OCV A");
    CHECK(scm_ocv_eval(NULL,sb.z,&ub,&slope)==SCM_OK,"rest OCV B");
    sb.h=(ub-ua)/a.H;*hB=sb.h;*error=0;
    CHECK(fabs(sb.h)<=1,"admissible hysteresis alternative");
    for(k=0;k<600;k++){
        CHECK(scm_physical_step(&a,&sa,NULL,60,0,&va)==SCM_OK,"rest A");
        CHECK(scm_physical_step(&b,&sb,NULL,60,0,&vb)==SCM_OK,"rest B");
        e=fabs(va-vb);if(e>*error)*error=e;
    }
    CHECK(*error<5e-14,"ten-hour rest ambiguity");
    CHECK(sa.z==.55&&sb.z==.558&&sa.h==0&&sb.h==*hB,"rest carries distinct states");
    CHECK(scm_physical_step(&a,&sa,NULL,60,.03,&va)==SCM_OK,"rest suffix A");
    CHECK(scm_physical_step(&b,&sb,NULL,60,.03,&vb)==SCM_OK,"rest suffix B");
    *suffix=va-vb;CHECK(fabs(*suffix)>1e-4,"nonzero current distinguishes rest pair");
}

static void chronology(double *observed,double *expected,double *charge)
{
    const double duration=10,I1=.02,I2=.06;
    scm_physical p={1,.18,{.3},{4},.025,2000,1200,.06};
    scm_physical_state a={.6,{.01},-.3},b=a;double va,vb,e=exp(-duration/p.tau[0]);
    CHECK(scm_physical_step(&p,&a,NULL,duration,I1,&va)==SCM_OK,"order A1");
    CHECK(scm_physical_step(&p,&a,NULL,duration,I2,&va)==SCM_OK,"order A2");
    CHECK(scm_physical_step(&p,&b,NULL,duration,I2,&vb)==SCM_OK,"order B1");
    CHECK(scm_physical_step(&p,&b,NULL,duration,I1,&vb)==SCM_OK,"order B2");
    *charge=a.z-b.z;*observed=a.v[0]-b.v[0];*expected=p.R[0]*(1-e)*(1-e)*(I2-I1);
    CHECK(fabs(*charge)<2e-15,"same transferred charge");
    CHECK(fabs(a.h-b.h)<2e-15,"same directional throughput hysteresis");
    CHECK(fabs(*observed-*expected)<2e-15&&fabs(*observed)>1e-3,"Foster chronological effect");
    CHECK(scm_physical_step(&p,&a,NULL,0,0,&va)==SCM_OK,"common endpoint A");
    CHECK(scm_physical_step(&p,&b,NULL,0,0,&vb)==SCM_OK,"common endpoint B");
    CHECK(fabs((va-vb)+*observed)<2e-14,"common-current voltage carries chronology");
}

int main(void)
{
    double prefix,rest,ambiguity,hB,suffix,order,expected,charge;
    collision(&prefix,&rest);rest_ambiguity(&ambiguity,&hB,&suffix);chronology(&order,&expected,&charge);
    printf("{\"test\":\"scm_canaries_reconstructed\",\"failures\":%d,"
           "\"collision_prefix_max_difference_V\":%.17g,\"collision_rest_1s_difference_V\":%.17g,"
           "\"rest_10h_max_difference_V\":%.17g,\"rest_candidate_B_h\":%.17g,"
           "\"rest_suffix_difference_V\":%.17g,\"chronology_polarization_difference_V\":%.17g,"
           "\"chronology_expected_difference_V\":%.17g,\"chronology_SOC_difference\":%.17g}\n",
           failures,prefix,rest,ambiguity,hB,suffix,order,expected,charge);
    return failures?1:0;
}
