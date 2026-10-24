/* Public-API audit of the reconstructed 3RC estimator and profile controls.
 * Local profile derivatives are checked by recomputing constrained minima.
 * This test does not establish global nonlinear optimization or coverage.
 */
#include "scm_estimator.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

#define NS 3500
#define NT 7
#define NA 9
#define ND 16
static int failures;
#define CHECK(c,m) do{if(!(c)){fprintf(stderr,"FAIL %s\n",m);failures++;}}while(0)
static const double theta0[NT]={-2.9957322735539909,-.69314718055994529,
 1.6094379124341003,5.393627546352362,5.913503005638270,.7,-2.8134107167600364};
static const double alpha0[NA]={.12,.18,.23,.27,.045,.004,-.003,.002,.03465};

static void fixed_options(scm_fit_options *o,const double *theta,int linked,double soc)
{
    scm_fit_options_default(o);o->starts=1;o->max_iterations=2;
    o->fixed_mask=(1u<<NT)-1u;
    memcpy(o->fixed_theta,theta,NT*sizeof(double));
    if(linked){o->fixed_mask&=~(1u<<5);o->has_current_soc=1;o->current_soc=soc;}
}
static int fixed_fit(scm_problem *p,const double *theta,int linked,double soc,scm_fit_result *r)
{
    scm_fit_options o;fixed_options(&o,theta,linked,soc);return scm_fit(p,&o,r);
}
static double feasibility(const scm_fit_result *r)
{
    double v=0;int i;
    for(i=0;i<5;i++)v=fmax(v,-r->alpha[i]);
    v=fmax(v,fabs(r->alpha[8])-r->alpha[4]);
    for(i=5;i<8;i++)v=fmax(v,fabs(r->alpha[i])-.08);
    return v;
}
static double replay(const scm_sample *samples,size_t count,const scm_fit_result *r,
                     int linked,double *g,double *joint,double *soc_gradient)
{
    scm_model_state s;scm_model_row row;double mu,jac[NT],cost=0;size_t k;int i,j;
    if(g)memset(g,0,NT*sizeof(double));
    if(joint)memset(joint,0,ND*ND*sizeof(double));
    if(soc_gradient)*soc_gradient=0;
    CHECK(scm_model_init(&s,3,r->theta)==SCM_OK,"replay init");
    for(k=0;k<count;k++){
        double resid,vec[ND];
        CHECK(scm_model_step(&s,NULL,samples[k].dt,samples[k].current,&row)==SCM_OK,"replay step");
        CHECK(scm_model_predict(&row,3,r->alpha,&mu,jac)==SCM_OK,"replay prediction");
        resid=(mu-samples[k].voltage)/.001;cost+=.5*resid*resid;
        if(soc_gradient)*soc_gradient+=resid*jac[5]/.001;
        if(linked)jac[6]-=r->charge_Ah/exp(r->theta[6])*jac[5];
        for(i=0;i<NT;i++){
            vec[i]=jac[i]*r->coordinate_scales[i]/.001;
            if(g)g[i]+=resid*vec[i];
        }
        for(i=0;i<NA;i++)vec[NT+i]=row.X[i]*r->coordinate_scales[NT+i]/.001;
        if(joint)for(i=0;i<ND;i++)for(j=0;j<ND;j++)joint[i*ND+j]+=vec[i]*vec[j];
    }
    return cost;
}

static void gradient_check(scm_problem *p,const scm_sample *samples,int linked,double soc,
                           double *max_error,double *soc_target_error,double *gram_error)
{
    scm_fit_result r,rp,rm;double g[NT],joint[ND*ND],sg=0,reference,largest=1;
    double tp[NT],tm[NT];int i;const double eps=1e-6;
    int ret=fixed_fit(p,theta0,linked,soc,&r);
    CHECK(ret==0,"profile base fit");if(ret)return;
    reference=replay(samples,NS,&r,linked,g,joint,&sg);
    CHECK(fabs(reference-r.objective)<1e-7,"profile cost equals returned physical point cost");
    for(i=0;i<ND*ND;i++)largest=fmax(largest,fabs(joint[i]));
    for(i=0;i<ND*ND;i++)*gram_error=fmax(*gram_error,fabs(joint[i]-r.joint_normal[i])/largest);
    if(linked)*soc_target_error=fmax(*soc_target_error,fabs(r.theta[5]-r.charge_Ah/exp(r.theta[6])-soc));
    for(i=0;i<NT;i++){
        double fd,error;if(linked&&i==5)continue;
        memcpy(tp,theta0,sizeof(tp));memcpy(tm,theta0,sizeof(tm));
        tp[i]+=eps*r.coordinate_scales[i];tm[i]-=eps*r.coordinate_scales[i];
        CHECK(fixed_fit(p,tp,linked,soc,&rp)==0,"positive profile coordinate");
        CHECK(fixed_fit(p,tm,linked,soc,&rm)==0,"negative profile coordinate");
        fd=(rp.objective-rm.objective)/(2*eps);
        error=fabs(fd-g[i])/fmax(1,fabs(fd));*max_error=fmax(*max_error,error);
    }
    if(linked){
        double fd,error;
        CHECK(fixed_fit(p,theta0,1,soc+eps,&rp)==0,"positive current SOC target");
        CHECK(fixed_fit(p,theta0,1,soc-eps,&rm)==0,"negative current SOC target");
        fd=(rp.objective-rm.objective)/(2*eps);
        error=fabs(fd-sg)/fmax(1,fabs(fd));*max_error=fmax(*max_error,error);
    }
}

int main(void)
{
    static scm_sample samples[NS],rest[300];
    const double currents[]={.03,.06,0,-.05,.015,0,.04,-.025,.05,-.03};
    scm_physical p={3,.12,{.18,.23,.27},{.05,.5,5},.045,220,370,.06};
    scm_physical_state s={.7,{.004,-.003,.002},.77};
    scm_problem *problem;scm_fit_options o;scm_fit_result baseline,r,after;
    double q=0,noiseless=0,alpha_error=0,restore_error=0,feas=0;
    double base_gradient_error=0,linked_gradient_error=0,gram_error=0,target_error=0;
    double noise_cost=0,zero_cost=0;unsigned zero_mask=0;int i,k,rc;
    for(k=0;k<NS;k++){
        samples[k].dt=1.0/35;samples[k].current=currents[k/350];
        q+=samples[k].dt*samples[k].current/3600;
        CHECK(scm_physical_step(&p,&s,NULL,samples[k].dt,samples[k].current,&samples[k].voltage)==SCM_OK,"generate 35Hz physical data");
    }
    problem=scm_problem_create(samples,NS,3,.001,NULL,SCM_FULL);
    CHECK(problem!=NULL,"create full problem");if(!problem)return 1;
    rc=fixed_fit(problem,theta0,0,0,&baseline);CHECK(rc==0,"noiseless base fit");if(rc)return 1;
    noiseless=baseline.objective;for(i=0;i<NA;i++)alpha_error=fmax(alpha_error,fabs(baseline.alpha[i]-alpha0[i]));
    CHECK(noiseless<1e-7,"noiseless objective");CHECK(alpha_error<3e-6,"noiseless linear recovery");
    /* u0 exceeds the default initial H, so feasibility needs coupled setup. */
    fixed_options(&o,theta0,0,0);o.fixed_alpha_mask=1u<<8;o.fixed_alpha[8]=alpha0[8];
    CHECK(scm_fit(problem,&o,&r)==0,"fixed u0 greater than nominal H is feasible");
    CHECK(fabs(r.alpha[8]-alpha0[8])<1e-10,"fixed u0 equality");feas=fmax(feas,feasibility(&r));
    CHECK(r.objective<1e-7,"fixed true u0 objective");
    fixed_options(&o,theta0,0,0);o.fixed_alpha_mask=(1u<<0)|(1u<<4)|(1u<<8);
    o.fixed_alpha[0]=.12;o.fixed_alpha[4]=.04;o.fixed_alpha[8]=.04;
    CHECK(scm_fit(problem,&o,&r)==0,"R0/H/u0 equalities with u0=H");
    CHECK(fabs(r.alpha[0]-.12)<1e-10&&fabs(r.alpha[4]-.04)<1e-10&&fabs(r.alpha[8]-.04)<1e-10,"fixed R0/H/u0 respected");
    feas=fmax(feas,feasibility(&r));
    CHECK(fixed_fit(problem,theta0,0,0,&after)==0,"unrestricted call after equality profile");
    restore_error=fmax(restore_error,fabs(after.objective-baseline.objective));
    for(i=0;i<NA;i++)restore_error=fmax(restore_error,fabs(after.alpha[i]-baseline.alpha[i]));
    fixed_options(&o,theta0,0,0);o.fixed_alpha_mask=(1u<<4)|(1u<<8);o.fixed_alpha[4]=.02;o.fixed_alpha[8]=.04;
    CHECK(scm_fit(problem,&o,&r)!=0,"infeasible H/u0 pair rejected");
    CHECK(fixed_fit(problem,theta0,0,0,&after)==0,"problem reusable after failed profile");
    restore_error=fmax(restore_error,fabs(after.objective-baseline.objective));
    for(i=0;i<NA;i++)restore_error=fmax(restore_error,fabs(after.alpha[i]-baseline.alpha[i]));
    CHECK(restore_error<1e-9,"profile constraints restored");
    scm_problem_destroy(problem);
    for(k=0;k<NS;k++)samples[k].voltage+=.0007*sin(.73*k)+.0002*cos(.117*k);
    problem=scm_problem_create(samples,NS,3,.001,NULL,SCM_FULL);
    CHECK(problem!=NULL,"create noisy problem");if(!problem)return 1;
    CHECK(fixed_fit(problem,theta0,0,0,&r)==0,"noisy profile fit");noise_cost=r.objective;
    gradient_check(problem,samples,0,0,&base_gradient_error,&target_error,&gram_error);
    gradient_check(problem,samples,1,theta0[5]-q/exp(theta0[6]),&linked_gradient_error,&target_error,&gram_error);
    CHECK(base_gradient_error<5e-5,"unrestricted envelope gradient");
    CHECK(linked_gradient_error<5e-5,"fixed-current-SOC chain-rule gradient");
    CHECK(target_error<1e-13,"current SOC equals requested target");
    CHECK(gram_error<2e-12,"full undamped joint Gram before reduction");
    CHECK(fixed_fit(problem,theta0,0,0,&after)==0,"unrestricted call after linked SOC profile");
    CHECK(fabs(after.objective-noise_cost)<1e-9,"linked SOC constraint restored");
    scm_problem_destroy(problem);
    s.z=.7;s.h=.77;for(i=0;i<3;i++)s.v[i]=0;
    for(k=0;k<300;k++){
        rest[k].dt=1.0/35;rest[k].current=0;
        CHECK(scm_physical_step(&p,&s,NULL,rest[k].dt,0,&rest[k].voltage)==SCM_OK,"generate rest data");
    }
    problem=scm_problem_create(rest,300,3,.001,NULL,SCM_FULL);
    CHECK(problem!=NULL,"create zero-excitation problem");if(!problem)return 1;
    CHECK(fixed_fit(problem,theta0,0,0,&r)==0,"singular zero-excitation inner solve");zero_cost=r.objective;zero_mask=r.unexcited_theta_mask;
    CHECK(zero_cost<1e-7,"zero-excitation compatible fit");
    CHECK((zero_mask&((1u<<3)|(1u<<4)))==((1u<<3)|(1u<<4)),"both directional rates tagged unexcited");
    fixed_options(&o,theta0,0,0);o.fixed_alpha_mask=(1u<<NA)-1u;
    memcpy(o.fixed_alpha,alpha0,NA*sizeof(double));for(i=5;i<8;i++)o.fixed_alpha[i]=0;
    CHECK(scm_fit(problem,&o,&r)==0,"all linear equalities with singular data");
    CHECK(r.objective<1e-7,"fixed compatible rest amplitudes");feas=fmax(feas,feasibility(&r));
    CHECK(feas<1e-10,"physical amplitude feasibility");
    scm_problem_destroy(problem);
    printf("{\"test\":\"scm_estimator_profile_API_3RC\",\"failures\":%d,\"samples\":%d,"
           "\"sample_rate_Hz\":35,\"noiseless_objective\":%.17g,\"noisy_objective\":%.17g,"
           "\"max_linear_parameter_error\":%.17g,\"max_feasibility_violation\":%.17g,"
           "\"constraint_restore_error\":%.17g,\"profile_gradient_relative_error\":%.17g,"
           "\"linked_SOC_gradient_relative_error\":%.17g,\"joint_Gram_relative_error\":%.17g,"
           "\"current_SOC_target_error\":%.17g,\"zero_excitation_objective\":%.17g,"
           "\"zero_excitation_theta_mask\":%u}\n",
           failures,NS,noiseless,noise_cost,alpha_error,feas,restore_error,base_gradient_error,
           linked_gradient_error,gram_error,target_error,zero_cost,zero_mask);
    return failures?1:0;
}
