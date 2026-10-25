/* Host driver for one bounded online candidate. Observations and public
 * configuration only; no truth file, raw journal or batch optimization. */
#include "scm_online_checkpoint.h"
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CSV_CAPACITY 256u
#define MAX_CHECKPOINTS 8u
static scm_online state;
static scm_online_workspace workspace;
static scm_online_query_result query;
static scm_online_config config;
static scm_sample sample;
static char csv_line[CSV_CAPACITY],csv_buffer[CSV_CAPACITY];
static char checkpoint_path[SCM_ONLINE_CHECKPOINT_PATH_CAPACITY];
static uint64_t save_at[MAX_CHECKPOINTS];

static void number(double x){if(isfinite(x))printf("%.17g",x);else fputs("null",stdout);}
static void string(const char *s)
{
    const unsigned char *p=(const unsigned char*)s;putchar('"');
    for(;*p;p++){if(*p=='"'||*p=='\\'){putchar('\\');putchar(*p);}else if(*p<32)printf("\\u%04x",*p);else putchar(*p);}putchar('"');
}
static void named(const char *name,double x){putchar(',');string(name);putchar(':');number(x);}
static void array(const char *name,const double *x,int n)
{
    int i;putchar(',');string(name);fputs(":[",stdout);for(i=0;i<n;i++){if(i)putchar(',');number(x[i]);}putchar(']');
}
static const char *space(const char *p){while(isspace((unsigned char)*p))p++;return p;}
static int count(const char *text,uint64_t *value)
{
    char *end;unsigned long long n;text=space(text);if(!*text||*text=='-')return -1;
    errno=0;n=strtoull(text,&end,10);if(errno||end==text||*space(end)||n>UINT64_MAX)return -1;
    *value=(uint64_t)n;return 0;
}
static int count_list(const char *text,unsigned *length)
{
    char token[32];const char *end;size_t n;unsigned k=0;
    if(!*text){*length=0;return 0;}
    while(*text){end=strchr(text,',');n=end?(size_t)(end-text):strlen(text);
        if(!n||n>=sizeof(token)||k>=MAX_CHECKPOINTS)return -1;
        memcpy(token,text,n);token[n]=0;
        if(count(token,&save_at[k])||!save_at[k]||(k&&save_at[k]<=save_at[k-1]))return -1;
        k++;if(!end)break;text=end+1;if(!*text)return -1;
    }*length=k;return 0;
}
static int hex_digit(char c)
{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
static int source_id(const char *text,unsigned char *id)
{
    int i,a,b;if(strlen(text)!=2*SCM_ONLINE_SOURCE_BYTES)return -1;
    for(i=0;i<SCM_ONLINE_SOURCE_BYTES;i++){a=hex_digit(text[2*i]);b=hex_digit(text[2*i+1]);if(a<0||b<0)return -1;id[i]=(unsigned char)(16*a+b);}return 0;
}
static FILE *open_data(const char *path)
{
    FILE *f=fopen(path,"r");size_t n;if(!f)return NULL;
    if(setvbuf(f,csv_buffer,_IOFBF,sizeof(csv_buffer))||!fgets(csv_line,sizeof(csv_line),f)){fclose(f);return NULL;}
    n=strlen(csv_line);while(n&&(csv_line[n-1]=='\n'||csv_line[n-1]=='\r'))csv_line[--n]=0;
    if(strcmp(csv_line,"sample_index,dt_s,current_A,voltage_V")){fclose(f);return NULL;}return f;
}
static int read_sample(FILE *f,uint64_t expected)
{
    const char *p;char *end;unsigned long long index;double values[3];int i;
    if(!fgets(csv_line,sizeof(csv_line),f)||(!strchr(csv_line,'\n')&&!feof(f)))return -1;
    p=space(csv_line);if(!*p||*p=='-')return -1;errno=0;index=strtoull(p,&end,10);
    if(errno||end==p||index>UINT64_MAX||(uint64_t)index!=expected)return -1;
    p=space(end);if(*p++!=',')return -1;
    for(i=0;i<3;i++){errno=0;values[i]=strtod(p,&end);if(errno||end==p||!isfinite(values[i]))return -1;
        p=space(end);if(i<2){if(*p++!=',')return -1;}else if(*p)return -1;}
    if(values[0]<0)return -1;
    sample.dt=values[0];sample.current=values[1];sample.voltage=values[2];return 0;
}
static size_t fixed_owned_bytes(void)
{
    return sizeof(state)+sizeof(workspace)+sizeof(query)+sizeof(config)+sizeof(sample)+
        sizeof(csv_line)+sizeof(csv_buffer)+sizeof(checkpoint_path)+sizeof(save_at);
}
static int emit_query(const char *reason)
{
    int rc=scm_online_query(&state,&query);if(rc)return rc;
    printf("{\"event\":\"query\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"reason\":",query.next_index,query.epoch_begin);
    string(reason);fputs(",\"state\":{\"soc_status\":",stdout);string(scm_online_status_name(query.soc_status));
    fputs(",\"capacity_status\":",stdout);string(scm_online_status_name(query.capacity_status));
    printf(",\"soc_status_code\":%d,\"capacity_status_code\":%d,\"flags\":%u,\"excitation\":%u",query.soc_status,query.capacity_status,query.flags,query.excitation);
#define U(field) printf(",\"" #field "\":%" PRIu64,query.field)
    U(epoch_begin);U(next_index);U(evidence_next_index);U(evidence_age_samples);
    U(prediction_count);U(voltage_count);U(missing_voltage_count);U(rejected_voltage_count);
    U(limited_gain_count);U(zero_gain_count);U(cold_resets);
#undef U
#define R(field) named(#field,query.field)
    R(elapsed_s);R(epoch_elapsed_s);R(current_soc);R(capacity_Ah);R(predicted_voltage_V);
    R(soc_local_lower);R(soc_local_upper);R(capacity_local_lower_Ah);R(capacity_local_upper_Ah);
    R(last_innovation_V);R(last_innovation_variance_V2);R(last_gain_scale);R(minimum_gain_scale);R(innovation_ewma);
#undef R
#define I(field) printf(",\"" #field "\":%d",query.field)
    I(point_available);I(capacity_available);I(prediction_available);I(local_ranges_available);
    I(soc_local_precision_hard);I(capacity_local_precision_hard);
    I(soc_local_precision_preferred);I(capacity_local_precision_preferred);
#undef I
    array("mean",query.mean,SCM_ONLINE_DIM);array("coordinate_sd",query.coordinate_sd,SCM_ONLINE_DIM);
    printf("},\"resources\":{\"state_bytes\":%zu,\"workspace_bytes\":%zu,\"query_bytes\":%zu,\"core_owned_bytes\":%zu,\"host_fixed_owned_bytes\":%zu,\"checkpoint_bytes\":%u}}\n",
        sizeof(state),sizeof(workspace),sizeof(query),sizeof(state)+sizeof(workspace)+sizeof(query),fixed_owned_bytes(),SCM_ONLINE_CHECKPOINT_BYTES);
    return ferror(stdout)?-1:0;
}
static int error(const char *operation,int code)
{
    fputs("{\"event\":\"error\",\"operation\":",stdout);string(operation);
    printf(",\"code\":%d,\"next_index\":%" PRIu64 "}\n",code,state.next_index);fflush(stdout);
    fprintf(stderr,"%s failed (code %d, next_index %" PRIu64 ")\n",operation,code,state.next_index);return EXIT_FAILURE;
}
static void help(void)
{
    puts("Usage: scm_online_probe --data FILE --source SHA256_HEX --end COUNT\n"
         "  --checkpoint-prefix PREFIX --save-at COUNT,COUNT --query-stride COUNT\n"
         "  [--restore CHECKPOINT] [--cold-reset]");
}
int main(int argc,char **argv)
{
    const char *data_path=NULL,*source=NULL,*prefix=NULL,*restore=NULL;
    uint64_t end=0,stride=350,start,i,delivered=0;unsigned save_count=0,save_cursor=0;
    FILE *data=NULL;int j,code,rc=EXIT_FAILURE,cold=0,end_set=0;
    for(j=1;j<argc;j++) {
        const char *arg=argv[j];
        if(!strcmp(arg,"--help")){help();return 0;}
        if(!strcmp(arg,"--cold-reset")){cold=1;continue;}
        if(j+1>=argc){help();return error("argument_missing",-1);}
        if(!strcmp(arg,"--data"))data_path=argv[++j];
        else if(!strcmp(arg,"--source"))source=argv[++j];
        else if(!strcmp(arg,"--checkpoint-prefix"))prefix=argv[++j];
        else if(!strcmp(arg,"--restore"))restore=argv[++j];
        else if(!strcmp(arg,"--end")){if(count(argv[++j],&end))return error("end",-1);end_set=1;}
        else if(!strcmp(arg,"--query-stride")){if(count(argv[++j],&stride)||!stride)return error("stride",-1);}
        else if(!strcmp(arg,"--save-at")){if(count_list(argv[++j],&save_count))return error("save_list",-1);}
        else return error("unknown_argument",-1);
    }
    if(!data_path||!source||!prefix||!end_set||end>73500||(cold&&!restore)){help();return error("required_argument",-1);}
    scm_online_config_default(&config);if(source_id(source,config.source_id))return error("source_id",-1);
    code=restore?scm_online_checkpoint_restore(&state,&config,restore,&workspace):scm_online_init(&state,&config);
    if(code)return error(restore?"restore":"init",code);
    start=state.next_index;if(start>end)return error("end_before_resume",-1);
    for(j=0;j<(int)save_count;j++)if(save_at[j]<=start||save_at[j]>end)return error("checkpoint_outside_segment",-1);
    printf("{\"event\":\"run\",\"schema\":\"mumble_online_jsonl_v1\",\"source_id\":");string(source);
    printf(",\"start_index\":%" PRIu64 ",\"end_index\":%" PRIu64 ",\"restored\":%s,\"cold_reset\":%s,\"query_stride_samples\":%" PRIu64 ",\"dimension\":%d",start,end,restore?"true":"false",cold?"true":"false",stride,SCM_ONLINE_DIM);
    named("sigma_V",config.sigma_V);named("max_dt_s",config.max_dt_s);named("max_abs_current_A",config.max_abs_current_A);
    printf(",\"host_fixed_owned_bytes\":%zu,\"CSV_line_bytes\":%zu,\"CSV_buffer_bytes\":%zu,\"checkpoint_path_bytes\":%zu,\"checkpoint_count_bytes\":%zu,\"checkpoint_bytes\":%u,\"batch_optimizer_calls\":0,\"truth_input\":false,\"raw_history_retained\":false,\"covariance\":\"P=S*S^T; full square factor; local prior-conditioned Gaussian\",\"temperature\":\"unsupported\",\"EOD\":\"unsupported\"}\n",
        fixed_owned_bytes(),sizeof(csv_line),sizeof(csv_buffer),sizeof(checkpoint_path),sizeof(save_at),SCM_ONLINE_CHECKPOINT_BYTES);
    if(cold&&(code=scm_online_cold_reset(&state)))return error("cold_reset",code);
    if((code=emit_query(cold?"cold_reset":restore?"resume":"initial")))return error("query",code);
    data=open_data(data_path);if(!data)return error("open_csv",-1);
    for(i=0;i<end;i++) {
        if(read_sample(data,i)){rc=error("read_csv",-1);goto done;}
        if(i<start)continue;
        code=scm_online_ingest(&state,config.source_id,i,&sample,1,&workspace);
        if(code){emit_query("update_failure");rc=error(code>0?"recovery_required":"ingest",code);goto done;}
        delivered++;
        if((save_cursor<save_count&&save_at[save_cursor]==state.next_index)||state.next_index%stride==0||state.next_index==end) {
            const char *reason=save_cursor<save_count&&save_at[save_cursor]==state.next_index?"checkpoint":"sample";
            if((code=emit_query(reason))){rc=error("query",code);goto done;}
        }
        if(save_cursor<save_count&&save_at[save_cursor]==state.next_index) {
            j=snprintf(checkpoint_path,sizeof(checkpoint_path),"%s-%" PRIu64 ".bin",prefix,state.next_index);
            if(j<0||(size_t)j>=sizeof(checkpoint_path)){rc=error("checkpoint_path",-1);goto done;}
            if((code=scm_online_checkpoint_save(&state,checkpoint_path,&workspace))){rc=error("checkpoint",code);goto done;}
            printf("{\"event\":\"checkpoint\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"path\":",state.next_index,state.epoch_begin);
            string(checkpoint_path);printf(",\"bytes\":%u}\n",SCM_ONLINE_CHECKPOINT_BYTES);save_cursor++;
        }
    }
    if(end==73500){do{j=fgetc(data);}while(j!=EOF&&isspace((unsigned char)j));if(j!=EOF||ferror(data)){rc=error("csv_trailing_data",-1);goto done;}}
    if(save_cursor!=save_count){rc=error("checkpoint_schedule",-1);goto done;}
    printf("{\"event\":\"complete\",\"next_index\":%" PRIu64 ",\"epoch_begin\":%" PRIu64 ",\"input_deliveries\":%" PRIu64 ",\"batch_optimizer_calls\":0}\n",state.next_index,state.epoch_begin,delivered);
    rc=fflush(stdout)||ferror(stdout)?error("output",-1):EXIT_SUCCESS;
done:
    if(fclose(data)&&rc==EXIT_SUCCESS)rc=error("close_csv",-1);
    return rc;
}
