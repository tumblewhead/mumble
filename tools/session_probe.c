/* Small host lifecycle driver for M1. The immutable input source is checked by
 * the Python runner. This program sees observations and public configuration
 * only; it never reads synthetic truth or adds an old-posterior factor. */
#include "scm_session_checkpoint.h"
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static scm_session session;
static scm_assessment assessment;
static scm_assess_workspace assessment_workspace;
static scm_session_query_result query;
static char csv_line[4096];

static void number(double x) { if(isfinite(x)) printf("%.17g",x); else fputs("null",stdout); }
static void string(const char *s)
{
    const unsigned char *p=(const unsigned char*)s;
    putchar('"');
    for(;*p;p++) {
        if(*p=='"'||*p=='\\') {putchar('\\');putchar(*p);}
        else if(*p<32) printf("\\u%04x",*p);
        else putchar(*p);
    }
    putchar('"');
}
static void named(const char *name,double x) { putchar(',');string(name);putchar(':');number(x); }
static void array(const char *name,const double *x,int n)
{
    int i;putchar(',');string(name);fputs(":[",stdout);
    for(i=0;i<n;i++){if(i)putchar(',');number(x[i]);}putchar(']');
}
static const char *space(const char *p) {while(isspace((unsigned char)*p))p++;return p;}
static int count(const char *text,uint64_t *value)
{
    char *end;unsigned long long v;text=space(text);
    if(!*text||*text=='-')return -1;
    errno=0;v=strtoull(text,&end,10);
    if(errno||end==text||*space(end)||v>UINT64_MAX)return -1;
    *value=(uint64_t)v;return 0;
}
static int count_list(const char *text,uint64_t *values,unsigned *length)
{
    char token[32];const char *end;size_t n;unsigned k=0;
    if(!*text){*length=0;return 0;}
    while(*text) {
        end=strchr(text,',');n=end?(size_t)(end-text):strlen(text);
        if(!n||n>=sizeof(token)||k>=SCM_SESSION_MAX_CHECKPOINTS)return -1;
        memcpy(token,text,n);token[n]=0;
        if(count(token,&values[k])||!values[k]||(k&&values[k]<=values[k-1]))return -1;
        k++;if(!end)break;text=end+1;if(!*text)return -1;
    }
    *length=k;return 0;
}
static int hex_digit(char c)
{
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return c-'a'+10;
    if(c>='A'&&c<='F')return c-'A'+10;
    return -1;
}
static int source_id(const char *text,unsigned char *id)
{
    int i,a,b;if(strlen(text)!=2*SCM_SESSION_SOURCE_BYTES)return -1;
    for(i=0;i<SCM_SESSION_SOURCE_BYTES;i++) {
        a=hex_digit(text[2*i]);b=hex_digit(text[2*i+1]);if(a<0||b<0)return -1;
        id[i]=(unsigned char)(16*a+b);
    }
    return 0;
}
static FILE *open_data(const char *path)
{
    FILE *f=fopen(path,"r");size_t n;if(!f)return NULL;
    if(!fgets(csv_line,sizeof(csv_line),f)){fclose(f);return NULL;}
    n=strlen(csv_line);while(n&&(csv_line[n-1]=='\n'||csv_line[n-1]=='\r'))csv_line[--n]=0;
    if(strcmp(csv_line,"sample_index,dt_s,current_A,voltage_V")){fclose(f);return NULL;}
    return f;
}
static int read_sample(FILE *f,uint64_t expected,scm_sample *sample)
{
    const char *p;char *end;unsigned long long index;double v[3];int i;
    if(!fgets(csv_line,sizeof(csv_line),f))return -1;
    if(!strchr(csv_line,'\n')&&!feof(f))return -1;
    p=space(csv_line);if(!*p||*p=='-')return -1;errno=0;index=strtoull(p,&end,10);
    if(errno||end==p||index>UINT64_MAX||(uint64_t)index!=expected)return -1;
    p=space(end);if(*p++!=',')return -1;
    for(i=0;i<3;i++) {
        errno=0;v[i]=strtod(p,&end);
        if(errno||end==p||!isfinite(v[i]))return -1;
        p=space(end);if(i<2){if(*p++!=',')return -1;}else if(*p)return -1;
    }
    if(v[0]<0)return -1;
    sample->dt=v[0];sample->current=v[1];sample->voltage=v[2];return 0;
}
static void emit_target(const scm_assess_target *t)
{
    fputs("{\"name\":",stdout);string(t->name);fputs(",\"units\":",stdout);string(t->units);
    fputs(",\"status\":",stdout);string(scm_assess_status_name(t->status));
    printf(",\"status_code\":%d,\"reasons\":%u",t->status,t->reasons);
#define TNUM(field) named(#field,t->field)
    TNUM(point);TNUM(lower);TNUM(upper);TNUM(support_lower);TNUM(support_upper);
    TNUM(null_projection);TNUM(local_standard_deviation);TNUM(local_halfwidth);TNUM(relative_halfwidth);
#undef TNUM
#define TINT(field) printf(",\"" #field "\":%d",t->field)
    TINT(point_available);TINT(has_local_range);TINT(has_relative_halfwidth);
    TINT(passes_local_precision);TINT(eligible_for_profile_check);
    TINT(active_constraints_present);TINT(conditioned_fit);
#undef TINT
    putchar('}');
}
static int emit_query(const char *reason)
{
    int rc=scm_session_query(&session,&query,&assessment,&assessment_workspace);
    if(rc)return rc;
    printf("{\"event\":\"query\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"reason\":",query.next_index,query.epoch_begin);
    string(reason);fputs(",\"state\":{\"status\":",stdout);string(scm_session_status_name(query.status));
    printf(",\"status_code\":%d,\"flags\":%u",query.status,query.flags);
#define Q64(field) printf(",\"" #field "\":%" PRIu64,query.field)
    Q64(epoch_begin);Q64(next_index);Q64(evidence_next_index);Q64(evidence_age_samples);
    Q64(cold_resets);Q64(fit_attempts);Q64(fit_results);Q64(last_fit_attempt_index);
#undef Q64
#define QNUM(field) named(#field,query.field)
    QNUM(elapsed_s);QNUM(epoch_elapsed_s);QNUM(epoch_charge_Ah);
    QNUM(current_soc);QNUM(capacity_Ah);QNUM(predicted_voltage_V);
#undef QNUM
#define QINT(field) printf(",\"" #field "\":%d",query.field)
    QINT(point_available);QINT(capacity_available);QINT(voltage_prediction_available);
    QINT(assessment_available);QINT(optimizer_status);QINT(last_fit_code);
    QINT(fit_due);QINT(fitting_available);QINT(evidence_current);
#undef QINT
    printf(",\"history_samples\":%zu},\"assessment\":",query.history_samples);
    if(!query.assessment_available)fputs("null",stdout);
    else {
        printf("{\"numerical_rank\":%d,\"eigen_converged\":%d,\"matrix_invalid\":%d,\"optimizer_status\":%d,\"uncertainty_type\":\"local_likelihood_no_validated_coverage\",\"current_soc\":",
            assessment.numerical_rank,assessment.eigen_converged,assessment.matrix_invalid,assessment.optimizer_status);
        emit_target(&assessment.targets[3*session.config.modes+7]);
        fputs(",\"capacity_Ah\":",stdout);emit_target(&assessment.targets[session.config.modes+3]);putchar('}');
    }
    printf(",\"resources\":{\"history_capacity\":%zu,\"owned_bytes\":%zu,\"peak_owned_bytes\":%zu,\"last_problem_auxiliary_bytes\":%zu,\"peak_fit_owned_bytes\":%zu}}\n",
        query.history_capacity,query.owned_bytes,query.peak_owned_bytes,query.last_problem_auxiliary_bytes,query.peak_fit_owned_bytes);
    return ferror(stdout)?-1:0;
}
static void emit_fit(int rc,int has_initial)
{
    const scm_fit_result *r=&session.fit;int nt=scm_model_ntheta(session.config.modes),na=scm_model_nalpha(session.config.modes),d=nt+na;
    printf("{\"event\":\"fit\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"returncode\":%d,\"fit\":",session.next_index,session.epoch_begin,rc);
    if(rc){fputs("null}\n",stdout);return;}
    printf("{\"method\":\"full\",\"modes\":%d,\"has_initial\":%s,\"fixed_mask\":0,\"fixed_alpha_mask\":0,\"has_current_soc\":false,\"fixed_current_soc\":null,\"ocv_kind\":\"illustrative_known_curve\",\"ocv_table_rows\":0",session.config.modes,has_initial?"true":"false");
    named("sigma_V",session.config.sigma);array("theta",r->theta,nt);array("alpha",r->alpha,na);
#define FNUM(field) named(#field,r->field)
    FNUM(objective);FNUM(objective_full);FNUM(voltage_rmse);FNUM(elapsed_cpu_s);
    FNUM(projected_gradient);FNUM(max_inner_kkt);FNUM(basis_seconds);
    FNUM(basis_max_orthogonality);FNUM(max_discarded_column_norm);FNUM(elapsed_physical_s);FNUM(charge_Ah);
#undef FNUM
#define FINT(field) printf(",\"" #field "\":%d",r->field)
    FINT(status);FINT(termination_reason);FINT(iterations);FINT(evaluations);
    FINT(converged_starts);FINT(starts);FINT(active_linear_constraints);FINT(active_outer_bounds);
#undef FINT
#define FSIZE(field) printf(",\"" #field "\":%zu",r->field)
    FSIZE(samples);FSIZE(features);FSIZE(blocks);FSIZE(data_bytes);FSIZE(basis_bytes);
    FSIZE(payload_bytes);FSIZE(workspace_bytes);FSIZE(retained_bytes);FSIZE(setup_peak_bytes);
#undef FSIZE
    printf(",\"unexcited_theta_mask\":%u,\"joint_normal_dimension\":%d,\"joint_normal_semantics\":\"Scaled likelihood Jacobian Gram before damping and Schur reduction; not a posterior\",\"joint_normal_coordinates\":\"Scaled theta followed by scaled alpha; packed row-major\"",r->unexcited_theta_mask,d);
    array("coordinate_scales",r->coordinate_scales,d);array("joint_normal",r->joint_normal,d*d);fputs("}}\n",stdout);
}
static int error(const char *operation,int rc)
{
    fputs("{\"event\":\"error\",\"operation\":",stdout);string(operation);
    printf(",\"code\":%d,\"next_index\":%" PRIu64 "}\n",rc,session.next_index);fflush(stdout);
    fprintf(stderr,"%s failed (code %d, next_index %" PRIu64 ")\n",operation,rc,session.next_index);
    return EXIT_FAILURE;
}
static void help(void)
{
    puts("Usage: scm_session_probe --data FILE --source SHA256_HEX --end N\n"
         "  --checkpoint-prefix PREFIX --save-at COUNT,COUNT --query-stride N\n"
         "  --fit-budget N [--restore FILE] [--cold-reset]\n"
         "Uses frozen M1 public defaults: 3RC, sigma=.001, starts=3, maxiter=120,\n"
         "fits at absolute sample counts350,31500,63000,73500; no truth input.");
}
int main(int argc,char **argv)
{
    scm_session_config config;scm_sample sample;FILE *data=NULL;
    const char *data_path=NULL,*source=NULL,*prefix=NULL,*restore=NULL,*save_text="";
    uint64_t end=0,stride=350,budget=0,actual_fits=0,save_at[SCM_SESSION_MAX_CHECKPOINTS],i,start;
    unsigned save_count=0,save_cursor=0;int j,rc=EXIT_FAILURE,cold=0,fit_rc,has_initial,had_fit;char path[4096];
    scm_session_config_default(&config);
    for(j=1;j<argc;j++) {
        const char *option=argv[j];
        if(!strcmp(option,"--help")){help();return EXIT_SUCCESS;}
        if(!strcmp(option,"--cold-reset")){cold=1;continue;}
        if(j+1>=argc)return error("missing_argument",-1);
        if(!strcmp(option,"--data"))data_path=argv[++j];
        else if(!strcmp(option,"--source"))source=argv[++j];
        else if(!strcmp(option,"--checkpoint-prefix"))prefix=argv[++j];
        else if(!strcmp(option,"--save-at"))save_text=argv[++j];
        else if(!strcmp(option,"--restore"))restore=argv[++j];
        else if(!strcmp(option,"--end")){if(count(argv[++j],&end))return error("end_argument",-1);}
        else if(!strcmp(option,"--query-stride")){if(count(argv[++j],&stride)||!stride)return error("stride_argument",-1);}
        else if(!strcmp(option,"--fit-budget")){if(count(argv[++j],&budget))return error("budget_argument",-1);}
        else return error("unknown_argument",-1);
    }
    if(!data_path||!source||!end||end>config.max_history_samples||source_id(source,config.source_id)||
       count_list(save_text,save_at,&save_count)||(save_count&&!prefix)||(cold&&!restore))return error("arguments",-1);
    fit_rc=restore?scm_session_checkpoint_restore(&session,&config,restore):scm_session_init(&session,&config);
    if(fit_rc){rc=error(restore?"restore":"init",fit_rc);goto done;}
    start=session.next_index;
    if(start>end){rc=error("end_before_resume",-1);goto done;}
    for(j=0;j<(int)save_count;j++)if(save_at[j]<=start||save_at[j]>end){rc=error("checkpoint_outside_segment",-1);goto done;}
    printf("{\"event\":\"run\",\"schema\":\"mumble_session_jsonl_v1\",\"source_id\":");string(source);
    printf(",\"start_index\":%" PRIu64 ",\"end_index\":%" PRIu64 ",\"restored\":%s,\"cold_reset\":%s,\"fit_budget\":%" PRIu64 ",\"query_stride_samples\":%" PRIu64 ",\"modes\":%d,\"starts\":%d,\"max_iterations\":%d,\"max_history_samples\":%" PRIu64,
        start,end,restore?"true":"false",cold?"true":"false",budget,stride,config.modes,config.starts,config.max_iterations,config.max_history_samples);
    named("sigma",config.sigma);
    printf(",\"host_fixed_objects_bytes\":%zu,\"temperature\":\"unsupported\",\"EOD\":\"unsupported\",\"truth_input\":false,\"prior_factor_added\":false}\n",
        sizeof(session)+sizeof(assessment)+sizeof(assessment_workspace)+sizeof(query)+sizeof(csv_line)+sizeof(config)+sizeof(sample));
    if(cold&&(fit_rc=scm_session_cold_reset(&session))){rc=error("cold_reset",fit_rc);goto done;}
    if((fit_rc=emit_query(cold?"cold_reset":restore?"resume":"initial"))){rc=error("query",fit_rc);goto done;}
    data=open_data(data_path);if(!data){rc=error("open_csv",-1);goto done;}
    /* Earlier rows are parsed only to reach the checkpoint position. The input
     * ledger receives each current-epoch observation exactly once. */
    for(i=0;i<end;i++) {
        if(read_sample(data,i,&sample)){rc=error("read_csv",-1);goto done;}
        if(i<start)continue;
        if((fit_rc=scm_session_ingest(&session,config.source_id,i,&sample,1))){rc=error("ingest",fit_rc);goto done;}
        had_fit=0;
        if(scm_session_fit_due(&session)) {
            if(actual_fits>=budget){rc=error("fit_budget_exhausted",-1);goto done;}
            has_initial=session.has_fit;actual_fits++;
            printf("{\"event\":\"fit_begin\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"process_fit_call\":%" PRIu64 ",\"initial_source\":\"%s\",\"prior_factor_added\":false}\n",
                session.next_index,session.epoch_begin,actual_fits,has_initial?"previous_estimated_theta_only":"public_starts");
            if(fflush(stdout)){rc=error("flush_fit_begin",-1);goto done;}
            fit_rc=scm_session_fit(&session);emit_fit(fit_rc,has_initial);fflush(stdout);
            if(fit_rc){rc=error("fit",fit_rc);goto done;}had_fit=1;
        }
        if(had_fit||(save_cursor<save_count&&save_at[save_cursor]==session.next_index)||session.next_index%stride==0||session.next_index==end) {
            const char *reason=had_fit?"fit":(save_cursor<save_count&&save_at[save_cursor]==session.next_index)?"checkpoint":"sample";
            if((fit_rc=emit_query(reason))){rc=error("query",fit_rc);goto done;}
        }
        if(save_cursor<save_count&&save_at[save_cursor]==session.next_index) {
            j=snprintf(path,sizeof(path),"%s-%" PRIu64 ".bin",prefix,session.next_index);
            if(j<0||(size_t)j>=sizeof(path)){rc=error("checkpoint_path",-1);goto done;}
            if((fit_rc=scm_session_checkpoint_save(&session,path))){rc=error("checkpoint",fit_rc);goto done;}
            printf("{\"event\":\"checkpoint\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"path\":",session.next_index,session.epoch_begin);
            string(path);fputs("}\n",stdout);save_cursor++;
        }
    }
    if(end==config.max_history_samples) {
        do{j=fgetc(data);}while(j!=EOF&&isspace((unsigned char)j));
        if(j!=EOF||ferror(data)){rc=error("csv_trailing_data",-1);goto done;}
    }
    if(save_cursor!=save_count){rc=error("checkpoint_schedule_incomplete",-1);goto done;}
    printf("{\"event\":\"complete\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"actual_fit_calls\":%" PRIu64 ",\"cumulative_fit_attempts\":%" PRIu64 ",\"history_samples\":%zu}\n",
        session.next_index,session.epoch_begin,actual_fits,session.fit_attempts,session.count);
    rc=fflush(stdout)||ferror(stdout)?error("output",-1):EXIT_SUCCESS;
done:
    if(data&&fclose(data)&&rc==EXIT_SUCCESS)rc=error("close_csv",-1);
    scm_session_destroy(&session);return rc;
}
