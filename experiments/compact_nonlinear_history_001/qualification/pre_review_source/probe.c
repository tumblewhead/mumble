/* Bounded external host qualification harness. The two candidate banks each
 * receive one chronological ADC-style stream. Exact oracle state, snapshots,
 * trace retention and file I/O below are host test machinery, never candidate
 * memory or candidate feedback. See the frozen plan for the one-run bounds.
 */
#include "compact_history.h"
#include <errno.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define FIXED_POINTS 42
#define ARMS 2
#define CHECKPOINTS 2
#define TRACE_CAP (CH_MAX_ROUNDS * (CH_FRACTIONS + 1))

typedef struct {
    double x[CH_DIM], alpha[SCM_MAX_ALPHA];
    scm_model_state state;
    double cost_sum, cost_correction;
    uint64_t model_steps, records_accumulated, first_unavailable_index;
    int status, initialized;
} exact_point;

typedef struct {
    int status;
    double cost, endpoint_x[CH_DIM];
    uint64_t model_steps, records_accumulated, first_unavailable_index;
} exact_snapshot;

typedef struct { int status; double cost; } cost_snapshot;
typedef struct { ch_result result; double x[CH_DIM]; } trace_event;

typedef struct {
    int refine_status, report_status, endpoint_status, trace_overflow;
    unsigned trace_count;
    uint32_t refinement_stop;
    double candidate_x[CH_DIM];
    ch_result before, after, endpoint;
    uint64_t model_steps, qr_rows, query_evaluations, prior_evaluations;
    uint64_t proposal_rounds, accepted_steps;
    cost_snapshot fixed[FIXED_POINTS][2];
    trace_event trace[TRACE_CAP];
} arm_snapshot;

typedef struct {
    uint64_t next_index;
    int complete;
    arm_snapshot arms[ARMS];
    exact_snapshot points[FIXED_POINTS];
} checkpoint;

typedef struct {
    ch_context banks[ARMS];
    exact_point oracle[FIXED_POINTS];
    checkpoint checkpoints[CHECKPOINTS];
    scm_model_row oracle_row;
    unsigned char record[32], source[32];
    uint64_t records_read, input_bytes_read, trial_evaluations;
    unsigned checkpoints_count, point_count;
    int failure_code;
    const char *failure_stage;
} host_harness;

static host_harness host;
static const char *arm_name[ARMS] = {"public_origin", "autonomous_origin"};

static void number(double x) { if(isfinite(x)) printf("%.17g",x); else fputs("null",stdout); }
static void vector(const double *x, unsigned n)
{ unsigned i; putchar('['); for(i=0;i<n;i++){if(i)putchar(',');number(x[i]);} putchar(']'); }

static uint64_t little_u64(const unsigned char *p)
{ unsigned i; uint64_t v=0; for(i=0;i<8;i++)v|=(uint64_t)p[i]<<(8*i);return v; }
static double little_double(const unsigned char *p)
{ uint64_t bits=little_u64(p);double v;memcpy(&v,&bits,8);return v; }

static int parse_source(const char *s)
{
    unsigned i;
    if(strlen(s)!=64)return -1;
    for(i=0;i<32;i++) {
        unsigned a=(unsigned char)s[2*i],b=(unsigned char)s[2*i+1];
        if(!((a>='0'&&a<='9')||(a>='a'&&a<='f')) ||
           !((b>='0'&&b<='9')||(b>='a'&&b<='f')))return -1;
        a=a<='9'?a-'0':a-'a'+10;b=b<='9'?b-'0':b-'a'+10;
        host.source[i]=(unsigned char)(16*a+b);
    }
    return 0;
}

static int supported_entering(const double *x)
{
    unsigned i;
    for(i=0;i<CH_DIM;i++)if(!isfinite(x[i])||x[i]<ch_lower[i]||x[i]>ch_upper[i])return 0;
    return 1;
}

static int initialize_exact(exact_point *p)
{
    double theta[SCM_MAX_THETA];unsigned i;
    p->first_unavailable_index=UINT64_MAX;
    if(!supported_entering(p->x)){p->status=CH_ERR_DOMAIN; p->first_unavailable_index=0; return 0;}
    for(i=0;i<5;i++)theta[i]=p->x[i];
    theta[5]=p->x[11];theta[6]=p->x[5];
    p->alpha[0]=p->x[6];for(i=0;i<3;i++){p->alpha[1+i]=p->x[7+i];p->alpha[5+i]=p->x[12+i];}
    p->alpha[4]=p->x[10];p->alpha[8]=p->x[10]*p->x[15];
    p->status=scm_model_init(&p->state,3,theta);
    if(p->status!=SCM_OK)return -1;
    p->initialized=1;return 0;
}

static int read_points(const char *path,unsigned count)
{
    FILE *f=fopen(path,"r");unsigned i,j;char extra[2];int extra_status;
    if(!f)return -1;
    for(i=0;i<count;i++)for(j=0;j<CH_DIM;j++){
        if(fscanf(f,"%lf",&host.oracle[i].x[j])!=1 || !isfinite(host.oracle[i].x[j])){fclose(f);return -1;}
    }
    extra_status=fscanf(f,"%1s",extra);
    if(extra_status!=EOF || ferror(f)){fclose(f);return -1;}
    if(fclose(f))return -1;
    host.point_count=count;
    for(i=0;i<count;i++)if(initialize_exact(&host.oracle[i]))return -1;
    return 0;
}

/* Exact original-model evaluation has no access to a candidate bank. */
static int advance_exact(exact_point *p,const scm_sample *s,uint64_t index,int allow_domain)
{
    double mu,res,value,t;int rc;
    if(p->status!=SCM_OK)return 0;
    p->model_steps++;
    rc=scm_model_step(&p->state,NULL,s->dt,s->current,&host.oracle_row);
    if(rc!=SCM_OK){p->status=rc;p->first_unavailable_index=index;return allow_domain&&rc==SCM_ERR_DOMAIN?0:-1;}
    rc=scm_model_predict(&host.oracle_row,3,p->alpha,&mu,NULL);
    if(rc!=SCM_OK){p->status=rc;p->first_unavailable_index=index;return -1;}
    res=(mu-s->voltage)/CH_SIGMA;value=0.5*res*res;
    if(!isfinite(value)){p->status=CH_ERR_NONFINITE;p->first_unavailable_index=index;return -1;}
    t=p->cost_sum+value;
    if(fabs(p->cost_sum)>=fabs(value))p->cost_correction+=(p->cost_sum-t)+value;
    else p->cost_correction+=(value-t)+p->cost_sum;
    p->cost_sum=t;p->records_accumulated++;
    return isfinite(p->cost_sum)&&isfinite(p->cost_correction)?0:-1;
}

static void snapshot_exact(const exact_point *p,exact_snapshot *o)
{
    unsigned j;memset(o,0,sizeof(*o));o->status=p->status;
    o->model_steps=p->model_steps;o->records_accumulated=p->records_accumulated;
    o->first_unavailable_index=p->first_unavailable_index;
    if(p->status!=SCM_OK)return;
    o->cost=p->cost_sum+p->cost_correction;memcpy(o->endpoint_x,p->x,sizeof(o->endpoint_x));
    o->endpoint_x[11]=p->state.z0-p->state.charge_Ah/p->state.Q;
    for(j=0;j<3;j++)o->endpoint_x[12+j]=p->x[7+j]*p->state.f[j]+p->x[12+j]*p->state.a[j];
    o->endpoint_x[15]=p->state.hb+p->x[15]*p->state.ha;
}

static void trace(const ch_context *c,void *user)
{
    arm_snapshot *s=user;trace_event *event;
    if(c->result.fraction!=UINT32_MAX)host.trial_evaluations++;
    if(s->trace_count>=TRACE_CAP){s->trace_overflow=1;return;}
    event=&s->trace[s->trace_count++];event->result=c->result;
    memcpy(event->x,c->workspace.query.point,sizeof(event->x));
}

static int checkpoint_now(uint64_t next_index)
{
    unsigned a,p,k;checkpoint *s;
    if(host.checkpoints_count>=CHECKPOINTS)return -1;
    s=&host.checkpoints[host.checkpoints_count++];s->next_index=next_index;
    for(p=0;p<host.point_count;p++)snapshot_exact(&host.oracle[p],&s->points[p]);
    for(a=0;a<ARMS;a++){
        ch_context *c=&host.banks[a];arm_snapshot *out=&s->arms[a];
        memcpy(c->workspace.query.point,c->bank.estimate,sizeof(c->bank.estimate));
        if(ch_query(c,CH_QUARTIC,CH_NO_CURVATURE,CH_EXACT_PRIOR)!=CH_OK)return -2;
        out->before=c->result;
        out->refine_status=ch_refine(c,CH_MAX_ROUNDS,trace,out);
        out->refinement_stop=c->result.stop_reason;
        if(out->refine_status<0 || out->trace_overflow)return -3;
        memcpy(out->candidate_x,c->bank.estimate,sizeof(out->candidate_x));
        memcpy(c->workspace.query.point,c->bank.estimate,sizeof(c->bank.estimate));
        out->report_status=ch_query(c,CH_QUARTIC,CH_NO_CURVATURE,CH_EXACT_PRIOR);
        out->after=c->result;
        if(out->report_status!=CH_OK)return -4;
        out->endpoint_status=ch_endpoint(c);out->endpoint=c->result;
        if(out->endpoint_status!=CH_OK)return -5;
        for(p=0;p<host.point_count;p++)for(k=0;k<2;k++){
            cost_snapshot *v=&out->fixed[p][k];
            memcpy(c->workspace.query.point,host.oracle[p].x,sizeof(host.oracle[p].x));
            v->status=ch_query(c,k==0?CH_AFFINE:CH_QUARTIC,CH_NO_CURVATURE,CH_NO_PRIOR);
            if(v->status==CH_OK)v->cost=c->result.likelihood_cost;
            else if(v->status!=CH_ERR_DOMAIN)return -6;
        }
        out->model_steps=c->bank.model_steps;out->qr_rows=c->bank.qr_rows;
        out->query_evaluations=c->bank.query_evaluations;out->prior_evaluations=c->bank.prior_evaluations;
        out->proposal_rounds=c->bank.proposal_rounds;out->accepted_steps=c->bank.accepted_steps;
    }
    s->complete=1;return 0;
}

static void print_cost(const ch_result *r)
{
    fputs("{\"likelihood_cost\":",stdout);number(r->likelihood_cost);
    fputs(",\"prior_cost\":",stdout);number(r->prior_cost);
    fputs(",\"total_cost\":",stdout);number(r->total_cost);
    fputs(",\"cost_absolute_scale\":",stdout);number(r->cost_absolute_scale);
    printf(",\"flags\":%u}",r->flags);
}

static void print_exact(unsigned index,const exact_snapshot *s)
{
    printf("{\"index\":%u,\"x\":",index);vector(host.oracle[index].x,CH_DIM);
    printf(",\"status\":\"%s\",\"status_code\":%d,\"model_steps\":%" PRIu64 ",\"records_accumulated\":%" PRIu64,
           s->status==SCM_OK?"available":"unavailable",s->status,s->model_steps,s->records_accumulated);
    fputs(",\"first_unavailable_index\":",stdout);
    if(s->first_unavailable_index==UINT64_MAX)fputs("null",stdout);else printf("%" PRIu64,s->first_unavailable_index);
    fputs(",\"cost\":",stdout);if(s->status==SCM_OK)number(s->cost);else fputs("null",stdout);
    fputs(",\"endpoint_x\":",stdout);if(s->status==SCM_OK)vector(s->endpoint_x,CH_DIM);else fputs("null",stdout);
    putchar('}');
}

static void print_arm(unsigned a,const arm_snapshot *s)
{
    unsigned i,k;
    printf("{\"arm\":\"%s\",\"candidate_x\":",arm_name[a]);vector(s->candidate_x,CH_DIM);
    printf(",\"refine_status\":%d,\"refinement_stop\":%u,\"report_status\":%d,\"endpoint_status\":%d,\"before\":",
           s->refine_status,s->refinement_stop,s->report_status,s->endpoint_status);print_cost(&s->before);
    fputs(",\"after\":",stdout);print_cost(&s->after);
    fputs(",\"endpoint\":{\"SOC\":",stdout);number(s->endpoint.detail.endpoint.SOC);
    fputs(",\"v\":",stdout);vector(s->endpoint.detail.endpoint.v,3);
    fputs(",\"h\":",stdout);number(s->endpoint.detail.endpoint.h);
    printf(",\"flags\":%u,\"SOC_exact_given_entering_x\":true,\"RC_h_second_order\":true}",s->endpoint.flags);
    printf(",\"counts\":{\"model_steps\":%" PRIu64 ",\"qr_rows\":%" PRIu64 ",\"query_evaluations\":%" PRIu64
           ",\"prior_evaluations\":%" PRIu64 ",\"proposal_rounds\":%" PRIu64 ",\"accepted_steps\":%" PRIu64 "}",
           s->model_steps,s->qr_rows,s->query_evaluations,s->prior_evaluations,s->proposal_rounds,s->accepted_steps);
    fputs(",\"fixed_points\":[",stdout);
    for(i=0;i<host.point_count;i++){
        if(i)putchar(',');
        printf("{\"index\":%u",i);
        for(k=0;k<2;k++){
            printf(",\"%s\":{\"status_code\":%d,\"cost\":",k==0?"affine":"quartic",s->fixed[i][k].status);
            if(s->fixed[i][k].status==CH_OK)number(s->fixed[i][k].cost);else fputs("null",stdout);putchar('}');
        }putchar('}');
    }
    fputs("],\"trace\":[",stdout);
    for(i=0;i<s->trace_count;i++){
        const trace_event *t=&s->trace[i];const ch_result *r=&t->result;
        if(i)putchar(',');
        printf("{\"event\":\"%s\",\"round\":%u,\"fraction\":",
                               r->fraction==UINT32_MAX?"proposal":"trial",r->round);
        if(r->fraction==UINT32_MAX)fputs("null",stdout);else printf("%u",r->fraction);
        fputs(",\"x\":",stdout);vector(t->x,CH_DIM);fputs(",\"cost\":",stdout);print_cost(r);
        printf(",\"stop_reason\":%u,\"step\":{\"slope\":",r->stop_reason);number(r->detail.step.slope);
        fputs(",\"slope_allowance\":",stdout);number(r->detail.step.slope_allowance);
        fputs(",\"model_decrease\":",stdout);number(r->detail.step.model_decrease);
        fputs(",\"model_allowance\":",stdout);number(r->detail.step.model_allowance);
        fputs(",\"cost_decrease\":",stdout);number(r->detail.step.cost_decrease);
        fputs(",\"cost_allowance\":",stdout);number(r->detail.step.cost_allowance);
        fputs(",\"armijo_required\":",stdout);number(r->detail.step.armijo_required);
        fputs(",\"combine_allowance\":",stdout);number(r->detail.step.combine_allowance);
        fputs(",\"alpha\":",stdout);number(r->detail.step.alpha);fputs("}}",stdout);
    }
    fputs("]}",stdout);
}

static void print_result(int primary,uint64_t prefix,const char *source_id,double cpu_s)
{
    uint64_t models=0,prior=0,queries=0,rounds=0,accepted=0,candidate_models=0,oracle_models=0;
    unsigned a,p,k;
    for(a=0;a<ARMS;a++){
        const ch_bank *b=&host.banks[a].bank;candidate_models+=b->model_steps;
        prior+=b->prior_evaluations;queries+=b->query_evaluations;rounds+=b->proposal_rounds;accepted+=b->accepted_steps;
    }
    for(p=0;p<host.point_count;p++)oracle_models+=host.oracle[p].model_steps;
    models=candidate_models+oracle_models;
    printf("{\"schema\":\"mumble_compact_nonlinear_history_%s_v1\",\"status\":\"%s\",\"source_id\":\"%s\",\"prefix_records\":%" PRIu64,
           primary?"primary":"audit",host.failure_code?"failed":"completed",source_id,prefix);
    printf(",\"failure_code\":%d,\"failure_stage\":\"%s\",\"counts\":{\"counts_complete\":true,\"records_read\":%" PRIu64
           ",\"input_bytes_read\":%" PRIu64 ",\"model_steps\":%" PRIu64 ",\"candidate_model_steps\":%" PRIu64
           ",\"oracle_model_steps\":%" PRIu64 ",\"prior_evaluations\":%" PRIu64 ",\"query_evaluations\":%" PRIu64
           ",\"proposal_rounds\":%" PRIu64 ",\"trial_evaluations\":%" PRIu64 ",\"accepted_steps\":%" PRIu64
           ",\"truth_reads\":0,\"source_generations\":0,\"learner_calls\":0,\"original_fitter_calls\":0},\"CPU_self_s\":",
           host.failure_code,host.failure_stage?host.failure_stage:"none",host.records_read,host.input_bytes_read,
           models,candidate_models,oracle_models,prior,queries,rounds,host.trial_evaluations,accepted);
    number(cpu_s);
    printf(",\"storage\":{\"candidate_factor_bytes\":%zu,\"candidate_bank_bytes\":%zu,\"candidate_jet_bytes\":%zu,\"candidate_workspace_bytes\":%zu,"
           "\"candidate_result_bytes\":%zu,\"candidate_sample_bytes\":%zu,\"candidate_core_bytes\":%zu,\"candidate_operational_layout_bytes\":%zu,"
           "\"ADC_reserve_bytes\":%u,\"checkpoint_codec_reserve_bytes\":%u,\"own_stack_planning_cap_bytes\":%u,\"runtime_IRQ_caller_reserve_bytes\":%u,"
           "\"candidate_planned_total_bytes\":%zu,\"target_budget_bytes\":10240,\"candidate_raw_history_bytes\":0,\"candidate_explicit_heap_allocations\":0,"
           "\"host_harness_static_bytes\":%zu,\"host_oracle_array_bytes\":%zu,\"host_snapshots_bytes\":%zu,\"target_stack_and_timing_measured\":false}",
           sizeof(host.banks[0].bank.upper),sizeof(ch_bank),sizeof(ch_jet),sizeof(ch_workspace),sizeof(ch_result),sizeof(scm_sample),sizeof(ch_context),
           sizeof(ch_operational_layout),CH_ADC_RESERVE_BYTES,CH_CODEC_RESERVE_BYTES,CH_OWN_STACK_CAP_BYTES,CH_RUNTIME_IRQ_CALLER_RESERVE_BYTES,
           sizeof(ch_operational_layout)+CH_OWN_STACK_CAP_BYTES+CH_RUNTIME_IRQ_CALLER_RESERVE_BYTES,
           sizeof(host),sizeof(host.oracle),sizeof(host.checkpoints));
    if(primary){
        fputs(",\"checkpoints\":[",stdout);
        for(k=0;k<host.checkpoints_count;k++){
            const checkpoint *s=&host.checkpoints[k];if(k)putchar(',');
            printf("{\"next_index\":%" PRIu64 ",\"complete\":%s,\"arms\":[",s->next_index,s->complete?"true":"false");
            for(a=0;a<ARMS;a++){if(a)putchar(',');print_arm(a,&s->arms[a]);}
            fputs("],\"oracle\":{\"points\":[",stdout);
            for(p=0;p<host.point_count;p++){if(p)putchar(',');print_exact(p,&s->points[p]);}
            fputs("]}}",stdout);
        }putchar(']');
    }else{
        fputs(",\"points\":[",stdout);
        for(p=0;p<host.point_count;p++){exact_snapshot out;snapshot_exact(&host.oracle[p],&out);if(p)putchar(',');print_exact(p,&out);}putchar(']');
    }
    fputs("}\n",stdout);
}

int main(int argc,char **argv)
{
    const char *mode=NULL,*observations=NULL,*points=NULL,*source_id="",*prefix_text=NULL;
    uint64_t prefix=0,index;unsigned i,p,a,seen=0;int primary=0,rc=0;char *end=NULL;FILE *input=NULL;clock_t started=clock();
    if(sizeof(double)!=8 || DBL_MANT_DIG!=53 || FLT_RADIX!=2){host.failure_code=-1;host.failure_stage="binary64_platform";goto done;}
    for(i=1;i+1<(unsigned)argc;i+=2){
        unsigned bit=0;
        if(!strcmp(argv[i],"--mode")){bit=1;mode=argv[i+1];}
        else if(!strcmp(argv[i],"--observations")){bit=2;observations=argv[i+1];}
        else if(!strcmp(argv[i],"--prefix")){bit=4;prefix_text=argv[i+1];}
        else if(!strcmp(argv[i],"--points")){bit=8;points=argv[i+1];}
        else if(!strcmp(argv[i],"--source-id")){bit=16;source_id=argv[i+1];}
        if(!bit || (seen&bit)){host.failure_code=-2;host.failure_stage="arguments";goto done;}seen|=bit;
    }
    if(argc!=11 || seen!=31){host.failure_code=-2;host.failure_stage="arguments";goto done;}
    primary=!strcmp(mode,"primary");
    errno=0;prefix=strtoull(prefix_text,&end,10);
    if(errno || !end || *end || (!primary&&strcmp(mode,"audit")) ||
       (primary&&prefix!=294000) || (!primary&&prefix!=252000&&prefix!=294000) || parse_source(source_id)){
        host.failure_code=-2;host.failure_stage="arguments";goto done;
    }
    if(read_points(points,primary?FIXED_POINTS:ARMS)){host.failure_code=-3;host.failure_stage="fixed_points";goto done;}
    if(primary){
        for(i=0;i<CH_DIM;i++)if(host.oracle[0].x[i]!=ch_public_mean[i]){host.failure_code=-4;host.failure_stage="public_origin_identity";goto done;}
        if(ch_init(&host.banks[0],host.source,ch_public_mean)!=CH_OK || ch_init(&host.banks[1],host.source,host.oracle[1].x)!=CH_OK){
            host.failure_code=-5;host.failure_stage="candidate_initialize";goto done;
        }
    }else for(p=0;p<host.point_count;p++)if(host.oracle[p].status!=SCM_OK){host.failure_code=-5;host.failure_stage="audit_point_support";goto done;}
    input=fopen(observations,"rb");if(!input){host.failure_code=-6;host.failure_stage="input_open";goto done;}
    for(index=0;index<prefix;index++){
        scm_sample sample;size_t n=fread(host.record,1,32,input);host.input_bytes_read+=n;
        if(n!=32){host.failure_code=-7;host.failure_stage="input_read";goto done;}host.records_read++;
        sample.dt=little_double(host.record+8);sample.current=little_double(host.record+16);sample.voltage=little_double(host.record+24);
        if(little_u64(host.record)!=index || !isfinite(sample.dt)||sample.dt<0||sample.dt>1 ||
           !isfinite(sample.current)||fabs(sample.current)>.25 || !isfinite(sample.voltage)){
            host.failure_code=-8;host.failure_stage="input_contract";goto done;
        }
        if(primary)for(a=0;a<ARMS;a++){
            host.banks[a].sample=sample;rc=ch_push(&host.banks[a],host.source,index);
            if(rc!=CH_OK){host.failure_code=rc;host.failure_stage="candidate_push";goto done;}
        }
        for(p=0;p<host.point_count;p++)if(advance_exact(&host.oracle[p],&sample,index,primary)){
            host.failure_code=-9;host.failure_stage="exact_reference_step";goto done;
        }
        if(primary&&(index+1==252000||index+1==294000)){
            rc=checkpoint_now(index+1);if(rc){host.failure_code=rc;host.failure_stage="compact_checkpoint";goto done;}
        }
    }
done:
    if(input&&fclose(input)&&!host.failure_code){host.failure_code=-10;host.failure_stage="input_close";}
    /* source_id comes from verified supervisor input. Invalid CLI strings are
     * never echoed into JSON where they could corrupt a failed capture. */
    if(strlen(source_id)!=64 || parse_source(source_id))source_id="";
    print_result(primary,prefix,source_id,(double)(clock()-started)/CLOCKS_PER_SEC);
    if(fflush(stdout)||ferror(stdout))return 3;
    return host.failure_code?2:0;
}
