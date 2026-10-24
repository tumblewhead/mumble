/* Host audit for the sparse fixed-chart remainder prototype.
 * Online ingestion retains no samples and uses caller-owned static scratch.
 * File replay, eigen diagnostics and candidate scoring below are HOST AUDIT
 * ONLY. They do not supply relinearization to the online evidence bank.
 * No truth metadata or nonlinear optimization is used.
 */
#include "scm_evidence.h"
#include "scm_remainder.h"
#include "scm_assess.h"
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define D SCM_EVIDENCE_DIM
#define MAX_CANDIDATES 32

/* Explicitly separated accounting: only online_* is needed for ingestion.
 * The standalone input configuration is duplicated by bank.init; a firmware
 * caller may release its own configuration after initialization.
 */
static scm_evidence_config input_config;
static scm_evidence online_bank;
static scm_evidence_workspace online_work;
static scm_remainder remainder_bank;
static scm_remainder_workspace remainder_work;
static scm_remainder_result remainder_query;
static scm_evidence_factor snapshot;
static scm_fit_result diagnostic_fit;
static scm_assessment diagnostic_assessment;
static scm_assess_workspace diagnostic_work;
static scm_assess_options diagnostic_options;
static double gradient[D], local_step[D], target_gradient[D];
static double input_candidates[MAX_CANDIDATES][D];
static char candidate_names[MAX_CANDIDATES][48];
static int candidate_classes[MAX_CANDIDATES],candidate_available[MAX_CANDIDATES];
static double candidate_scales[MAX_CANDIDATES];
static double direct_normal[D*D], direct_gradient[D], audit_jacobian[D];
static double candidate_theta[SCM_MAX_THETA],candidate_alpha[SCM_MAX_ALPHA];
static long double audit_alpha_precise[SCM_MAX_ALPHA];
static scm_model_state audit_anchor,audit_candidate;
static scm_model_row audit_anchor_row,audit_candidate_row;
static double audit_theta_jac[SCM_MAX_THETA];
static char csv_line[4096],source_hex[65];
static unsigned candidate_count,input_candidate_count;
static double nll_budget,checkpoint_anchor_cost;

static void number(double x)
{
    if(isfinite(x))printf("%.17g",x);else fputs("null",stdout);
}
static void array(const double *x,int n)
{
    int i;putchar('[');for(i=0;i<n;i++){if(i)putchar(',');number(x[i]);}putchar(']');
}
static const char *space(const char *s)
{
    while(isspace((unsigned char)*s))s++;
    return s;
}
static int parse_u64(const char *s,uint64_t *value)
{
    char *end;unsigned long long x;s=space(s);
    if(!*s||*s=='-')return -1;
    errno=0;x=strtoull(s,&end,10);
    if(errno||end==s||*space(end)||x>UINT64_MAX)return -1;
    *value=(uint64_t)x;return 0;
}
static int parse_budget(const char *s)
{
    char *end;errno=0;nll_budget=strtod(s,&end);
    return errno||end==s||*space(end)||!isfinite(nll_budget)||nll_budget<0?-1:0;
}
static int hex_digit(char c)
{
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return c-'a'+10;
    if(c>='A'&&c<='F')return c-'A'+10;
    return -1;
}
static int read_anchor(const char *path,uint64_t event_cap)
{
    FILE *f=fopen(path,"r");int i,nt,na,d,c,rc=-1;
    if(!f){fprintf(stderr,"Cannot open anchor: %s\n",path);return -1;}
    memset(&input_config,0,sizeof(input_config));
    if(fscanf(f,"%d%lf%64s",&input_config.modes,&input_config.sigma,source_hex)!=3)goto done;
    nt=scm_model_ntheta(input_config.modes);na=scm_model_nalpha(input_config.modes);d=nt+na;
    if(!nt||strlen(source_hex)!=64)goto done;
    for(i=0;i<32;i++) {
        int a=hex_digit(source_hex[2*i]),b=hex_digit(source_hex[2*i+1]);
        if(a<0||b<0)goto done;
        input_config.source_id[i]=(unsigned char)(16*a+b);
    }
    for(i=0;i<nt;i++)if(fscanf(f,"%lf",&input_config.theta[i])!=1)goto done;
    for(i=0;i<na;i++)if(fscanf(f,"%lf",&input_config.alpha[i])!=1)goto done;
    for(i=0;i<d;i++)if(fscanf(f,"%lf",&input_config.scale[i])!=1)goto done;
    for(i=0;i<d;i++)if(fscanf(f,"%lf",&input_config.radius[i])!=1)goto done;
    if(fscanf(f,"%u",&candidate_count)!=1||candidate_count>MAX_CANDIDATES)goto done;
    for(i=0;i<(int)candidate_count*d;i++) {
        double *v=&input_candidates[i/d][i%d];
        if(fscanf(f,"%lf",v)!=1||!isfinite(*v))goto done;
    }
    do{c=fgetc(f);}while(c!=EOF&&isspace((unsigned char)c));
    if(c!=EOF||ferror(f))goto done;
    input_config.max_event_samples=event_cap;
    input_config.residual_rms_limit_sigma=4.;
    rc=scm_evidence_init(&online_bank,&input_config);
    if(!rc)rc=scm_remainder_init(&remainder_bank,&input_config);
    input_candidate_count=candidate_count;
done:
    if(fclose(f)&&rc==0)rc=-1;
    if(rc)fprintf(stderr,"Invalid anchor/configuration (code %d): %s\n",rc,path);
    return rc;
}
static FILE *open_data(const char *path)
{
    FILE *f=fopen(path,"r");size_t n;
    if(!f){fprintf(stderr,"Cannot open data: %s\n",path);return NULL;}
    if(!fgets(csv_line,sizeof(csv_line),f)){fclose(f);return NULL;}
    n=strlen(csv_line);while(n&&(csv_line[n-1]=='\n'||csv_line[n-1]=='\r'))csv_line[--n]=0;
    if(strcmp(csv_line,"sample_index,dt_s,current_A,voltage_V")) {
        fprintf(stderr,"Invalid CSV header: %s\n",path);fclose(f);return NULL;
    }
    return f;
}
static int read_sample(FILE *f,uint64_t expected,scm_sample *s)
{
    const char *p;char *end;unsigned long long index;double values[3];int i;
    if(!fgets(csv_line,sizeof(csv_line),f)) {
        fprintf(stderr,"CSV ended before requested sample %" PRIu64 "\n",expected);return -1;
    }
    if(!strchr(csv_line,'\n')&&!feof(f))goto invalid;
    p=space(csv_line);if(!*p||*p=='-')goto invalid;
    errno=0;index=strtoull(p,&end,10);
    if(errno||end==p||index>UINT64_MAX||(uint64_t)index!=expected)goto invalid;
    p=space(end);if(*p++!=',')goto invalid;
    for(i=0;i<3;i++) {
        errno=0;values[i]=strtod(p,&end);
        if(errno||end==p||!isfinite(values[i]))goto invalid;
        p=space(end);if(i<2){if(*p++!=',')goto invalid;}else if(*p)goto invalid;
    }
    if(values[0]<0)goto invalid;
    s->dt=values[0];s->current=values[1];s->voltage=values[2];return 0;
invalid:
    fprintf(stderr,"Malformed or out-of-order CSV row; expected sample %" PRIu64 "\n",expected);
    return -1;
}
static const char *guard_name(int status)
{
    if(status==SCM_EVIDENCE_OK)return "inside_declared_radius_and_support";
    if(status==SCM_EVIDENCE_ERR_RADIUS)return "relinearization_required";
    if(status==SCM_EVIDENCE_ERR_DOMAIN)return "outside_physical_support";
    return "invalid_candidate";
}
static int support(double x,double lo,double hi)
{
    return isfinite(x)&&x>=lo-1e-12&&x<=hi+1e-12;
}
/* Same declared supports as the reference and evidence core. This host audit
 * ignores only the engineering radius so an out-of-radius failure witness can
 * still receive an exact nonlinear replay when physically feasible.
 */
static int candidate_in_support(void)
{
    int i,n=input_config.modes;
    const double lo3[3]={.015,.15,1.5},hi3[3]={.15,1.5,30};
    for(i=0;i<n;i++) {
        double lo=n==3?lo3[i]:(i?.8:.015),hi=n==3?hi3[i]:(i?180.:30.);
        if(!support(candidate_theta[i],log(lo),log(hi)))return 0;
    }
    if(!support(candidate_theta[n],log(5.),log(1200.))||
       !support(candidate_theta[n+1],log(5.),log(1200.))||
       !support(candidate_theta[n+2],.2,.95)||
       !support(candidate_theta[n+3],log(.03),log(.10)))return 0;
    for(i=0;i<=n;i++)if(!support(candidate_alpha[i],0,1))return 0;
    if(!support(candidate_alpha[n+1],0,.1))return 0;
    for(i=0;i<n;i++)if(!support(candidate_alpha[n+2+i],-.08,.08))return 0;
    return support(candidate_alpha[2+2*n],-.1,.1)&&
           fabs(candidate_alpha[2+2*n])<=candidate_alpha[n+1]+1e-12;
}
static int audit_moments(const char *path,uint64_t count,double factor_zero)
{
    FILE *f=open_data(path);uint64_t index;int i,j,nt=scm_model_ntheta(input_config.modes);
    int na=scm_model_nalpha(input_config.modes),d=nt+na;
    double direct_zero=0,max_h=0,max_g=0,norm_h=0,error_h=0,norm_g=0,error_g=0;
    if(!f)return -1;
    memset(direct_normal,0,sizeof(direct_normal));memset(direct_gradient,0,sizeof(direct_gradient));
    if(scm_model_init(&audit_anchor,input_config.modes,input_config.theta)){fclose(f);return -1;}
    for(index=0;index<count;index++) {
        scm_sample s;double mu,residual;
        if(read_sample(f,index,&s)||scm_model_step(&audit_anchor,&input_config.ocv,s.dt,s.current,&audit_anchor_row)||
           scm_model_predict(&audit_anchor_row,input_config.modes,input_config.alpha,&mu,audit_theta_jac)) {
            fclose(f);return -1;
        }
        residual=(mu-s.voltage)/input_config.sigma;direct_zero+=.5*residual*residual;
        for(i=0;i<nt;i++)audit_jacobian[i]=audit_theta_jac[i]*input_config.scale[i]/input_config.sigma;
        for(i=0;i<na;i++)audit_jacobian[nt+i]=audit_anchor_row.X[i]*input_config.scale[nt+i]/input_config.sigma;
        for(i=0;i<d;i++) {
            direct_gradient[i]+=audit_jacobian[i]*residual;
            for(j=0;j<d;j++)direct_normal[i*d+j]+=audit_jacobian[i]*audit_jacobian[j];
        }
    }
    if(fclose(f))return -1;
    for(i=0;i<d*d;i++) {
        double error=direct_normal[i]-diagnostic_fit.joint_normal[i];
        max_h=fmax(max_h,fabs(error));norm_h=hypot(norm_h,direct_normal[i]);error_h=hypot(error_h,error);
    }
    for(i=0;i<d;i++) {
        double error=direct_gradient[i]-gradient[i];
        max_g=fmax(max_g,fabs(error));norm_g=hypot(norm_g,direct_gradient[i]);error_g=hypot(error_g,error);
    }
    fputs("\"host_direct_affine_audit\":{\"scope\":\"retained_file_replay_not_online\",\"zero_cost\":",stdout);number(direct_zero);
    fputs(",\"zero_cost_error\":",stdout);number(direct_zero-factor_zero);
    fputs(",\"gram_max_abs_error\":",stdout);number(max_h);
    fputs(",\"gram_relative_frobenius_error\":",stdout);number(error_h/fmax(norm_h,1.));
    fputs(",\"gradient_max_abs_error\":",stdout);number(max_g);
    fputs(",\"gradient_relative_l2_error\":",stdout);number(error_g/fmax(norm_g,1.));
    putchar('}');return 0;
}
static void target_diagnostic(const char *name,int logarithmic,double point)
{
    const scm_assessment *a=&diagnostic_assessment;
    int i,j,d=a->joint_dimension;double norm2=0,null2=0,var=0,projection,ratio;
    double radius,lo,hi,half;int available;
    for(i=0;i<d;i++)norm2+=target_gradient[i]*target_gradient[i];
    for(j=0;j<d;j++) {
        projection=0;for(i=0;i<d;i++)projection+=target_gradient[i]*diagnostic_work.vectors[i*d+j];
        if(a->eigenvalues[j]>a->eigen_cutoff)var+=projection*projection/a->eigenvalues[j];
        else null2+=projection*projection;
    }
    ratio=norm2>0?fmin(1.,fmax(0.,null2/norm2)):1.;
    available=!a->matrix_invalid&&a->eigen_converged&&ratio<=diagnostic_options.null_projection_tol&&isfinite(var);
    radius=2*sqrt(fmax(0.,var));lo=logarithmic?point*exp(-radius):point-radius;
    hi=logarithmic?point*exp(radius):point+radius;half=fmax(point-lo,hi-point);
    if(!isfinite(lo)||!isfinite(hi)||!isfinite(half))available=0;
    printf("\"%s\":{\"semantics\":\"fixed_chart_local_only\",\"coverage_validated\":false,\"point\":",name);number(point);
    fputs(",\"null_projection\":",stdout);number(ratio);
    printf(",\"local_range_available\":%s,\"two_sigma_halfwidth\":",available?"true":"false");number(available?half:NAN);
    fputs(",\"two_sigma_relative_halfwidth\":",stdout);number(available&&point!=0?half/fabs(point):NAN);
    fputs(",\"local_range\":[",stdout);number(available?lo:NAN);putchar(',');number(available?hi:NAN);putchar(']');
    printf(",\"passes_reference_precision_screen\":%s,\"status\":\"%s\"}",
           available&&(logarithmic?half/fabs(point)<=.1:half<=.05)?"true":"false",
           available?"finite_fixed_chart_local":"unresolved");
}
static const char *candidate_class_name(int kind)
{
    static const char *names[]={"predetermined","full_joint_local_step","scaled_full_joint_local_step",
        "conditional_SOC_Q_minimizer","retained_eigenspace_likelihood_probe","gamma_minus_control"};
    return kind>=0&&kind<6?names[kind]:"invalid";
}
static int add_candidate(const char *name,int kind,double scale,int available,const double *delta,int d)
{
    unsigned k=candidate_count;
    if(k>=MAX_CANDIDATES)return -1;
    memcpy(input_candidates[k],delta,(size_t)d*sizeof(double));
    snprintf(candidate_names[k],sizeof(candidate_names[k]),"%s",name);
    candidate_classes[k]=kind;candidate_scales[k]=scale;candidate_available[k]=available;
    candidate_count++;return 0;
}
static int make_candidates(void)
{
    static const char *names[]={"zero","inside_R0","inside_SOC_Q","outside_Q","outside_SOC"};
    int i,j,k,d=diagnostic_assessment.joint_dimension,n=input_config.modes;
    int available=!diagnostic_assessment.matrix_invalid;char name[48];
    candidate_count=input_candidate_count;
    for(i=0;i<(int)input_candidate_count;i++) {
        if(i<5)snprintf(candidate_names[i],sizeof(candidate_names[i]),"%s",names[i]);
        else snprintf(candidate_names[i],sizeof(candidate_names[i]),"input_%d",i);
        candidate_classes[i]=0;candidate_scales[i]=1.;candidate_available[i]=1;
    }
    if(add_candidate("full_joint_step",1,1.,available,local_step,d))return -1;
    for(k=1;k<=8;k++) {
        double scale=ldexp(1.,-k);
        for(i=0;i<d;i++)target_gradient[i]=scale*local_step[i];
        snprintf(name,sizeof(name),"full_joint_step_over_%u",1u<<k);
        if(add_candidate(name,2,scale,available,target_gradient,d))return -1;
    }
    memset(target_gradient,0,sizeof(target_gradient));
    {
        int z=n+2,q=n+3;
        double a=diagnostic_fit.joint_normal[z*d+z],b=diagnostic_fit.joint_normal[z*d+q];
        double c=diagnostic_fit.joint_normal[q*d+q],det=a*c-b*b;
        int conditional=available&&isfinite(det)&&det>1e-14*fmax(a*c,1.);
        if(conditional) {
            target_gradient[z]=(-c*gradient[z]+b*gradient[q])/det;
            target_gradient[q]=(b*gradient[z]-a*gradient[q])/det;
        }
        if(add_candidate("conditional_SOC_Q_step",3,1.,conditional,target_gradient,d))return -1;
    }
    for(k=0;k<8;k++) {
        double norm=0;
        for(j=0;j<d;j++)if(diagnostic_assessment.eigenvalues[j]>diagnostic_assessment.eigen_cutoff)
            norm=hypot(norm,sin((double)((k+1)*(j+1))));
        memcpy(target_gradient,local_step,(size_t)d*sizeof(double));
        if(available&&norm>0)for(j=0;j<d;j++)if(diagnostic_assessment.eigenvalues[j]>diagnostic_assessment.eigen_cutoff) {
            double u=2.*sin((double)((k+1)*(j+1)))/(norm*sqrt(diagnostic_assessment.eigenvalues[j]));
            for(i=0;i<d;i++)target_gradient[i]+=diagnostic_work.vectors[i*d+j]*u;
        }
        snprintf(name,sizeof(name),"likelihood_direction_%d",k);
        if(add_candidate(name,4,1.,available&&norm>0,target_gradient,d))return -1;
    }
    memset(target_gradient,0,sizeof(target_gradient));
    target_gradient[n+1]=.5*input_config.radius[n+1];
    return add_candidate("gamma_minus_half_radius",5,.5,1,target_gradient,d);
}
static void region_json(double step_cost)
{
    double E=0,Lupper=step_cost+2.,B;int j;
    for(j=0;j<remainder_bank.pair_count;j++) {
        int p=remainder_bank.pair_row[j],q=remainder_bank.pair_column[j];
        E+=remainder_bank.coefficient[j]*input_config.radius[p]*input_config.radius[q]*(p==q?.5:1.);
    }
    B=sqrt(2.*fmax(0.,Lupper))*E+.5*E*E;
    fputs("\"region_bound\":{\"definition\":\"intersection_of_original_radius_box_physical_support_and_affine_NLL_at_most_attained_affine_step_cost_plus_2\",\"affine_step_cost\":",stdout);number(step_cost);
    fputs(",\"step_cost_is_global_minimum_claim\":false",stdout);
    fputs(",\"affine_NLL_upper\":",stdout);number(Lupper);
    fputs(",\"E_bound_over_radius_box\":",stdout);number(E);
    fputs(",\"B_bound_over_intersection\":",stdout);number(B);
    printf(",\"within_engineering_budget\":%s,\"all_box_points_claimed_low_loss\":false,\"null_directions_bounded_by_data\":false,\"coverage_validated\":false,\"arithmetic_validated\":false,\"full_rank\":%s}",
           isfinite(B)&&B<=nll_budget?"true":"false",diagnostic_assessment.numerical_rank==diagnostic_assessment.joint_dimension?"true":"false");
}
static int emit_candidate(const char *path,uint64_t count,const double *delta,int candidate_index)
{
    FILE *f=open_data(path);uint64_t index;int i,nt=scm_model_ntheta(input_config.modes);
    int na=scm_model_nalpha(input_config.modes),d=nt+na,feasible,guard,qr,nonzero=0,eligible,query_available;
    long double affine_cost=0,nonlinear_cost=0,signed_difference=0,error_norm=0,max_error=0;
    double factor_cost,actual_norm,upper;
    if(!f)return -1;
    for(i=0;i<d;i++)if(delta[i]!=0)nonzero=1;
    for(i=0;i<nt;i++)candidate_theta[i]=input_config.theta[i]+input_config.scale[i]*delta[i];
    for(i=0;i<na;i++) {
        candidate_alpha[i]=input_config.alpha[i]+input_config.scale[nt+i]*delta[nt+i];
        audit_alpha_precise[i]=(long double)input_config.alpha[i]+(long double)input_config.scale[nt+i]*delta[nt+i];
    }
    feasible=candidate_in_support();
    if(scm_model_init(&audit_anchor,input_config.modes,input_config.theta)){fclose(f);return -1;}
    if(feasible&&scm_model_init(&audit_candidate,input_config.modes,candidate_theta))feasible=0;
    for(index=0;index<count;index++) {
        scm_sample s;double unused_mu;long double mu_affine,mu_exact,ra,rn,error;
        if(read_sample(f,index,&s)||scm_model_step(&audit_anchor,&input_config.ocv,s.dt,s.current,&audit_anchor_row)||
           scm_model_predict(&audit_anchor_row,input_config.modes,input_config.alpha,&unused_mu,audit_theta_jac)) {
            fclose(f);return -1;
        }
        /* Equivalent affine expression places the exactly linear amplitude
         * terms in the same arithmetic order as the nonlinear replay. Long
         * double accumulation reduces subtraction error in large host costs;
         * this does not make the bounded core validated interval arithmetic.
         */
        mu_affine=(long double)audit_anchor_row.ocv;
        for(i=0;i<na;i++)mu_affine+=(long double)audit_anchor_row.X[i]*audit_alpha_precise[i];
        for(i=0;i<nt;i++)mu_affine+=(long double)audit_theta_jac[i]*input_config.scale[i]*delta[i];
        ra=(mu_affine-(long double)s.voltage)/(long double)input_config.sigma;
        affine_cost+=.5L*ra*ra;
        if(feasible) {
            if(scm_model_step(&audit_candidate,&input_config.ocv,s.dt,s.current,&audit_candidate_row))feasible=0;
            else {
                mu_exact=(long double)audit_candidate_row.ocv;
                for(i=0;i<na;i++)mu_exact+=(long double)audit_candidate_row.X[i]*audit_alpha_precise[i];
                rn=(mu_exact-(long double)s.voltage)/(long double)input_config.sigma;
                nonlinear_cost+=.5L*rn*rn;error=mu_exact-mu_affine;
                signed_difference+=.5L*((error/(long double)input_config.sigma)*(rn+ra));
                error_norm=hypotl(error_norm,error);max_error=fmaxl(max_error,fabsl(error));
            }
        }
    }
    if(fclose(f))return -1;
    guard=scm_evidence_check_candidate(&online_bank,delta);factor_cost=scm_evidence_factor_cost(&snapshot,delta);
    qr=scm_remainder_query(&remainder_bank,&online_bank,delta,nll_budget,&remainder_query);
    actual_norm=feasible?(double)(error_norm/(long double)input_config.sigma):NAN;
    query_available=qr==0&&(remainder_query.status==SCM_REMAINDER_WITHIN_ANALYTIC_BUDGET||remainder_query.status==SCM_REMAINDER_EXCEEDS_BUDGET);
    upper=query_available?remainder_query.affine_nll+remainder_query.nll_error_bound:NAN;
    eligible=qr==0&&candidate_available[candidate_index]&&nonzero&&guard==0&&
        remainder_query.status==SCM_REMAINDER_WITHIN_ANALYTIC_BUDGET&&
        online_bank.residual_flagged_events==0&&isfinite(upper)&&upper<checkpoint_anchor_cost;
    printf("{\"probe_name\":\"%s\",\"kind\":\"%s\",\"candidate_index\":%d,\"candidate_generation_available\":%s,\"step_scale\":",
           candidate_names[candidate_index],candidate_class_name(candidate_classes[candidate_index]),candidate_index,candidate_available[candidate_index]?"true":"false");number(candidate_scales[candidate_index]);
    fputs(",\"delta_scaled\":",stdout);array(delta,d);
    printf(",\"guard_code\":%d,\"guard\":\"%s\",\"guard_is_remainder_certificate\":false",guard,guard_name(guard));
    fputs(",\"factor_cost\":",stdout);number(factor_cost);
    fputs(",\"direct_affine_cost\":",stdout);number((double)affine_cost);
    fputs(",\"factor_minus_direct_affine\":",stdout);number(factor_cost-(double)affine_cost);
    printf(",\"exact_nonlinear_replay_available\":%s,\"exact_nonlinear_cost\":",feasible?"true":"false");number(feasible?(double)nonlinear_cost:NAN);
    fputs(",\"exact_minus_affine_cost\":",stdout);number(feasible?(double)signed_difference:NAN);
    fputs(",\"exact_minus_affine_by_cost_subtraction\":",stdout);number(feasible?(double)(nonlinear_cost-affine_cost):NAN);
    fputs(",\"actual_whitened_remainder_norm\":",stdout);number(actual_norm);
    fputs(",\"nonlinear_minus_affine_prediction_rms_V\":",stdout);number(feasible?(double)(error_norm/sqrtl((long double)count)):NAN);
    fputs(",\"nonlinear_minus_affine_prediction_max_V\":",stdout);number(feasible?(double)max_error:NAN);
    fputs(",\"theta\":",stdout);array(candidate_theta,nt);fputs(",\"alpha\":",stdout);array(candidate_alpha,na);
    fputs(",\"Q_Ah\":",stdout);number(feasible?exp(candidate_theta[input_config.modes+3]):NAN);
    fputs(",\"current_SOC\":",stdout);number(feasible?candidate_theta[input_config.modes+2]-online_bank.model.charge_Ah/exp(candidate_theta[input_config.modes+3]):NAN);
    printf(",\"remainder\":{\"query_return\":%d,\"status\":\"%s\",\"status_code\":%d,\"arithmetic_validated\":false,\"domain_code\":%d,\"affine_nll\":",
           qr,scm_remainder_status_name(remainder_query.status),remainder_query.status,remainder_query.domain_code);number(query_available?remainder_query.affine_nll:NAN);
    fputs(",\"E_bound\":",stdout);number(query_available?remainder_query.whitened_prediction_error_bound:NAN);
    fputs(",\"B_bound\":",stdout);number(query_available?remainder_query.nll_error_bound:NAN);
    fputs(",\"budget\":",stdout);number(nll_budget);
    fputs(",\"descent_upper_nll\":",stdout);number(upper);
    fputs(",\"prediction_bound_minus_observed\":",stdout);number(query_available?remainder_query.whitened_prediction_error_bound-actual_norm:NAN);
    fputs(",\"NLL_bound_minus_abs_observed\":",stdout);number(query_available&&feasible?remainder_query.nll_error_bound-fabs((double)signed_difference):NAN);
    printf(",\"eligible_update\":%s,\"is_nonzero_candidate\":%s,\"residual_flags_clear\":%s,\"update_applied\":false},",
           eligible?"true":"false",nonzero?"true":"false",online_bank.residual_flagged_events==0?"true":"false");
    fputs("\"scope\":\"host_audit_replays_input_no_online_relinearization\"}",stdout);return 0;
}
static int emit_checkpoint(const char *path,const char *label)
{
    const scm_evidence_config *c=&input_config;int nt=scm_model_ntheta(c->modes),na=scm_model_nalpha(c->modes),d=nt+na;
    int i,j,rc;double cost0,normal_residual=0,gradient_norm=0,Q,projection;
    if(scm_evidence_snapshot(&online_bank,&snapshot,&online_work))return -1;
    memset(&diagnostic_fit,0,sizeof(diagnostic_fit));
    rc=scm_evidence_factor_normal(&snapshot,diagnostic_fit.joint_normal,gradient,&cost0);if(rc)return rc;
    memcpy(diagnostic_fit.theta,c->theta,(size_t)nt*sizeof(double));
    memcpy(diagnostic_fit.alpha,c->alpha,(size_t)na*sizeof(double));
    memcpy(diagnostic_fit.coordinate_scales,c->scale,(size_t)d*sizeof(double));
    diagnostic_fit.charge_Ah=online_bank.model.charge_Ah;
    diagnostic_fit.elapsed_physical_s=online_bank.model.elapsed;
    diagnostic_fit.status=1; /* The nonlinear fit has not been performed. */
    if(!(online_bank.excitation&1u))diagnostic_fit.unexcited_theta_mask|=1u<<c->modes;
    if(!(online_bank.excitation&2u))diagnostic_fit.unexcited_theta_mask|=1u<<(c->modes+1);
    scm_assess_options_default(&diagnostic_options);
    rc=scm_assess(&diagnostic_fit,c->modes,&diagnostic_options,&diagnostic_assessment,&diagnostic_work);if(rc)return rc;
    memset(local_step,0,sizeof(local_step));
    if(!diagnostic_assessment.matrix_invalid)for(j=0;j<d;j++)if(diagnostic_assessment.eigenvalues[j]>diagnostic_assessment.eigen_cutoff) {
        projection=0;for(i=0;i<d;i++)projection+=diagnostic_work.vectors[i*d+j]*gradient[i];
        for(i=0;i<d;i++)local_step[i]-=diagnostic_work.vectors[i*d+j]*projection/diagnostic_assessment.eigenvalues[j];
    }
    for(i=0;i<d;i++) {
        double v=gradient[i];for(j=0;j<d;j++)v+=diagnostic_fit.joint_normal[i*d+j]*local_step[j];
        normal_residual=hypot(normal_residual,v);gradient_norm=hypot(gradient_norm,gradient[i]);
    }
    checkpoint_anchor_cost=cost0;
    if(make_candidates())return -1;
    printf("{\"label\":\"%s\",\"samples\":%" PRIu64 ",\"next_sample_index\":%" PRIu64 ",\"completed_events\":%" PRIu64,
           label,snapshot.samples,online_bank.next_index,online_bank.events_completed);
    printf(",\"active_event_samples\":%" PRIu64 ",\"excitation_mask\":%u,\"elapsed_s\":",online_bank.event.samples,online_bank.excitation);number(online_bank.model.elapsed);
    printf(",\"residual_monitor\":{\"limit_sigma\":%.17g,\"flagged_events\":%" PRIu64 ",\"last_event_samples\":%" PRIu64 ",\"last_event_anchor_rms_sigma\":",
           input_config.residual_rms_limit_sigma,online_bank.residual_flagged_events,online_bank.last_event_samples);
    number(online_bank.last_event_anchor_rms_sigma);
    fputs(",\"max_event_anchor_rms_sigma\":",stdout);number(online_bank.max_event_anchor_rms_sigma);
    fputs(",\"aggregate_anchor_rms_sigma\":",stdout);number(scm_evidence_factor_rms_sigma(&snapshot));
    fputs(",\"active_event_anchor_rms_sigma\":",stdout);number(scm_evidence_factor_rms_sigma(&online_bank.event));
    fputs(",\"action\":\"flag_only_no_evidence_removed\",\"historical_remainder_certificate\":false}",stdout);
    fputs(",\"charge_Ah\":",stdout);number(online_bank.model.charge_Ah);
    fputs(",\"zero_cost\":",stdout);number(cost0);
    fputs(",\"gram\":",stdout);array(diagnostic_fit.joint_normal,d*d);
    fputs(",\"gradient\":",stdout);array(gradient,d);
    fputs(",\"packed_factor\":",stdout);array(snapshot.upper,SCM_EVIDENCE_PACKED);
    printf(",\"numerical_rank\":%d,\"eigen_converged\":%s,\"matrix_invalid\":%s,\"eigen_cutoff\":",
           diagnostic_assessment.numerical_rank,diagnostic_assessment.eigen_converged?"true":"false",diagnostic_assessment.matrix_invalid?"true":"false");number(diagnostic_assessment.eigen_cutoff);
    fputs(",\"eigenvalues\":",stdout);array(diagnostic_assessment.eigenvalues,d);
    printf(",\"affine_solve_available\":%s,\"affine_solve_status\":\"%s\"",
           !diagnostic_assessment.matrix_invalid?"true":"false",
           !diagnostic_assessment.matrix_invalid?"minimum_norm_on_retained_eigenspace":"unavailable_invalid_matrix");
    fputs(",\"local_step\":",stdout);array(local_step,d);
    fputs(",\"normal_equation_residual_l2\":",stdout);number(normal_residual);
    fputs(",\"normal_equation_residual_relative\":",stdout);number(normal_residual/fmax(1.,gradient_norm));
    fputs(",\"affine_cost_reduction\":",stdout);number(cost0-scm_evidence_factor_cost(&snapshot,local_step));
    fputs(",\"nonlinear_optimizer_status\":\"not_run\",\"assessment_adapter_status\":1,\"coverage_validated\":false,\"gamma_minus_structural_status\":",stdout);
    printf("\"%s\",\"targets\":{",(online_bank.excitation&2u)?"excitation_present":"unexcited");
    Q=exp(c->theta[c->modes+3]);memset(target_gradient,0,sizeof(target_gradient));
    target_gradient[c->modes+3]=c->scale[c->modes+3];target_diagnostic("Q_Ah",1,Q);putchar(',');
    memset(target_gradient,0,sizeof(target_gradient));target_gradient[c->modes+2]=c->scale[c->modes+2];
    target_gradient[c->modes+3]=online_bank.model.charge_Ah/Q*c->scale[c->modes+3];
    target_diagnostic("current_SOC",0,c->theta[c->modes+2]-online_bank.model.charge_Ah/Q);fputs("},",stdout);
    if(audit_moments(path,snapshot.samples,cost0))return -1;
    printf(",\"remainder_summary\":{\"next_sample_index\":%" PRIu64 ",\"pair_count\":%d,\"pairs\":[",remainder_bank.next_index,remainder_bank.pair_count);
    for(j=0;j<remainder_bank.pair_count;j++) {
        if(j)putchar(',');
        printf("[%u,%u]",(unsigned)remainder_bank.pair_row[j],(unsigned)remainder_bank.pair_column[j]);
    }
    fputs("],\"coefficients\":",stdout);array(remainder_bank.coefficient,remainder_bank.pair_count);
    fputs(",\"last_hessian_bounds\":",stdout);array(remainder_bank.last_bound,remainder_bank.pair_count);
    fputs(",\"arithmetic_validated\":false},",stdout);
    region_json(scm_evidence_factor_cost(&snapshot,local_step));
    printf(",\"candidate_count\":%u,\"candidate_construction\":{\"likelihood_directions\":\"u_j=sin((k+1)*(j+1)), k=0..7, normalize_on_retained_eigenspace_then_delta=localstep+2*V*Lambda^-0.5*u\",\"likelihood_delta_target\":2,\"null_uncertainty_withheld\":true,\"all_steps_from_original_anchor\":true,\"conditional_solver_relative_determinant_floor\":1e-14}",candidate_count);
    fputs(",\"candidates\":[",stdout);
    for(i=0;i<(int)candidate_count;i++){if(i)putchar(',');if(emit_candidate(path,snapshot.samples,input_candidates[i],i))return -1;}
    fputs("]}",stdout);return 0;
}
static void memory_json(void)
{
    size_t candidates=sizeof(input_candidates),local=sizeof(gradient)+sizeof(local_step)+sizeof(target_gradient);
    size_t replay=sizeof(direct_normal)+sizeof(direct_gradient)+sizeof(audit_jacobian)+sizeof(candidate_theta)+sizeof(candidate_alpha)+
        sizeof(audit_anchor)+sizeof(audit_candidate)+sizeof(audit_anchor_row)+sizeof(audit_candidate_row)+sizeof(audit_theta_jac);
    size_t assessment=sizeof(diagnostic_fit)+sizeof(diagnostic_assessment)+sizeof(diagnostic_work)+sizeof(diagnostic_options);
    size_t remainder_bytes=sizeof(remainder_bank)+sizeof(remainder_work)+sizeof(remainder_query);
    size_t candidate_metadata=sizeof(candidate_names)+sizeof(candidate_classes)+sizeof(candidate_available)+sizeof(candidate_scales)+sizeof(input_candidate_count);
    size_t total=sizeof(input_config)+sizeof(online_bank)+sizeof(online_work)+sizeof(snapshot)+assessment+local+candidates+replay+
        sizeof(csv_line)+sizeof(source_hex)+sizeof(candidate_count)+remainder_bytes+candidate_metadata+sizeof(audit_alpha_precise)+sizeof(nll_budget)+sizeof(checkpoint_anchor_cost);
    printf("\"memory\":{\"bank_bytes\":%zu,\"config_bytes\":%zu,\"factor_bytes\":%zu,\"factor_numeric_payload_bytes\":%zu,\"update_workspace_bytes\":%zu,\"model_state_bytes\":%zu,\"model_row_bytes\":%zu,",
           sizeof(online_bank),sizeof(input_config),sizeof(snapshot),sizeof(snapshot.upper),sizeof(online_work),sizeof(scm_model_state),sizeof(scm_model_row));
    printf("\"online_bank_plus_workspace_bytes\":%zu,\"online_raw_history_bytes\":0,\"online_explicit_basis_bytes\":0,\"online_heap_bytes\":0,",
           sizeof(online_bank)+sizeof(online_work));
    printf("\"fit_result_bytes\":%zu,\"assessment_bytes\":%zu,\"assessment_workspace_bytes\":%zu,\"assessment_options_bytes\":%zu,",
           sizeof(diagnostic_fit),sizeof(diagnostic_assessment),sizeof(diagnostic_work),sizeof(diagnostic_options));
    printf("\"diagnostic_objects_bytes\":%zu,\"snapshot_output_bytes\":%zu,\"local_vector_arrays_bytes\":%zu,\"input_candidate_arrays_bytes\":%zu,\"host_replay_arrays_bytes\":%zu,\"csv_buffer_bytes\":%zu,\"probe_static_objects_sum_bytes\":%zu,",
           assessment,sizeof(snapshot),local,candidates,replay,sizeof(csv_line),total);
    printf("\"remainder_bank_bytes\":%zu,\"remainder_workspace_bytes\":%zu,\"remainder_query_result_bytes\":%zu,\"remainder_incremental_objects_bytes\":%zu,\"paired_ingestion_objects_bytes\":%zu,\"candidate_metadata_bytes\":%zu,\"host_precise_alpha_array_bytes\":%zu,\"host_long_double_bytes\":%zu,",
           sizeof(remainder_bank),sizeof(remainder_work),sizeof(remainder_query),remainder_bytes,sizeof(online_bank)+sizeof(online_work)+sizeof(remainder_bank)+sizeof(remainder_work),candidate_metadata,sizeof(audit_alpha_precise),sizeof(long double));
    fputs("\"accounting\":\"Host ABI sizeof sums; linker padding, stack, stdio/libm runtime and external OCV storage are additional. Host replay/diagnostics are separate from bounded ingestion.\",\"MCU_qualified\":false}",stdout);
}
int main(int argc,char **argv)
{
    FILE *f;uint64_t end,split,event_cap,index;int emitted=0,rc=1;
    if(argc!=7||parse_u64(argv[3],&end)||parse_u64(argv[4],&split)||parse_u64(argv[5],&event_cap)||parse_budget(argv[6])||
       !end||split>end||!event_cap) {
        fprintf(stderr,"Usage: %s DATA.csv ANCHOR.txt END_SAMPLES SPLIT_SAMPLES MAX_EVENT_SAMPLES BUDGET_NLL\n",argv[0]);return 2;
    }
    if(read_anchor(argv[2],event_cap))return 2;
    f=open_data(argv[1]);if(!f)return 2;
    printf("{\"schema\":\"mumble_remainder_probe_v1\",\"source_id\":\"%s\",\"modes\":%d,\"dimension\":%d,\"sigma_V\":",
           source_hex,input_config.modes,scm_model_ntheta(input_config.modes)+scm_model_nalpha(input_config.modes));number(input_config.sigma);
    printf(",\"event_cap_samples\":%" PRIu64 ",\"end_samples\":%" PRIu64 ",\"split_samples\":%" PRIu64 ",\"truth_used\":false,\"anchor_bootstrap\":\"external_not_implemented_in_probe\",\"bounded_cold_start_demonstrated\":false,",event_cap,end,split);
    fputs("\"arithmetic_validated\":false,\"budget_NLL\":",stdout);number(nll_budget);
    fputs(",\"host_replay_arithmetic\":\"double_state_propagation_and_analytic_theta_Jacobian;reordered_exact_linear_amplitude_terms_and_long_double_cost_accumulation\",",stdout);
    memory_json();fputs(",\"checkpoints\":[",stdout);
    for(index=0;index<end;index++) {
        scm_sample s;
        if(read_sample(f,index,&s))goto done;
        if(scm_remainder_evidence_push(&online_bank,&remainder_bank,input_config.source_id,index,&s,&online_work,&remainder_work)) {
            fprintf(stderr,"Evidence ingestion failed at sample %" PRIu64 "\n",index);goto done;
        }
        if(index+1==split&&split<end) {
            if(scm_evidence_seal(&online_bank,&online_work)||emit_checkpoint(argv[1],"split"))goto done;
            emitted=1;
        }
    }
    if(scm_evidence_seal(&online_bank,&online_work))goto done;
    if(emitted)putchar(',');
    if(emit_checkpoint(argv[1],"final"))goto done;
    fputs("]}\n",stdout);rc=0;
done:
    if(fclose(f)&&rc==0)rc=1;
    if(rc)fprintf(stderr,"Probe failed; output is incomplete and must not be accepted.\n");
    return rc;
}
