/* Postclosure-only reference: one fixed candidate, unchanged original model,
 * identical ADC producer/decode, no fit/prior/feedback into the live engine. */
#include "host_input.h"
#include "../compact_nonlinear_history_001/compact_history.h"
#include "scm_model.h"

#include <ctype.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define AUDIT_SCHEMA "mumble_live_anchor_exact_audit_v1"

typedef struct {
    double x[16],theta[7],alpha[9];
    scm_model_state model;
    scm_model_row row;
    hp_observation observation;
    adc12_raw_sample raw;
    hp_quantization_error error;
    adc12_reading decoded;
    unsigned char bytes[32];
    double sum,correction,naive_cost,last_voltage;
    uint64_t prefix,records_read,records_accumulated,init_calls,step_calls,predict_calls;
    int point_available;
} audit_workspace;

static audit_workspace w;
static unsigned char input_buffer[4096];

static int read_point(const char *path)
{
    FILE *f=fopen(path,"rb");char token[128],*end;unsigned i;int extra;
    if(!f)return -1;
    for(i=0;i<16u;i++) {
        if(fscanf(f,"%127s",token)!=1){fclose(f);return -1;}
        w.x[i]=strtod(token,&end);
        if(end==token || *end || !isfinite(w.x[i])){fclose(f);return -1;}
    }
    do{extra=fgetc(f);}while(extra!=EOF && isspace((unsigned char)extra));
    if(extra!=EOF || ferror(f)){fclose(f);return -1;}
    if(fclose(f)!=0)return -1;
    w.point_available=1;return 0;
}

static int source_valid(const char *id)
{
    unsigned i;
    if(strlen(id)!=64u)return 0;
    for(i=0;i<64u;i++)if(!((id[i]>='0' && id[i]<='9') || (id[i]>='a' && id[i]<='f')))return 0;
    return 1;
}

static void number(double x)
{
    if(isfinite(x))printf("%.17g",x);else printf("null");
}

static int close_result(FILE *input,const char *source,const char *status,
                        const char *stage,int code,int exit_status)
{
    unsigned i;
    int available=strcmp(status,"available")==0;
    if(input && fclose(input)!=0){status="failed";stage="input_close";code=-301;exit_status=1;available=0;}
    printf("{\"schema\":\"" AUDIT_SCHEMA "\",\"status\":\"%s\",\"source_id\":\"%s\","
           "\"stage\":\"%s\",\"code\":%d,\"prefix\":%" PRIu64 ",\"x\":",status,source,stage,code,w.prefix);
    if(w.point_available){putchar('[');for(i=0;i<16u;i++){if(i)putchar(',');number(w.x[i]);}putchar(']');}
    else printf("null");
    printf(",\"records_read\":%" PRIu64 ",\"records_accumulated\":%" PRIu64
           ",\"model_init_calls\":%" PRIu64 ",\"model_steps\":%" PRIu64
           ",\"model_predict_calls\":%" PRIu64 ",\"counts_complete\":true,\"likelihood_cost\":",
           w.records_read,w.records_accumulated,w.init_calls,w.step_calls,w.predict_calls);
    if(available)number(w.sum+w.correction);else printf("null");
    printf(",\"partial_likelihood_cost\":");number(w.sum+w.correction);
    printf(",\"naive_cost\":");number(w.naive_cost);
    printf(",\"endpoint\":");
    if(available) {
        printf("{\"SOC\":");number(w.row.z);
        printf(",\"v_V\":[");
        for(i=0;i<3u;i++){if(i)putchar(',');number(w.x[7u+i]*w.model.f[i]+w.x[12u+i]*w.model.a[i]);}
        printf("],\"h\":");number(w.model.hb+w.x[15]*w.model.ha);
        printf(",\"elapsed_s\":");number(w.model.elapsed);
        printf(",\"charge_Ah\":");number(w.model.charge_Ah);
        printf(",\"predicted_voltage_V\":");number(w.last_voltage);putchar('}');
    } else printf("null");
    printf(",\"workspace_bytes\":%zu,\"input_buffer_bytes\":%zu,\"sigma_V\":0.001,"
           "\"input_semantics\":\"identical_ADC_encode_decode_as_candidate\","
           "\"optimizer_calls\":0,\"prior_calls\":0,\"truth_reads\":0,\"candidate_mutations\":0,"
           "\"arithmetic_scope\":\"compensated_sum_of_computed_binary64_residual_squares;not_a_full_real_model_error_bound\"}\n",
           sizeof(w),sizeof(input_buffer));
    if(fflush(stdout)!=0 || ferror(stdout))return 1;
    return exit_status;
}

int main(int argc,char **argv)
{
    const char *path,*point_path,*source;
    FILE *input;
    uint64_t index;
    unsigned i;
    int status;
    if(argc==2 && strcmp(argv[1],"--help")==0) {
        puts("host_exact_audit --observations PATH --prefix 252000|294000|504000 --point PATH --source-id HEX64");return 0;
    }
    if(argc!=9 || strcmp(argv[1],"--observations") || strcmp(argv[3],"--prefix") ||
       strcmp(argv[5],"--point") || strcmp(argv[7],"--source-id")) {
        fputs("Audit argument contract differs\n",stderr);return 2;
    }
    path=argv[2];point_path=argv[6];source=argv[8];
    if(!strcmp(argv[4],"252000"))w.prefix=UINT64_C(252000);
    else if(!strcmp(argv[4],"294000"))w.prefix=UINT64_C(294000);
    else if(!strcmp(argv[4],"504000"))w.prefix=UINT64_C(504000);
    else {fputs("Audit prefix is not predeclared\n",stderr);return 2;}
    if(!source_valid(source)){fputs("Invalid source ID\n",stderr);return 2;}
    if(read_point(point_path))return close_result(NULL,source,"failed","point_input",-302,1);
    for(i=0;i<16u;i++)if(w.x[i]<ch_lower[i] || w.x[i]>ch_upper[i])
        return close_result(NULL,source,"unavailable","point_support",SCM_ERR_DOMAIN,0);
    for(i=0;i<5u;i++)w.theta[i]=w.x[i];
    w.theta[5]=w.x[11];w.theta[6]=w.x[5];
    for(i=0;i<5u;i++)w.alpha[i]=w.x[6u+i];
    for(i=0;i<3u;i++)w.alpha[5u+i]=w.x[12u+i];
    w.alpha[8]=w.x[10]*w.x[15];
    w.init_calls++;
    status=scm_model_init(&w.model,3,w.theta);
    if(status!=SCM_OK)return close_result(NULL,source,"unavailable","model_init",status,0);
    input=fopen(path,"rb");
    if(!input)return close_result(NULL,source,"failed","input_open",-303,1);
    if(setvbuf(input,(char *)input_buffer,_IOFBF,sizeof(input_buffer))!=0)
        return close_result(input,source,"failed","input_buffer",-304,1);
    for(index=0;index<w.prefix;index++) {
        double residual,cost,next;
        if(fread(w.bytes,1,sizeof(w.bytes),input)!=sizeof(w.bytes))
            return close_result(input,source,"failed","input_short_or_read_error",-305,1);
        w.records_read++;
        status=hp_decode_record(w.bytes,&w.observation);
        if(status)return close_result(input,source,"failed","record_decode",status,1);
        status=hp_encode(index,&w.observation,&w.raw,&w.error);
        if(status)return close_result(input,source,"failed","record_encode",status,1);
        status=adc12_convert(&w.raw,&hp_fixture_calibration,&w.decoded);
        if(status)return close_result(input,source,"failed","record_convert",status,1);
        w.step_calls++;
        status=scm_model_step(&w.model,NULL,w.decoded.dt_s,w.decoded.current_A,&w.row);
        if(status!=SCM_OK)return close_result(input,source,"unavailable","exact_model_step",status,0);
        w.predict_calls++;
        status=scm_model_predict(&w.row,3,w.alpha,&w.last_voltage,NULL);
        if(status!=SCM_OK)return close_result(input,source,"unavailable","exact_model_prediction",status,0);
        residual=(w.last_voltage-w.decoded.voltage_V)/0.001;
        cost=0.5*residual*residual;next=w.sum+cost;
        if(!isfinite(cost) || !isfinite(next))return close_result(input,source,"unavailable","cost_overflow",-306,0);
        w.correction+=fabs(w.sum)>=fabs(cost)?(w.sum-next)+cost:(cost-next)+w.sum;
        w.sum=next;w.naive_cost+=cost;
        if(!isfinite(w.correction) || !isfinite(w.sum+w.correction) || !isfinite(w.naive_cost))
            return close_result(input,source,"unavailable","cost_sum_overflow",-307,0);
        w.records_accumulated++;
    }
    return close_result(input,source,"available","complete",0,0);
}
