/* Three saved-checkpoint, one-step conditional-belief diagnostic.
 * No ingest/update API, fitting, source generation, or truth input is used.
 * The unchanged checkpoint codec and physical model remain authoritative.
 */
#define _POSIX_C_SOURCE 200809L
#include "scm_hypothesis_checkpoint.h"
#include <errno.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define D SCM_HYPOTHESIS_DIM
#define NODES (2 * D)
#define PACK(i,j) SCM_HYPOTHESIS_FACTOR_INDEX(i,j)
#define CENTER_V_TOL 1e-12
#define PROJECTION_TOL 2e-13
#define OBSERVATION_COUNT UINT64_C(504000)
#define FAILURE_FLAGS (SCM_ONLINE_FLAG_RECOVERY_REQUIRED | SCM_ONLINE_FLAG_MODEL_UNAVAILABLE | SCM_ONLINE_FLAG_MISSING_VOLTAGE | SCM_ONLINE_FLAG_UPDATE_REJECTED)

static const uint64_t checkpoint_indices[3] = {252000, 283500, 294000};
static const char *coordinate_names[D] = {
    "log_tau1", "log_tau2", "log_tau3", "log_gamma_plus", "log_gamma_minus", "log_Q_Ah",
    "R0_ohm", "R1_ohm", "R2_ohm", "R3_ohm", "H_V", "SOC", "v1_V", "v2_V", "v3_V", "h"
};
static double lower[D], upper[D];
static unsigned node_calls, center_calls;

typedef struct {
    int column, sign, propagated, model_code, post_available;
    unsigned pre_mask, post_mask;
    double pre[D], post[D], voltage, attempted_soc;
} point_result;

typedef struct {
    scm_hypothesis_component saved;
    point_result center, node[NODES];
    int center_valid, reference_valid, admissible;
    unsigned invalid_nodes, pre_invalid_nodes, post_invalid_nodes, propagated_nodes;
    double observation_gradient[D], chain_gradient[D], projected[D];
    double production_center_V, center_order_difference_V;
    double projected_direct_max_difference_V;
    double linear_clean_sd_V, linear_clean_variance_V2;
    double linear_predictive_variance_V2, linear_predictive_sd_V;
    double nonlinear_mean_V, nonlinear_clean_variance_V2, nonlinear_predictive_variance_V2;
    double mean_shift_physical_V, mean_shift_production_V, variance_shift_V2;
} component_result;

typedef struct {
    uint64_t checkpoint_index, observation_index;
    scm_sample input;
    double log_weights[2];
    int saved_state_unchanged;
    component_result component[2];
} snapshot_result;

/* Host diagnostics intentionally have their own storage, not estimator SRAM. */
static snapshot_result results[3];
static scm_hypothesis bank, immutable_bank;
static scm_hypothesis_workspace workspace;
static unsigned char checkpoint_buffer[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES];

static void number(double value)
{
    if(isfinite(value))printf("%.17g", value);
    else fputs("null", stdout);
}

static void string(const char *value)
{
    const unsigned char *p=(const unsigned char *)value;
    putchar('"');
    for(;*p;p++) {
        if(*p=='"'||*p=='\\'){putchar('\\');putchar(*p);}
        else if(*p<32)printf("\\u%04x",(unsigned)*p);
        else putchar(*p);
    }
    putchar('"');
}

static void vector(const double *values,size_t count)
{
    size_t i;putchar('[');
    for(i=0;i<count;i++){if(i)putchar(',');number(values[i]);}
    putchar(']');
}

static void named_number(const char *name,double value)
{putchar(',');string(name);putchar(':');number(value);}

static double factor(const scm_hypothesis_component *c,int row,int column)
{return column<=row?c->factor[PACK(row,column)]:0.;}

static unsigned domain_mask(const double point[D])
{
    unsigned mask=0;int i;
    for(i=0;i<D;i++)if(!isfinite(point[i])||point[i]<lower[i]||point[i]>upper[i])mask|=1u<<i;
    return mask;
}

static void make_physical(const double x[D],scm_physical *p,scm_physical_state *s)
{
    int i;memset(p,0,sizeof(*p));memset(s,0,sizeof(*s));p->modes=3;
    p->Q=exp(x[5]);p->gamma_plus=exp(x[3]);p->gamma_minus=exp(x[4]);
    p->R0=x[6];p->H=x[10];s->z=x[11];s->h=x[15];
    for(i=0;i<3;i++){p->tau[i]=exp(x[i]);p->R[i]=x[7+i];s->v[i]=x[12+i];}
}

static int point_valid(const point_result *point)
{return !point->pre_mask&&point->propagated&&point->model_code==0&&point->post_available&&!point->post_mask;}

static void propagate_point(point_result *point,const scm_sample *input,int is_center)
{
    scm_physical p;scm_physical_state state;int i;
    point->pre_mask=domain_mask(point->pre);
    if(point->pre_mask)return;
    make_physical(point->pre,&p,&state);
    point->attempted_soc=point->pre[11]-input->current*input->dt/(3600.*p.Q);
    point->propagated=1;
    if(is_center)center_calls++;else node_calls++;
    point->model_code=scm_physical_step(&p,&state,NULL,input->dt,input->current,&point->voltage);
    if(point->model_code)return; /* The physical API leaves state unchanged on error. */
    memcpy(point->post,point->pre,sizeof(point->post));
    point->post[11]=state.z;point->post[15]=state.h;
    for(i=0;i<3;i++)point->post[12+i]=state.v[i];
    point->post_available=1;point->post_mask=domain_mask(point->post);
    if(!isfinite(point->voltage))point->model_code=SCM_ERR_NONFINITE;
}

static void make_nodes(const scm_hypothesis_component *saved,point_result nodes[NODES])
{
    int column,sign_index,i;
    for(column=0;column<D;column++)for(sign_index=0;sign_index<2;sign_index++) {
        point_result *node=&nodes[2*column+sign_index];
        memset(node,0,sizeof(*node));node->column=column;node->sign=sign_index?-1:1;
        for(i=0;i<D;i++)node->pre[i]=saved->mean[i]+node->sign*4.*factor(saved,i,column);
        node->pre_mask=domain_mask(node->pre);
    }
}

/* Independent full-chain derivative; the propagated-factor evaluation below
 * follows the same nonzero arithmetic structure as scm_hypothesis.c:predict.
 * Neither calculation advances or mutates the saved learner.
 */
static int linear_reference(component_result *out,const scm_sample *input)
{
    const scm_hypothesis_component *saved=&out->saved;
    double F[D][D],predicted_factor[SCM_HYPOTHESIS_FACTOR_ENTRIES];
    double u,slope,charge,q,a,om,d_tau,d_R,d_gamma,current=input->current,dt=input->dt;
    double clean_sd=0.,predictive_sd=saved->config.sigma_V;
    int i,j,k,m;
    memset(F,0,sizeof(F));for(i=0;i<D;i++)F[i][i]=1.;
    memcpy(predicted_factor,saved->factor,sizeof(predicted_factor));
    charge=current*dt/(3600.*exp(saved->mean[5]));F[11][5]=charge;
    for(j=0;j<=11;j++)predicted_factor[PACK(11,j)]=factor(saved,11,j)+charge*factor(saved,5,j);
    for(i=0;i<3;i++) {
        k=12+i;q=dt/exp(saved->mean[i]);a=exp(-q);om=-expm1(-q);
        d_tau=q*a*(saved->mean[k]-saved->mean[7+i]*current);d_R=om*current;
        F[k][k]=a;F[k][i]=d_tau;F[k][7+i]=d_R;
        for(j=0;j<=k;j++)predicted_factor[PACK(k,j)]=a*factor(saved,k,j)+
            d_tau*factor(saved,i,j)+d_R*factor(saved,7+i,j);
    }
    if(current!=0&&dt!=0) {
        double sign=current>0?1.:-1.;k=current>0?3:4;
        q=exp(saved->mean[k])*(fabs(current)/3600.)*dt;a=exp(-q);
        d_gamma=-q*a*(saved->mean[15]-sign);F[15][15]=a;F[15][k]=d_gamma;
        for(j=0;j<D;j++)predicted_factor[PACK(15,j)]=a*factor(saved,15,j)+d_gamma*factor(saved,k,j);
    }
    if(scm_ocv_eval(NULL,out->center.post[11],&u,&slope))return -1;
    out->production_center_V=u-out->center.post[6]*current-out->center.post[12]-
        out->center.post[13]-out->center.post[14]-out->center.post[10]*out->center.post[15];
    out->center_order_difference_V=out->center.voltage-out->production_center_V;
    out->observation_gradient[6]=-current;out->observation_gradient[10]=-out->center.post[15];
    out->observation_gradient[11]=slope;
    out->observation_gradient[12]=out->observation_gradient[13]=out->observation_gradient[14]=-1.;
    out->observation_gradient[15]=-out->center.post[10];
    for(j=0;j<D;j++)for(i=0;i<D;i++)out->chain_gradient[j]+=out->observation_gradient[i]*F[i][j];
    for(j=0;j<D;j++) {
        double value=0.,direct=0.;
        for(i=j;i<D;i++)value+=predicted_factor[PACK(i,j)]*out->observation_gradient[i];
        for(m=j;m<D;m++)direct+=out->chain_gradient[m]*factor(saved,m,j);
        out->projected[j]=value;
        out->projected_direct_max_difference_V=fmax(out->projected_direct_max_difference_V,fabs(value-direct));
        clean_sd=hypot(clean_sd,value);
    }
    for(j=D-1;j>=0;j--)predictive_sd=hypot(predictive_sd,out->projected[j]);
    out->linear_clean_sd_V=clean_sd;out->linear_clean_variance_V2=clean_sd*clean_sd;
    out->linear_predictive_variance_V2=out->linear_clean_variance_V2+saved->config.sigma_V*saved->config.sigma_V;
    out->linear_predictive_sd_V=predictive_sd;
    if(!isfinite(out->production_center_V)||!isfinite(out->linear_predictive_variance_V2)||
       !isfinite(predictive_sd)||!isfinite(out->projected_direct_max_difference_V))return -1;
    if(fabs(out->center_order_difference_V)>CENTER_V_TOL||
       out->projected_direct_max_difference_V>PROJECTION_TOL)return -1;
    return 0;
}

static void compensated_add(double value,double *sum,double *correction)
{
    double y=value-*correction,t=*sum+y;*correction=(t-*sum)-y;*sum=t;
}

static void evaluate_component(component_result *out,const scm_hypothesis_component *saved,const scm_sample *input)
{
    double sum=0.,correction=0.,variance=0.,variance_correction=0.,shift;
    int i;
    memset(out,0,sizeof(*out));out->saved=*saved;
    out->center.column=-1;memcpy(out->center.pre,saved->mean,sizeof(out->center.pre));
    propagate_point(&out->center,input,1);out->center_valid=point_valid(&out->center);
    if(out->center_valid)out->reference_valid=linear_reference(out,input)==0;
    make_nodes(saved,out->node); /* Generate and precheck all 32 before propagation. */
    for(i=0;i<NODES;i++) {
        point_result *node=&out->node[i];
        if(!node->pre_mask)propagate_point(node,input,0);
        out->propagated_nodes+=(unsigned)node->propagated;
        if(node->pre_mask)out->pre_invalid_nodes++;
        else if(!point_valid(node))out->post_invalid_nodes++;
        if(!point_valid(node))out->invalid_nodes++;
    }
    out->admissible=out->center_valid&&out->reference_valid&&out->invalid_nodes==0;
    if(!out->admissible)return; /* Never form a moment from a partial node set. */
    for(i=0;i<NODES;i++)compensated_add(out->node[i].voltage-out->center.voltage,&sum,&correction);
    shift=sum/NODES;out->mean_shift_physical_V=shift;
    out->nonlinear_mean_V=out->center.voltage+shift;
    out->mean_shift_production_V=out->center_order_difference_V+shift;
    for(i=0;i<NODES;i++) {
        double residual=(out->node[i].voltage-out->center.voltage)-shift;
        compensated_add(residual*residual,&variance,&variance_correction);
    }
    out->nonlinear_clean_variance_V2=variance/NODES;
    out->nonlinear_predictive_variance_V2=out->nonlinear_clean_variance_V2+saved->config.sigma_V*saved->config.sigma_V;
    out->variance_shift_V2=out->nonlinear_clean_variance_V2-out->linear_clean_variance_V2;
    if(!isfinite(out->nonlinear_mean_V)||!isfinite(out->nonlinear_clean_variance_V2)||
       !isfinite(out->nonlinear_predictive_variance_V2)||!isfinite(out->variance_shift_V2)) {
        out->reference_valid=0;out->admissible=0;
    }
}

static void emit_failure(const char *stage,int coordinate,double value,int code)
{
    fputs("{\"stage\":",stdout);string(stage);printf(",\"model_code\":%d,\"coordinate\":",code);
    if(coordinate>=0) {
        printf("%d,\"coordinate_name\":",coordinate);string(coordinate_names[coordinate]);
        named_number("value",value);named_number("lower",lower[coordinate]);named_number("upper",upper[coordinate]);
        named_number("lower_margin",value-lower[coordinate]);named_number("upper_margin",upper[coordinate]-value);
    } else fputs("null",stdout);
    putchar('}');
}

static void emit_point(const point_result *point)
{
    int i,first=1;
    printf("{\"column\":%d,\"sign\":%d,\"weight\":%.17g,\"pre_state\":",point->column,point->sign,point->column<0?0.:1./NODES);
    vector(point->pre,D);printf(",\"pre_failure_mask\":%u,\"propagated\":%s",point->pre_mask,point->propagated?"true":"false");
    fputs(",\"post_state\":",stdout);if(point->post_available)vector(point->post,D);else fputs("null",stdout);
    printf(",\"post_failure_mask\":%u,\"model_code\":",point->post_mask);
    if(point->propagated)printf("%d",point->model_code);else fputs("null",stdout);
    fputs(",\"voltage_V\":",stdout);if(point_valid(point))number(point->voltage);else fputs("null",stdout);
    fputs(",\"attempted_SOC\":",stdout);if(point->propagated)number(point->attempted_soc);else fputs("null",stdout);
    printf(",\"admitted\":%s,\"failures\":[",point_valid(point)?"true":"false");
    for(i=0;i<D;i++)if(point->pre_mask&(1u<<i)) {
        if(!first)putchar(',');
        emit_failure("pre_chart_domain",i,point->pre[i],0);first=0;
    }
    if(point->propagated&&point->model_code) {
        int coordinate=(!isfinite(point->attempted_soc)||point->attempted_soc<lower[11]||point->attempted_soc>upper[11])?11:-1;
        if(!first)putchar(',');
        emit_failure("physical_step_domain_or_numeric",coordinate,point->attempted_soc,point->model_code);first=0;
    }
    for(i=0;i<D;i++)if(point->post_mask&(1u<<i)) {
        if(!first)putchar(',');
        emit_failure("post_chart_domain",i,point->post[i],0);first=0;
    }
    fputs("]}",stdout);
}

static void emit_component(const component_result *out,unsigned component)
{
    int i;printf("{\"component\":%u,\"saved_mean\":",component);vector(out->saved.mean,D);
    fputs(",\"saved_lower_factor_packed_by_row\":",stdout);vector(out->saved.factor,SCM_HYPOTHESIS_FACTOR_ENTRIES);
    named_number("sigma_V",out->saved.config.sigma_V);
    printf(",\"center_valid\":%s,\"linear_reference_valid\":%s,\"moment_rule_admissible\":%s",
           out->center_valid?"true":"false",out->reference_valid?"true":"false",out->admissible?"true":"false");
    printf(",\"node_count\":%d,\"node_propagations\":%u,\"invalid_nodes\":%u,\"pre_invalid_nodes\":%u,\"post_invalid_nodes\":%u,\"center\":",
           NODES,out->propagated_nodes,out->invalid_nodes,out->pre_invalid_nodes,out->post_invalid_nodes);
    emit_point(&out->center);
    fputs(",\"linearized\":",stdout);
    if(out->center_valid) {
        fputs("{\"mean_V\":",stdout);number(out->production_center_V);
        named_number("physical_center_V",out->center.voltage);
        named_number("physical_minus_production_order_V",out->center_order_difference_V);
        named_number("center_order_tolerance_V",CENTER_V_TOL);
        named_number("clean_sd_V",out->linear_clean_sd_V);
        named_number("clean_variance_V2",out->linear_clean_variance_V2);
        named_number("predictive_variance_V2",out->linear_predictive_variance_V2);
        named_number("predictive_sd_from_hypot_V",out->linear_predictive_sd_V);
        named_number("direct_chain_vs_propagated_factor_max_V",out->projected_direct_max_difference_V);
        fputs(",\"observation_gradient_at_predicted_center\":",stdout);vector(out->observation_gradient,D);
        fputs(",\"chain_gradient_at_saved_center\":",stdout);vector(out->chain_gradient,D);
        fputs(",\"projected_factor_V\":",stdout);vector(out->projected,D);putchar('}');
    } else fputs("null",stdout);
    fputs(",\"nonlinear_moments\":",stdout);
    if(out->admissible) {
        fputs("{\"mean_V\":",stdout);number(out->nonlinear_mean_V);
        named_number("clean_variance_V2",out->nonlinear_clean_variance_V2);
        named_number("predictive_variance_V2",out->nonlinear_predictive_variance_V2);
        named_number("mean_shift_vs_physical_center_V",out->mean_shift_physical_V);
        named_number("mean_shift_vs_production_center_V",out->mean_shift_production_V);
        named_number("variance_shift_V2",out->variance_shift_V2);putchar('}');
    } else fputs("null",stdout);
    fputs(",\"nodes\":[",stdout);for(i=0;i<NODES;i++){if(i)putchar(',');emit_point(&out->node[i]);}fputs("]}",stdout);
}

static uint64_t get64(const unsigned char *bytes)
{uint64_t value=0;unsigned i;for(i=0;i<8;i++)value|=(uint64_t)bytes[i]<<(8*i);return value;}

static double get_double(const unsigned char *bytes)
{uint64_t bits=get64(bytes);double value;memcpy(&value,&bits,sizeof(value));return value;}

static int read_observation(FILE *source,uint64_t expected,scm_sample *input,uint64_t *actual)
{
    unsigned char bytes[32];
    if(expected>(uint64_t)INT64_MAX/32||fseeko(source,(off_t)(expected*32),SEEK_SET)||fread(bytes,1,sizeof(bytes),source)!=sizeof(bytes))return -1;
    *actual=get64(bytes);if(*actual!=expected)return -2;
    input->dt=get_double(bytes+8);input->current=get_double(bytes+16);input->voltage=get_double(bytes+24);
    if(!isfinite(input->dt)||input->dt<=0||input->dt>1||!isfinite(input->current)||fabs(input->current)>.25||!isfinite(input->voltage))return -3;
    return 0;
}

static int hex_digit(char c)
{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}

static int source_identity(const char *text,unsigned char id[SCM_ONLINE_SOURCE_BYTES])
{
    unsigned i;if(strlen(text)!=2*SCM_ONLINE_SOURCE_BYTES)return -1;
    for(i=0;i<SCM_ONLINE_SOURCE_BYTES;i++){int a=hex_digit(text[2*i]),b=hex_digit(text[2*i+1]);if(a<0||b<0)return -1;id[i]=(unsigned char)(16*a+b);}
    return 0;
}

static int parse_index(const char *text,uint64_t *value)
{
    unsigned long long parsed;char *end;
    if(!*text||*text=='+'||*text=='-')return -1;
    errno=0;parsed=strtoull(text,&end,10);if(errno||*end||parsed>UINT64_MAX)return -1;
    *value=(uint64_t)parsed;return 0;
}

static int fail(const char *stage,int code,uint64_t index)
{
    fputs("{\"schema\":\"mumble_conditional_belief_probe_v1\",\"status\":\"failed\",\"failure_stage\":",stdout);
    string(stage);printf(",\"code\":%d,\"index\":%" PRIu64 ",\"node_propagations\":%u,\"center_propagations\":%u}\n",code,index,node_calls,center_calls);
    return 1;
}

/* Fabricated, independent central derivatives of the unchanged physical step.
 * These calls are qualification work, never canonical checkpoint evaluations.
 */
static int derivative_self_test(scm_hypothesis_component *toy,double *max_derivative_error,
                                double *max_variance_error,int *unchanged)
{
    const double currents[3]={.06,-.06,0.},step=1e-5;
    scm_hypothesis_component original=*toy;
    component_result reference;point_result points[2];scm_sample input={.125,0.,3.8};
    double derivative[D],variance,p;
    int c,i,j,k,s,ok=1;
    *max_derivative_error=0.;*max_variance_error=0.;
    for(c=0;c<3;c++) {
        input.current=currents[c];memset(&reference,0,sizeof(reference));reference.saved=*toy;
        reference.center.column=-1;memcpy(reference.center.pre,toy->mean,sizeof(toy->mean));
        propagate_point(&reference.center,&input,1);
        if(!point_valid(&reference.center)||linear_reference(&reference,&input))return 0;
        for(i=0;i<D;i++) {
            for(s=0;s<2;s++) {
                memset(&points[s],0,sizeof(points[s]));points[s].column=i;points[s].sign=s?-1:1;
                memcpy(points[s].pre,toy->mean,sizeof(toy->mean));points[s].pre[i]+=(s?-step:step);
                propagate_point(&points[s],&input,0);
                if(!point_valid(&points[s]))return 0;
            }
            derivative[i]=(points[0].voltage-points[1].voltage)/(2*step);
            *max_derivative_error=fmax(*max_derivative_error,fabs(derivative[i]-reference.chain_gradient[i]));
        }
        variance=0.;
        for(i=0;i<D;i++)for(j=0;j<D;j++) {
            p=0.;for(k=0;k<D;k++)p+=factor(toy,i,k)*factor(toy,j,k);
            variance+=derivative[i]*p*derivative[j];
        }
        *max_variance_error=fmax(*max_variance_error,fabs(variance-reference.linear_clean_variance_V2));
        if(fabs(variance-reference.linear_clean_variance_V2)>2e-15+2e-10*fabs(variance))ok=0;
    }
    *unchanged=memcmp(&original,toy,sizeof(original))==0;
    return ok&&*max_derivative_error<=2e-8&&*unchanged;
}

static int wrong_index_self_test(void)
{
    unsigned char wrong_record[32]={1};uint64_t actual=UINT64_MAX;
    scm_sample input;FILE *file=tmpfile();int rc,ok;
    unsigned before_nodes=node_calls,before_centers=center_calls;
    if(!file)return 0;
    if(fwrite(wrong_record,1,sizeof(wrong_record),file)!=sizeof(wrong_record)||fflush(file)) {
        fclose(file);return 0;
    }
    rc=read_observation(file,0,&input,&actual);
    ok=rc==-2&&actual==1&&node_calls==before_nodes&&center_calls==before_centers;
    if(fclose(file))return 0;
    return ok;
}

static int self_test(void)
{
    scm_hypothesis_config config;scm_hypothesis toy;
    component_result result;scm_sample input={1./35.,0.,3.8};
    double expected_variance,derivative_error,variance_error;
    int linear_ok,zero_ok,boundary_ok,post_ok,dense_ok=1,derivative_ok,wrong_index_ok,unchanged=0;
    int i,j,k;point_result nodes[NODES];
    scm_hypothesis_config_default(&config);
    if(scm_hypothesis_init(&toy,&config,SCM_HYPOTHESIS_COINCIDENT))return fail("self_test_init",-1,0);
    memset(toy.component[0].factor,0,sizeof(toy.component[0].factor));
    toy.component[0].mean[12]=.01;toy.component[0].factor[PACK(12,12)]=.001;
    evaluate_component(&result,&toy.component[0],&input);
    expected_variance=.000001*exp(-2*input.dt/exp(toy.component[0].mean[0]));
    linear_ok=result.admissible&&fabs(result.mean_shift_production_V)<=1e-13&&
        fabs(result.nonlinear_clean_variance_V2-expected_variance)<=1e-16&&
        fabs(result.linear_clean_variance_V2-expected_variance)<=1e-16;
    memset(toy.component[0].factor,0,sizeof(toy.component[0].factor));
    evaluate_component(&result,&toy.component[0],&input);
    zero_ok=result.admissible&&result.nonlinear_clean_variance_V2==0&&
        result.nonlinear_predictive_variance_V2==config.sigma_V*config.sigma_V;
    toy.component[0].mean[15]=1.;toy.component[0].factor[PACK(15,15)]=1e-5;
    evaluate_component(&result,&toy.component[0],&input);
    boundary_ok=!result.admissible&&result.center_valid&&result.pre_invalid_nodes==1&&result.propagated_nodes==31&&
        result.node[30].pre_mask==(1u<<15);
    memset(toy.component[0].factor,0,sizeof(toy.component[0].factor));
    toy.component[0].mean[15]=0;toy.component[0].mean[11]=.001;toy.component[0].factor[PACK(11,11)]=.0002;
    input.dt=1.;input.current=.1;
    evaluate_component(&result,&toy.component[0],&input);
    post_ok=!result.admissible&&result.center_valid&&result.pre_invalid_nodes==0&&result.post_invalid_nodes==1&&
        result.node[23].model_code==SCM_ERR_DOMAIN&&result.node[23].attempted_soc<0;
    for(i=0;i<D;i++)for(j=0;j<=i;j++)toy.component[0].factor[PACK(i,j)]=(i==j?2.:(i+j)%2?-.25:.3)*1e-7;
    make_nodes(&toy.component[0],nodes);
    for(i=0;i<D;i++) {
        double mean=0.;for(k=0;k<NODES;k++)mean+=nodes[k].pre[i]/NODES;
        if(fabs(mean-toy.component[0].mean[i])>2e-13)dense_ok=0;
    }
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        double actual=0.,expected=0.;
        for(k=0;k<NODES;k++)actual+=(nodes[k].pre[i]-toy.component[0].mean[i])*(nodes[k].pre[j]-toy.component[0].mean[j])/NODES;
        for(k=0;k<D;k++)expected+=factor(&toy.component[0],i,k)*factor(&toy.component[0],j,k);
        if(fabs(actual-expected)>1e-20)dense_ok=0;
    }
    toy.component[0].mean[11]=.47;toy.component[0].mean[15]=.2;
    toy.component[0].mean[12]=.01;toy.component[0].mean[13]=-.02;toy.component[0].mean[14]=.005;
    for(i=0;i<D;i++)for(j=0;j<=i;j++)toy.component[0].factor[PACK(i,j)]=(i==j?2.:(i+j)%2?-.25:.3)*1e-4;
    derivative_ok=derivative_self_test(&toy.component[0],&derivative_error,&variance_error,&unchanged);
    wrong_index_ok=wrong_index_self_test();
    printf("{\"schema\":\"mumble_conditional_belief_preflight_v1\",\"passed\":%s,\"checks\":{\"linear_voltage_moments\":%s,\"zero_covariance\":%s,\"pre_domain_boundary\":%s,\"post_domain_SOC\":%s,\"dense_factor_node_mean_covariance\":%s,\"positive_negative_zero_current_derivatives_and_dense_covariance\":%s,\"wrong_observation_index_rejected_without_propagation\":%s,\"saved_component_unchanged\":%s},\"derivative_step\":1e-5,\"derivative_abs_tolerance\":2e-8,\"maximum_derivative_error\":%.17g,\"maximum_variance_error_V2\":%.17g,\"fixture_node_propagations\":%u,\"fixture_center_propagations\":%u,\"canonical_data_read\":false}\n",
        linear_ok&&zero_ok&&boundary_ok&&post_ok&&dense_ok&&derivative_ok&&wrong_index_ok?"true":"false",linear_ok?"true":"false",zero_ok?"true":"false",boundary_ok?"true":"false",post_ok?"true":"false",dense_ok?"true":"false",derivative_ok?"true":"false",wrong_index_ok?"true":"false",unchanged?"true":"false",derivative_error,variance_error,node_calls,center_calls);
    return linear_ok&&zero_ok&&boundary_ok&&post_ok&&dense_ok&&derivative_ok&&wrong_index_ok?0:1;
}

int main(int argc,char **argv)
{
    const char *source_text=NULL,*observation_path=NULL,*paths[3]={NULL,NULL,NULL};
    scm_hypothesis_config config;FILE *observations=NULL;struct stat st;
    int i,j,rc,valid=1;unsigned inadmissible=0;
    scm_hypothesis_bounds(lower,upper);
    if(sizeof(double)!=8||DBL_MANT_DIG!=53||DBL_MAX_EXP!=1024)return fail("binary64_platform",-1,0);
    if(argc==2&&!strcmp(argv[1],"--self-test"))return self_test();
    for(i=1;i<argc;i++) {
        if(!strcmp(argv[i],"--source-id")&&i+1<argc){if(source_text)return fail("duplicate_source",-1,0);source_text=argv[++i];}
        else if(!strcmp(argv[i],"--observations")&&i+1<argc){if(observation_path)return fail("duplicate_observations",-1,0);observation_path=argv[++i];}
        else if(!strcmp(argv[i],"--checkpoint")&&i+2<argc) {
            uint64_t n;if(parse_index(argv[++i],&n))return fail("checkpoint_index_argument",-1,0);
            for(j=0;j<3&&checkpoint_indices[j]!=n;j++){}
            if(j==3||paths[j])return fail("checkpoint_index_set",-1,n);
            paths[j]=argv[++i];
        } else return fail("arguments",-1,0);
    }
    if(!source_text||!observation_path||!paths[0]||!paths[1]||!paths[2])return fail("required_arguments",-1,0);
    scm_hypothesis_config_default(&config);if(source_identity(source_text,config.source_id))return fail("source_id",-1,0);
    observations=fopen(observation_path,"rb");if(!observations)return fail("open_observations",errno,0);
    if(fstat(fileno(observations),&st)||!S_ISREG(st.st_mode)||st.st_size<0||
       (uintmax_t)st.st_size!=OBSERVATION_COUNT*32) {
        fclose(observations);return fail("observation_extent",-1,0);
    }
    /* Validate every checkpoint and every next observation before propagation. */
    for(i=0;i<3;i++) {
        snapshot_result *out=&results[i];out->checkpoint_index=checkpoint_indices[i];
        rc=scm_hypothesis_checkpoint_restore(&bank,&config,paths[i],&workspace,checkpoint_buffer);
        if(rc){fclose(observations);return fail("checkpoint_restore",rc,checkpoint_indices[i]);}
        for(j=0;j<2;j++)if(bank.component[j].next_index!=checkpoint_indices[i]||bank.component[j].flags&FAILURE_FLAGS) {
            fclose(observations);return fail("checkpoint_index_or_state",-1,checkpoint_indices[i]);
        }
        rc=read_observation(observations,checkpoint_indices[i],&out->input,&out->observation_index);
        if(rc){fclose(observations);return fail("next_observation",rc,checkpoint_indices[i]);}
        for(j=0;j<2;j++){out->component[j].saved=bank.component[j];out->log_weights[j]=bank.log_weight[j];}
    }
    if(fclose(observations))return fail("close_observations",errno,0);
    for(i=0;i<3;i++) {
        snapshot_result *out=&results[i];
        memset(&immutable_bank,0,sizeof(immutable_bank));
        for(j=0;j<2;j++)immutable_bank.component[j]=out->component[j].saved;
        for(j=0;j<2;j++) {
            evaluate_component(&out->component[j],&immutable_bank.component[j],&out->input);
            if(!out->component[j].admissible)inadmissible++;
            if(!out->component[j].center_valid||!out->component[j].reference_valid)valid=0;
        }
        out->saved_state_unchanged=1;
        for(j=0;j<2;j++)if(memcmp(&immutable_bank.component[j],&out->component[j].saved,sizeof(scm_hypothesis_component)))out->saved_state_unchanged=0;
        if(!out->saved_state_unchanged)valid=0;
    }
    if(node_calls>192||center_calls>6)valid=0;
    fputs("{\"schema\":\"mumble_conditional_belief_probe_v1\",\"status\":",stdout);
    string(!valid?"failed_reference_or_center":inadmissible?"completed_with_inadmissible_components":"completed_all_components_admissible");
    fputs(",\"source_id\":",stdout);string(source_text);
    printf(",\"node_rule\":\"mu +/-4*L[:,k]; 32 equal weights1/32\",\"node_propagations\":%u,\"center_propagations\":%u,\"inadmissible_components\":%u,\"new_learner_updates\":0,\"source_generations\":0,\"truth_inputs\":0,\"lower\":",node_calls,center_calls,inadmissible);
    vector(lower,D);fputs(",\"upper\":",stdout);vector(upper,D);fputs(",\"coordinate_names\":[",stdout);
    for(i=0;i<D;i++){if(i)putchar(',');string(coordinate_names[i]);}
    fputs("],\"snapshots\":[",stdout);
    for(i=0;i<3;i++) {
        snapshot_result *out=&results[i];if(i)putchar(',');
        printf("{\"checkpoint_next_index\":%" PRIu64 ",\"observation_index\":%" PRIu64 ",\"predicted_next_index\":%" PRIu64,
               out->checkpoint_index,out->observation_index,out->checkpoint_index+1);
        named_number("nominal_checkpoint_s",out->checkpoint_index/35.);named_number("dt_s",out->input.dt);
        named_number("current_A",out->input.current);named_number("observed_voltage_V",out->input.voltage);
        printf(",\"saved_state_unchanged\":%s,\"log_weights\":",out->saved_state_unchanged?"true":"false");vector(out->log_weights,2);
        fputs(",\"components\":[",stdout);for(j=0;j<2;j++){if(j)putchar(',');emit_component(&out->component[j],(unsigned)j);}fputs("]}",stdout);
    }
    fputs("],\"scope\":\"Local deterministic moment/domain diagnostic only. Inadmissible node sets have no nonlinear moments. No clipping, dropping, replacement, renormalization, covariance inflation or coverage claim.\"}\n",stdout);
    if(fflush(stdout)||ferror(stdout))return 2;
    return valid?0:1;
}
