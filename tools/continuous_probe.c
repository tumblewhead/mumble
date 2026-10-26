/* Truth-free host adapter for continuous_learning_validation_001.
 * Input: headerless little-endian <Qddd (index,dt,I,V),32 bytes.
 * Metrics: headerless little-endian <Q7dQiI,80 bytes, version1; the final JSON
 * receipt describes its field order/availability bits. All observation/scoring
 * buffers below are HOST observers, separate from the7152-byte owned learner.
 * Frozen estimator/model/codec sources are linked without modification. */
#define _POSIX_C_SOURCE 200809L
#include "scm_hypothesis_checkpoint.h"
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <float.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define LEDGER (state.component[0])
#define QUERY_CAP 8192u
#define MAX_CHECKPOINTS 64u
#define RING_COUNT 35u
#define FAILURE_RESERVE UINT64_C(32768)
#define DEFAULT_OUTPUT_CAP UINT64_C(536870912)
#define MAX_DELIVERIES UINT64_C(661500)
#define FAILURE_FLAGS (SCM_ONLINE_FLAG_RECOVERY_REQUIRED|SCM_ONLINE_FLAG_MODEL_UNAVAILABLE|SCM_ONLINE_FLAG_MISSING_VOLTAGE|SCM_ONLINE_FLAG_UPDATE_REJECTED)

/* These five objects are the unchanged learner owned subtotal. */
static scm_hypothesis state;
static scm_hypothesis_workspace workspace;
static scm_hypothesis_query_result query;
static scm_hypothesis_config config;
static scm_sample sample;

/* Fixed host observers. No raw history is retained beyond this failure ring. */
static scm_hypothesis entering;
static unsigned char checkpoint_buffer[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES];
static unsigned char observations[RING_COUNT][32],observation_bytes[32],metric_bytes[80];
static char checkpoint_path[SCM_HYPOTHESIS_CHECKPOINT_PATH_CAPACITY];
static char query_text[QUERY_CAP+1],query_index_line[64];
static uint64_t save_at[MAX_CHECKPOINTS];
static unsigned ring_next,ring_used,save_count,save_cursor;
static size_t query_pos;
static int query_error,initialized,capturing_failure;
static uint64_t output_bytes,output_cap=DEFAULT_OUTPUT_CAP;
static uint64_t metric_records,query_records,checkpoint_records,deliveries,consumed;
static uint64_t first_index,last_query_index=UINT64_MAX,requested_end,failed_input_index;
static uint64_t next_query_index,previous_query_index;
static int have_next_query,have_previous_query,query_schedule_done;
static const char *failure_operation="none",*checkpoint_prefix=NULL,*source_text=NULL;
static int failure_code,failure_capture_ok=1;
static FILE *query_file,*metrics_file,*index_file;
static volatile sig_atomic_t stop_signal;

/* Async handler performs no I/O, allocation, state mutation or longjmp.
 * The current ingest/output transaction finishes before the main loop captures
 * its next safe boundary. External supervisors may still have to hard-kill an
 * unresponsive process and must then mark diagnostic capture unavailable. */
static void request_stop(int signum){stop_signal=(sig_atomic_t)signum;}
static int install_stop_handlers(void)
{
    struct sigaction action;
    memset(&action,0,sizeof(action));action.sa_handler=request_stop;
    sigemptyset(&action.sa_mask);action.sa_flags=SA_RESTART;
    return sigaction(SIGINT,&action,NULL)||sigaction(SIGTERM,&action,NULL)?-1:0;
}

static size_t owned_bytes(void)
{return sizeof(state)+sizeof(workspace)+sizeof(query)+sizeof(config)+sizeof(sample);}
static size_t host_observer_named_bytes(void)
{return sizeof(entering)+sizeof(checkpoint_buffer)+sizeof(observations)+sizeof(observation_bytes)+sizeof(metric_bytes)+sizeof(checkpoint_path)+sizeof(query_text)+sizeof(query_index_line)+sizeof(save_at);}

static uint64_t get64(const unsigned char *p)
{uint64_t x=0;unsigned i;for(i=0;i<8;i++)x|=(uint64_t)p[i]<<(8*i);return x;}
static void put64(unsigned char *p,uint64_t x)
{unsigned i;for(i=0;i<8;i++)p[i]=(unsigned char)(x>>(8*i));}
static void put32(unsigned char *p,uint32_t x)
{unsigned i;for(i=0;i<4;i++)p[i]=(unsigned char)(x>>(8*i));}
static double get_double(const unsigned char *p)
{uint64_t x=get64(p);double d;memcpy(&d,&x,8);return d;}
static void put_double(unsigned char *p,double d)
{uint64_t x;memcpy(&x,&d,8);put64(p,x);}

static int room(size_t bytes)
{
    uint64_t limit=output_cap;
    if(!capturing_failure){if(limit<FAILURE_RESERVE)return 0;limit-=FAILURE_RESERVE;}
    return output_bytes<=limit&&(uint64_t)bytes<=limit-output_bytes;
}
static FILE *exclusive(const char *path,const char *mode)
{
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);FILE *f;
    if(fd<0)return NULL;
    f=fdopen(fd,mode);if(!f)close(fd);return f;
}
static int write_bytes(FILE *f,const void *data,size_t bytes)
{
    if(!f||!room(bytes))return -1;
    if(fwrite(data,1,bytes,f)!=bytes)return -1;
    output_bytes+=(uint64_t)bytes;return 0;
}
static int named_path(const char *suffix)
{
    int n=snprintf(checkpoint_path,sizeof(checkpoint_path),"%s-%s",checkpoint_prefix,suffix);
    return n<0||(size_t)n>=sizeof(checkpoint_path)?-1:0;
}
static int save_named_bank(const scm_hypothesis *bank,const char *suffix)
{
    FILE *reservation;int rc;
    if(!room(SCM_HYPOTHESIS_CHECKPOINT_BYTES)||named_path(suffix))return -1;
    reservation=exclusive(checkpoint_path,"wb");if(!reservation)return -1;
    if(fclose(reservation))return -1;
    /* The codec replaces only this adapter's exclusively reserved placeholder. */
    rc=scm_hypothesis_checkpoint_save(bank,checkpoint_path,checkpoint_buffer);
    if(rc)return rc;
    output_bytes+=SCM_HYPOTHESIS_CHECKPOINT_BYTES;checkpoint_records++;return 0;
}
static int save_current_index(void)
{
    char suffix[40];int n=snprintf(suffix,sizeof(suffix),"%" PRIu64 ".bin",LEDGER.next_index);
    if(n<0||(size_t)n>=sizeof(suffix))return -1;
    return save_named_bank(&state,suffix);
}

static void qprintf(const char *format,...)
{
    va_list ap;int n;
    if(query_error)return;
    va_start(ap,format);n=vsnprintf(query_text+query_pos,sizeof(query_text)-query_pos,format,ap);va_end(ap);
    if(n<0||(size_t)n>=sizeof(query_text)-query_pos){query_error=1;return;}
    query_pos+=(size_t)n;
}
static void qputs(const char *s){qprintf("%s",s);}
static void qchar(int c){qprintf("%c",c);}
static void number(double x){if(isfinite(x))qprintf("%.17g",x);else qputs("null");}
static void string(const char *s)
{
    const unsigned char *p=(const unsigned char*)s;qchar('"');
    for(;*p;p++){if(*p=='"'||*p=='\\'){qchar('\\');qchar(*p);}else if(*p<32)qprintf("\\u%04x",*p);else qchar(*p);}qchar('"');
}
static void named(const char *name,double x){qchar(',');string(name);qchar(':');number(x);}
static void array(const char *name,const double *x,int n)
{
    int i;qchar(',');string(name);qputs(":[");for(i=0;i<n;i++){if(i)qchar(',');number(x[i]);}qchar(']');
}
static void query_reset(void){query_pos=0;query_error=0;query_text[0]=0;}
static int query_flush(void)
{return query_error||query_pos>QUERY_CAP?-1:write_bytes(query_file,query_text,query_pos);}

static void emit_aggregate(const scm_hypothesis_aggregate_query *q)
{
    qputs("{\"soc_status\":");string(scm_hypothesis_status_name(q->soc_status));
    qputs(",\"capacity_status\":");string(scm_hypothesis_status_name(q->capacity_status));
    qprintf(",\"soc_status_code\":%d,\"capacity_status_code\":%d,\"flags\":%u,\"excitation\":%u",q->soc_status,q->capacity_status,q->flags,q->excitation);
#define U(field) qprintf(",\"" #field "\":%" PRIu64,q->field)
    U(epoch_begin);U(next_index);U(evidence_next_index);U(evidence_age_samples);
    U(prediction_count);U(voltage_count);U(missing_voltage_count);U(rejected_voltage_count);U(cold_resets);
#undef U
#define R(field) named(#field,q->field)
    R(elapsed_s);R(epoch_elapsed_s);R(current_soc);R(capacity_Ah);R(predicted_voltage_V);
    R(soc_local_lower);R(soc_local_upper);R(capacity_local_lower_Ah);R(capacity_local_upper_Ah);
#undef R
#define I(field) qprintf(",\"" #field "\":%d",q->field)
    I(point_available);I(capacity_available);I(prediction_available);I(local_ranges_available);
    I(soc_local_precision_hard);I(capacity_local_precision_hard);I(soc_local_precision_preferred);I(capacity_local_precision_preferred);
#undef I
    named("raw_soc",q->mean[SCM_ONLINE_Z]);named("raw_capacity_Ah",exp(q->mean[SCM_ONLINE_LOG_Q]));
    array("mean",q->mean,SCM_HYPOTHESIS_DIM);array("coordinate_sd",q->coordinate_sd,SCM_HYPOTHESIS_DIM);qchar('}');
}
static void emit_component(const scm_online_query_result *q,unsigned index)
{
    qprintf("{\"component\":%u,\"soc_status\":",index);string(scm_hypothesis_status_name(q->soc_status));
    qputs(",\"capacity_status\":");string(scm_hypothesis_status_name(q->capacity_status));
    qprintf(",\"soc_status_code\":%d,\"capacity_status_code\":%d,\"flags\":%u,\"excitation\":%u",q->soc_status,q->capacity_status,q->flags,q->excitation);
    qprintf(",\"last_limited_mask\":%u,\"last_blocked_mask\":%u",q->last_limited_mask,q->last_blocked_mask);
#define U(field) qprintf(",\"" #field "\":%" PRIu64,q->field)
    U(epoch_begin);U(next_index);U(evidence_next_index);U(evidence_age_samples);
    U(prediction_count);U(voltage_count);U(missing_voltage_count);U(rejected_voltage_count);
    U(limited_gain_count);U(zero_gain_count);U(cold_resets);
#undef U
#define R(field) named(#field,q->field)
    R(elapsed_s);R(epoch_elapsed_s);R(current_soc);R(capacity_Ah);R(predicted_voltage_V);
    R(soc_local_lower);R(soc_local_upper);R(capacity_local_lower_Ah);R(capacity_local_upper_Ah);
    R(last_innovation_V);R(last_innovation_variance_V2);R(last_gain_scale);R(last_max_gain_scale);
    R(minimum_gain_scale);R(innovation_ewma);
#undef R
#define I(field) qprintf(",\"" #field "\":%d",q->field)
    I(point_available);I(capacity_available);I(prediction_available);I(local_ranges_available);
    I(soc_local_precision_hard);I(capacity_local_precision_hard);I(soc_local_precision_preferred);I(capacity_local_precision_preferred);
#undef I
    named("raw_soc",q->mean[SCM_ONLINE_Z]);named("raw_capacity_Ah",exp(q->mean[SCM_ONLINE_LOG_Q]));
    array("mean",q->mean,SCM_HYPOTHESIS_DIM);array("coordinate_sd",q->coordinate_sd,SCM_HYPOTHESIS_DIM);qchar('}');
}
static int emit_query(const char *reason,int attempted)
{
    unsigned j;int rc;
    if(last_query_index==LEDGER.next_index)return 0;
    if(query_records>=24000)return -1;
    rc=scm_hypothesis_query(&state,SCM_HYPOTHESIS_AGGREGATE,&query);if(rc)return rc;
    query_reset();
    qprintf("{\"event\":\"query\",\"schema\":\"mumble_continuous_query_v1\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"reason\":",LEDGER.next_index,LEDGER.epoch_begin);
    string(reason);named("elapsed_s",LEDGER.elapsed_s);qputs(",\"aggregate\":");emit_aggregate(&query.view.aggregate);
    array("log_weights",query.log_weight,2);array("all_component_hull",query.all_component_soc_capacity_hull,4);
    qprintf(",\"component_flags\":[%u,%u],\"generation\":%" PRIu64 ",\"bank_flags\":%u,\"bank_evidence_next_index\":%" PRIu64,
        query.component_flags[0],query.component_flags[1],state.header.generation,state.header.flags,state.header.bank_evidence_next_index);
    qprintf(",\"last_rejection_stage_code\":%u,\"last_rejection_component\":%u,\"last_rejection_stage\":",state.header.last_rejection_stage,state.header.last_rejection_component);
    string(scm_hypothesis_rejection_stage_name(state.header.last_rejection_stage));
    qprintf(",\"current_score_attempt\":%s,\"score_transaction_accepted\":%s,\"pre_correction_log_likelihood\":[",attempted?"true":"false",attempted&&!(LEDGER.flags&FAILURE_FLAGS)?"true":"false");
    for(j=0;j<2;j++){if(j)qchar(',');number(attempted?workspace.pre_correction_log_likelihood[j]:NAN);}
    qputs("],\"components\":[");
    for(j=0;j<2;j++){rc=scm_hypothesis_query(&state,(int)j,&query);if(rc)return rc;if(j)qchar(',');emit_component(&query.view.component,j);}
    qputs("],\"application_SOC_Q_accuracy\":\"unresolved\",\"coverage\":\"unvalidated\",\"hard_support\":\"not_provided\"}\n");
    rc=query_flush();if(!rc){query_records++;last_query_index=LEDGER.next_index;}return rc;
}

static const char *space(const char *p){while(isspace((unsigned char)*p))p++;return p;}
static int parse_count(const char *text,uint64_t *value)
{
    char *end;unsigned long long n;text=space(text);if(!*text||*text=='-'||*text=='+')return -1;
    errno=0;n=strtoull(text,&end,10);if(errno||end==text||*space(end)||n>UINT64_MAX)return -1;*value=(uint64_t)n;return 0;
}
static int checkpoint_list(const char *text)
{
    char token[32];const char *end;size_t n;unsigned k=0;
    if(!*text){save_count=0;return 0;}
    while(*text){end=strchr(text,',');n=end?(size_t)(end-text):strlen(text);if(!n||n>=sizeof(token)||k>=MAX_CHECKPOINTS)return -1;
        memcpy(token,text,n);token[n]=0;if(parse_count(token,&save_at[k])||(k&&save_at[k]<=save_at[k-1]))return -1;
        k++;if(!end)break;text=end+1;if(!*text)return -1;}
    save_count=k;return 0;
}
static int hex_digit(char c)
{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
static int parse_source(const char *text,unsigned char *id)
{
    int i,a,b;if(strlen(text)!=2*SCM_ONLINE_SOURCE_BYTES)return -1;
    for(i=0;i<SCM_ONLINE_SOURCE_BYTES;i++){a=hex_digit(text[2*i]);b=hex_digit(text[2*i+1]);if(a<0||b<0)return -1;id[i]=(unsigned char)(16*a+b);}return 0;
}
static int advance_query_schedule(void)
{
    uint64_t n;
    if(query_schedule_done){have_next_query=0;return 0;}
    if(!fgets(query_index_line,sizeof(query_index_line),index_file)){
        if(ferror(index_file))return -1;
        query_schedule_done=1;have_next_query=0;return 0;}
    if(!strchr(query_index_line,'\n')&&!feof(index_file))return -1;
    if(parse_count(query_index_line,&n)||(have_previous_query&&n<=previous_query_index))return -1;
    previous_query_index=n;have_previous_query=1;next_query_index=n;have_next_query=1;return 0;
}
static int schedule_through(uint64_t index,int *selected)
{
    *selected=0;
    while(have_next_query&&next_query_index<=index){if(next_query_index==index)*selected=1;if(advance_query_schedule())return -1;}
    return 0;
}

static int emit_metric(const double old_logw[2],int ingest_code)
{
    const scm_hypothesis_aggregate_query *q;double a,b,total,forecast=NAN,fit=NAN;
    uint64_t mask=0;int rc;
    rc=scm_hypothesis_query(&state,SCM_HYPOTHESIS_AGGREGATE,&query);if(rc)return rc;
    q=&query.view.aggregate;
    if(!isfinite(q->mean[11])||!isfinite(exp(q->mean[5])))return -1;
    if(q->point_available)mask|=1;
    if(q->capacity_available)mask|=2;
    if(!ingest_code&&!(q->flags&FAILURE_FLAGS)){
        a=exp(old_logw[0]);b=exp(old_logw[1]);total=a+b;a/=total;b/=total;
        forecast=sample.voltage-(a*state.component[0].last_innovation_V+b*state.component[1].last_innovation_V);
        if(!isfinite(forecast))return -1;
        mask|=4;
    }
    if(q->prediction_available){fit=q->predicted_voltage_V;if(!isfinite(fit))return -1;mask|=8;}
    put64(metric_bytes,LEDGER.next_index);put_double(metric_bytes+8,LEDGER.elapsed_s);
    put_double(metric_bytes+16,q->mean[11]);put_double(metric_bytes+24,exp(q->mean[5]));
    put_double(metric_bytes+32,forecast);put_double(metric_bytes+40,fit);
    put_double(metric_bytes+48,old_logw[0]);put_double(metric_bytes+56,old_logw[1]);
    put64(metric_bytes+64,mask);put32(metric_bytes+72,(uint32_t)(int32_t)ingest_code);put32(metric_bytes+76,q->flags);
    if(write_bytes(metrics_file,metric_bytes,sizeof(metric_bytes)))return -1;
    metric_records++;return 0;
}

static void capture_failure(int attempted)
{
    FILE *f;unsigned k;
    if(!initialized||!checkpoint_prefix)return;
    capturing_failure=1;
    if(save_named_bank(&entering,"failure-entering.bin"))failure_capture_ok=0;
    if(save_named_bank(&state,"failure-state.bin"))failure_capture_ok=0;
    if(named_path("failure-live-raw.bin"))failure_capture_ok=0;
    else {f=exclusive(checkpoint_path,"wb");if(!f)failure_capture_ok=0;else{
        if(write_bytes(f,&state,sizeof(state)))failure_capture_ok=0;
        if(fclose(f))failure_capture_ok=0;}}
    if(named_path("failure-inputs.bin"))failure_capture_ok=0;
    else {f=exclusive(checkpoint_path,"wb");if(!f)failure_capture_ok=0;else{
        for(k=0;k<ring_used;k++){unsigned at=(ring_next+RING_COUNT-ring_used+k)%RING_COUNT;if(write_bytes(f,observations[at],32)){failure_capture_ok=0;break;}}
        if(fclose(f))failure_capture_ok=0;}}
    if(query_file&&emit_query("failure",attempted))failure_capture_ok=0;
    if(named_path("failure.json"))failure_capture_ok=0;
    else {f=exclusive(checkpoint_path,"wb");if(!f)failure_capture_ok=0;else{
        query_reset();qputs("{\"schema\":\"mumble_continuous_failure_v1\",\"operation\":");string(failure_operation);
        qprintf(",\"code\":%d,\"supervisor_signal\":%d,\"failed_input_index\":%" PRIu64 ",\"entering_index\":%" PRIu64 ",\"next_index\":%" PRIu64 ",\"ring_records\":%u,\"rejection_stage_code\":%u,\"rejection_component\":%u,\"raw_state_bytes\":%zu,\"raw_state_scope\":\"host ABI diagnostic; not a portable checkpoint\"}\n",failure_code,(int)stop_signal,failed_input_index,entering.component[0].next_index,LEDGER.next_index,ring_used,state.header.last_rejection_stage,state.header.last_rejection_component,sizeof(state));
        if(query_error||write_bytes(f,query_text,query_pos))failure_capture_ok=0;
        if(fclose(f))failure_capture_ok=0;}}
    capturing_failure=0;
}
static void fail(const char *operation,int code)
{if(!failure_code){failure_operation=operation;failure_code=code?code:-1;}}
static int ledger_ok(uint64_t expected,const scm_hypothesis *before)
{
    unsigned j;if(scm_hypothesis_validate(&state))return -1;
    if(LEDGER.next_index!=expected||LEDGER.prediction_count!=before->component[0].prediction_count+1||
       LEDGER.voltage_count!=before->component[0].voltage_count+1||LEDGER.missing_voltage_count!=before->component[0].missing_voltage_count||
       LEDGER.elapsed_s!=before->component[0].elapsed_s+sample.dt||LEDGER.epoch_elapsed_s!=before->component[0].epoch_elapsed_s+sample.dt||
       state.header.generation!=before->header.generation+1)return -1;
    for(j=0;j<2;j++)if(memcmp(state.component[j].config.source_id,config.source_id,SCM_ONLINE_SOURCE_BYTES))return -1;
    return 0;
}
static void receipt(void)
{
    printf("{\"schema\":\"mumble_continuous_adapter_receipt_v1\",\"status\":\"%s\",\"operation\":\"%s\",\"code\":%d,\"supervisor_signal\":%d,\"start_index\":%" PRIu64 ",\"end_index\":%" PRIu64 ",\"next_index\":%" PRIu64 ",\"input_deliveries\":%" PRIu64 ",\"consumed_intervals\":%" PRIu64 ",\"metric_records\":%" PRIu64 ",\"query_records\":%" PRIu64 ",\"checkpoint_records\":%" PRIu64 ",\"output_bytes\":%" PRIu64 ",\"owned_subtotal_bytes\":%zu,\"host_observer_named_bytes\":%zu,\"host_runtime_stack_additional\":true,\"scalar_record_bytes\":80,\"scalar_format\":\"little-endian <Q7dQiI; headerless version1\",\"availability_bits\":{\"SOC\":1,\"Q\":2,\"causal_forecast\":4,\"filtered_fit\":8},\"truth_input\":false,\"batch_optimizer_calls\":0,\"failure_capture_ok\":%s,\"rejected_voltage_count\":%" PRIu64 ",\"last_rejection_stage_code\":%u,\"flags\":%u,\"source_id\":\"%s\"}\n",
        failure_code?"failed":"complete",failure_operation,failure_code,(int)stop_signal,first_index,requested_end,initialized?LEDGER.next_index:0,
        deliveries,consumed,metric_records,query_records,checkpoint_records,output_bytes,owned_bytes(),host_observer_named_bytes(),
        failure_capture_ok?"true":"false",initialized?LEDGER.rejected_voltage_count:0,initialized?state.header.last_rejection_stage:0,initialized?LEDGER.flags:0,source_text?source_text:"");
}
static void help(void)
{
    puts("Usage: continuous_probe --data observations.bin --data-start-index0 --source HEX64 --end N\n"
         " --metrics metrics.bin --queries queries.jsonl --query-indices indices.txt\n"
         " --checkpoint-prefix PREFIX --checkpoint-indices CSV [--restore FILE] [--cold-reset]\n"
         " [--max-output-bytes N]. Input/query/checkpoint indices are global. No truth input.");
}

int main(int argc,char **argv)
{
    const char *data_path=NULL,*metrics_path=NULL,*queries_path=NULL,*indices_path=NULL,*restore=NULL;
    uint64_t data_start=0,i;int j,cold=0,end_set=0,attempted=0,selected=0,captured=0;FILE *data=NULL;struct stat st;
    for(j=1;j<argc;j++){
        const char *arg=argv[j];if(!strcmp(arg,"--help")){help();return 0;}
        if(!strcmp(arg,"--cold-reset")){cold=1;continue;}
        if(j+1>=argc){fail("argument_missing",-1);goto finish;}
        if(!strcmp(arg,"--data"))data_path=argv[++j];
        else if(!strcmp(arg,"--data-start-index")){if(parse_count(argv[++j],&data_start)){fail("data_start",-1);goto finish;}}
        else if(!strcmp(arg,"--source"))source_text=argv[++j];
        else if(!strcmp(arg,"--end")){if(parse_count(argv[++j],&requested_end)){fail("end",-1);goto finish;}end_set=1;}
        else if(!strcmp(arg,"--metrics"))metrics_path=argv[++j];
        else if(!strcmp(arg,"--queries"))queries_path=argv[++j];
        else if(!strcmp(arg,"--query-indices"))indices_path=argv[++j];
        else if(!strcmp(arg,"--checkpoint-prefix"))checkpoint_prefix=argv[++j];
        else if(!strcmp(arg,"--checkpoint-indices")){if(checkpoint_list(argv[++j])){fail("checkpoint_list",-1);goto finish;}}
        else if(!strcmp(arg,"--restore"))restore=argv[++j];
        else if(!strcmp(arg,"--max-output-bytes")){if(parse_count(argv[++j],&output_cap)){fail("output_cap",-1);goto finish;}}
        else {fail("unknown_argument",-1);goto finish;}
    }
    if(!data_path||!metrics_path||!queries_path||!indices_path||!checkpoint_prefix||!source_text||!end_set||(cold&&!restore)||output_cap>DEFAULT_OUTPUT_CAP||output_cap<FAILURE_RESERVE){fail("required_argument",-1);goto finish;}
    if(sizeof(double)!=8||DBL_MANT_DIG!=53||DBL_MAX_EXP!=1024||sizeof(uint64_t)!=8||sizeof(uint32_t)!=4){fail("numeric_representation",-1);goto finish;}
    if(owned_bytes()>7152){fail("owned_resource",-1);goto finish;}
    if(install_stop_handlers()){fail("signal_handler_setup",-1);goto finish;}
    scm_hypothesis_config_default(&config);
    if(parse_source(source_text,config.source_id)){fail("source_id",-1);goto finish;}
    j=restore?scm_hypothesis_checkpoint_restore(&state,&config,restore,&workspace,checkpoint_buffer):scm_hypothesis_init(&state,&config,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);
    if(j){fail(restore?"restore":"init",j);goto finish;}
    initialized=1;entering=state;
    if(!(state.header.flags&SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT)){fail("mode_mismatch",-1);goto finish;}
    if(cold&&(j=scm_hypothesis_cold_reset(&state))){fail("cold_reset",j);goto finish;}
    entering=state;first_index=LEDGER.next_index;
    if(first_index>requested_end||data_start>first_index||requested_end-first_index>MAX_DELIVERIES){fail("segment_domain",-1);goto finish;}
    for(j=0;j<(int)save_count;j++)if(save_at[j]<first_index||save_at[j]>requested_end){fail("checkpoint_outside_segment",-1);goto finish;}
    metrics_file=exclusive(metrics_path,"wb");if(!metrics_file){fail("open_metrics",-1);goto finish;}
    query_file=exclusive(queries_path,"wb");if(!query_file){fail("open_queries",-1);goto finish;}
    index_file=fopen(indices_path,"r");if(!index_file||advance_query_schedule()){fail("open_query_schedule",-1);goto finish;}
    if(schedule_through(first_index,&selected)){fail("query_schedule",-1);goto finish;}
    if(save_named_bank(&state,"initial.bin")){fail("initial_checkpoint",-1);goto finish;}
    if(emit_query(cold?"cold_reset":restore?"resume":"initial",0)){fail("initial_query",-1);goto finish;}
    while(save_cursor<save_count&&save_at[save_cursor]==first_index){if(save_current_index()){fail("initial_scheduled_checkpoint",-1);goto finish;}save_cursor++;}
    data=fopen(data_path,"rb");if(!data||fstat(fileno(data),&st)||st.st_size<0||st.st_size%32||
        requested_end<data_start||requested_end-data_start>(uint64_t)st.st_size/32||first_index-data_start>(uint64_t)INT64_MAX/32||
        fseeko(data,(off_t)((first_index-data_start)*32),SEEK_SET)){fail("input_extent",-1);goto finish;}
    for(i=first_index;i<requested_end;i++){
        double old_logw[2];uint64_t old_rejected;int ingest_code;
        attempted=0;entering=state;failed_input_index=i;
        if(stop_signal){fail("supervisor_stop",-200-(int)stop_signal);break;}
        if(fread(observation_bytes,1,32,data)!=32){fail("read_observation",-1);break;}
        memcpy(observations[ring_next],observation_bytes,32);ring_next=(ring_next+1)%RING_COUNT;if(ring_used<RING_COUNT)ring_used++;
        if(get64(observation_bytes)!=i){fail("input_index",SCM_ONLINE_ERR_ORDER);break;}
        sample.dt=get_double(observation_bytes+8);sample.current=get_double(observation_bytes+16);sample.voltage=get_double(observation_bytes+24);
        if(!(sample.dt>0)||!isfinite(sample.dt)||sample.dt>config.max_dt_s||!isfinite(sample.current)||fabs(sample.current)>config.max_abs_current_A||!isfinite(sample.voltage)){fail("input_domain",SCM_ONLINE_ERR_DOMAIN);break;}
        if(stop_signal){fail("supervisor_stop",-200-(int)stop_signal);break;}
        old_logw[0]=state.log_weight[0];old_logw[1]=state.log_weight[1];old_rejected=LEDGER.rejected_voltage_count;
        attempted=1;deliveries++;ingest_code=scm_hypothesis_ingest(&state,config.source_id,i,&sample,1,&workspace);
        if(LEDGER.next_index==i+1)consumed++;
        if(emit_metric(old_logw,ingest_code)){fail("metric_output",-1);break;}
        if(ingest_code){fail(ingest_code>0?"recovery":"ingest",ingest_code);break;}
        if((LEDGER.flags&FAILURE_FLAGS)||LEDGER.rejected_voltage_count!=old_rejected){fail("voltage_transaction",-1);break;}
        if(ledger_ok(i+1,&entering)){fail("ledger",-1);break;}
        if(schedule_through(LEDGER.next_index,&selected)){fail("query_schedule",-1);break;}
        if(selected||(save_cursor<save_count&&save_at[save_cursor]==LEDGER.next_index)||LEDGER.next_index==requested_end){
            if(emit_query(save_cursor<save_count&&save_at[save_cursor]==LEDGER.next_index?"checkpoint":"sample",1)){fail("query_output",-1);break;}}
        if(save_cursor<save_count&&save_at[save_cursor]==LEDGER.next_index){if(save_current_index()){fail("checkpoint",-1);break;}save_cursor++;}
    }
    if(!failure_code){
        if(save_cursor!=save_count){fail("checkpoint_schedule",-1);goto finish;}
        /* Validate the rest of the index file even when it has entries outside
         * this suffix. They are observation-free schedule metadata. */
        while(have_next_query)if(advance_query_schedule()){fail("query_schedule_tail",-1);break;}
    }
finish:
    if(stop_signal&&!failure_code){
        if(initialized){entering=state;failed_input_index=LEDGER.next_index;}
        attempted=0;fail("supervisor_stop",-200-(int)stop_signal);
    }
    if(metrics_file&&fflush(metrics_file))fail("flush_metrics",-1);
    if(query_file&&fflush(query_file))fail("flush_queries",-1);
    if(failure_code){capture_failure(attempted);captured=1;}
    if(data&&fclose(data))fail("close_input",-1);
    if(index_file&&fclose(index_file))fail("close_query_schedule",-1);
    if(metrics_file&&fclose(metrics_file))fail("close_metrics",-1);
    if(query_file&&fclose(query_file))fail("close_queries",-1);
    metrics_file=NULL;query_file=NULL;
    if(failure_code&&!captured)capture_failure(attempted);
    receipt();
    if(failure_code)fprintf(stderr,"%s failed: code%d, next_index%" PRIu64 "\n",failure_operation,failure_code,initialized?LEDGER.next_index:0);
    return failure_code?EXIT_FAILURE:EXIT_SUCCESS;
}
