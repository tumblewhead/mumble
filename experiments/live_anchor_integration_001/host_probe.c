/* Host-only archive producer and trace sink. The estimator receives only
 * source ID, sequence and adc12_raw_sample; no archive handle enters ctx.
 * One canonical stream, no warmup, restore, truth or fitted-anchor option. */
#include "rolling_engine.h"
#include "host_input.h"

#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define HP_QUERY_CAP UINT64_C(346501)
#define HP_PRIOR_CAP UINT64_C(315001)
#define HP_MODEL_CAP UINT64_C(6048000)
#define HP_ROUND_CAP UINT64_C(31500)
#define HP_SCHEMA "mumble_live_anchor_trace_v1"

typedef struct { double sum,correction; } hp_sum;
typedef struct {
    hp_sum signed_error,squared_error;
    double maximum_absolute_error;
} hp_error_stat;
typedef struct {
    re_context context;
    unsigned char source_id[32],record[HP_RECORD_BYTES];
    hp_observation observation;
    adc12_raw_sample raw;
    hp_quantization_error error;
    hp_error_stat dt,current,voltage;
    hp_sum source_elapsed;
    uint64_t records_read,records_encoded,records_offered,records_admitted;
    uint64_t blocks_committed,snapshots;
    uint64_t ties[4],low_rails[3],high_rails[3];
    uint64_t last_snapshot_index;
    int initialized;
} hp_host;

static hp_host host;
static unsigned char input_buffer[4096],output_buffer[65536];
static const char *const coordinate_names[16]={
    "logtau1","logtau2","logtau3","loggamma_plus","loggamma_minus","logQ_Ah",
    "R0_ohm","R1_ohm","R2_ohm","R3_ohm","H_V","initial_SOC",
    "initial_v1_V","initial_v2_V","initial_v3_V","initial_h"
};

static int add(hp_sum *s,double x)
{
    double y=s->sum+x;
    if(!isfinite(x) || !isfinite(y))return -1;
    s->correction+=fabs(s->sum)>=fabs(x)?(s->sum-y)+x:(x-y)+s->sum;
    s->sum=y;
    return isfinite(s->correction) && isfinite(s->sum+s->correction)?0:-1;
}
static double total(const hp_sum *s) { return s->sum+s->correction; }

static int error_stat(hp_error_stat *s,double error)
{
    if(add(&s->signed_error,error) || add(&s->squared_error,error*error))return -1;
    s->maximum_absolute_error=fmax(s->maximum_absolute_error,fabs(error));return 0;
}

static int record_statistics(void)
{
    unsigned i;
    if(error_stat(&host.dt,host.error.dt_s) || error_stat(&host.current,host.error.current_A) ||
       error_stat(&host.voltage,host.error.voltage_V) ||
       add(&host.source_elapsed,host.observation.dt_s))return -1;
    for(i=0;i<4u;i++)if(host.error.half_ties&(UINT32_C(1)<<i))host.ties[i]++;
    for(i=0;i<3u;i++) {
        if(host.error.rails&(UINT32_C(1)<<i))host.low_rails[i]++;
        if(host.error.rails&(UINT32_C(1)<<(i+4u)))host.high_rails[i]++;
    }
    return 0;
}

static int hex_source(const char *text,unsigned char source[32])
{
    unsigned i;
    if(strlen(text)!=64u)return -1;
    for(i=0;i<32u;i++) {
        unsigned j,value=0;
        for(j=0;j<2u;j++) {
            unsigned char c=(unsigned char)text[2u*i+j];unsigned digit;
            if(c>='0' && c<='9')digit=(unsigned)(c-'0');
            else if(c>='a' && c<='f')digit=(unsigned)(c-'a')+10u;
            else if(c>='A' && c<='F')digit=(unsigned)(c-'A')+10u;
            else return -1;
            value=value*16u+digit;
        }
        source[i]=(unsigned char)value;
    }
    return 0;
}

static void number(double x)
{
    if(isfinite(x))printf("%.17g",x);else printf("null");
}

static void point(const double *x)
{
    unsigned i;putchar('[');
    for(i=0;i<16u;i++){if(i)putchar(',');number(x[i]);}
    putchar(']');
}

static void counters(void)
{
    const ch_bank *b=&host.context.core.bank;
    printf("{\"model_steps\":%" PRIu64 ",\"qr_rows\":%" PRIu64
           ",\"query_evaluations\":%" PRIu64 ",\"prior_evaluations\":%" PRIu64
           ",\"proposal_rounds\":%" PRIu64 ",\"accepted_steps\":%" PRIu64 "}",
           b->model_steps,b->qr_rows,b->query_evaluations,b->prior_evaluations,
           b->proposal_rounds,b->accepted_steps);
}

static int within_work_caps(void)
{
    const ch_bank *b=&host.context.core.bank;
    return b->model_steps<=HP_MODEL_CAP && b->qr_rows<=HP_CANONICAL_RECORDS &&
           b->query_evaluations<=HP_QUERY_CAP && b->prior_evaluations<=HP_PRIOR_CAP &&
           b->proposal_rounds<=HP_ROUND_CAP && b->accepted_steps<=b->proposal_rounds;
}

static int snapshot(const char *kind,uint32_t search_stop,uint32_t fraction,
                    uint64_t accepted_before)
{
    re_context *c=&host.context;
    const ch_bank *b=&c->core.bank;
    const ch_result *r=&c->core.result.evidence;
    unsigned i;
    int status;
    memcpy(c->core.workspace.query.point,b->estimate,sizeof(b->estimate));
    status=re_query(c,0,1);
    if(status!=CH_OK)return status;
    if(!within_work_caps())return -201;
    if(!b->available || (r->flags&CH_FLAG_ENDPOINT_INVALID) ||
       !isfinite(r->likelihood_cost) || !isfinite(r->prior_cost) || !isfinite(r->total_cost) ||
       !isfinite(r->detail.endpoint.SOC) || !isfinite(r->detail.endpoint.h) ||
       !isfinite(b->jet.model.elapsed))return -202;
    for(i=0;i<16u;i++)if(!isfinite(b->estimate[i]))return -202;
    for(i=0;i<3u;i++)if(!isfinite(r->detail.endpoint.v[i]))return -202;
    printf("{\"schema\":\"" HP_SCHEMA "\",\"kind\":\"%s\",\"next_index\":%" PRIu64
           ",\"elapsed_s\":",kind,b->next_index);
    number(b->jet.model.elapsed);printf(",\"source_elapsed_s\":");number(total(&host.source_elapsed));
    printf(",\"x\":");point(b->estimate);
    printf(",\"endpoint\":{\"SOC\":");number(r->detail.endpoint.SOC);
    printf(",\"v_V\":[");for(i=0;i<3u;i++){if(i)putchar(',');number(r->detail.endpoint.v[i]);}
    printf("],\"h\":");number(r->detail.endpoint.h);
    printf(",\"min_support_slack\":");number(r->detail.endpoint.min_support_slack);
    printf(",\"min_endpoint_slack\":");number(r->detail.endpoint.min_endpoint_slack);
    printf("},\"likelihood_cost\":");number(r->likelihood_cost);
    printf(",\"prior_cost\":");number(r->prior_cost);
    printf(",\"total_cost\":");number(r->total_cost);
    printf(",\"flags\":%" PRIu32 ",\"search_stop_reason\":%" PRIu32
           ",\"last_fraction\":",r->flags,search_stop);
    if(fraction==UINT32_MAX)printf("null");else printf("%" PRIu32,fraction);
    printf(",\"accepted_steps_in_block\":%" PRIu64
           ",\"available\":%s,\"phase_and_flags\":%" PRIu32 ",\"counts\":",
           b->accepted_steps-accepted_before,b->available?"true":"false",c->inputs.phase_and_flags);
    counters();printf("}\n");
    if(ferror(stdout))return -203;
    host.snapshots++;host.last_snapshot_index=b->next_index;return CH_OK;
}

static void stat_json(const hp_error_stat *s)
{
    printf("{\"maximum_absolute\":");number(s->maximum_absolute_error);
    printf(",\"signed_sum\":");number(total(&s->signed_error));
    printf(",\"mean\":");
    if(host.records_encoded)number(total(&s->signed_error)/(double)host.records_encoded);else printf("null");
    printf(",\"RMS\":");
    if(host.records_encoded)number(sqrt(total(&s->squared_error)/(double)host.records_encoded));else printf("null");
    putchar('}');
}

static int finish(FILE *input,const char *stage,int code)
{
    const ch_bank *b=&host.context.core.bank;
    int failed=code!=0;
    unsigned i;
    if(input && fclose(input)!=0 && !failed){stage="input_close";code=-204;failed=1;}
    printf("{\"schema\":\"" HP_SCHEMA "\",\"kind\":\"terminal\",\"status\":\"%s\","
           "\"stage\":\"%s\",\"code\":%d,\"records_read\":%" PRIu64
           ",\"records_encoded\":%" PRIu64 ",\"records_offered\":%" PRIu64
           ",\"records_admitted\":%" PRIu64 ",\"committed_next_index\":%" PRIu64
           ",\"blocks_committed\":%" PRIu64 ",\"snapshots\":%" PRIu64
           ",\"last_snapshot_index\":%" PRIu64 ",\"counts\":",
           failed?"failed":"completed",stage,code,host.records_read,host.records_encoded,
           host.records_offered,host.records_admitted,b->next_index,host.blocks_committed,
           host.snapshots,host.last_snapshot_index);
    counters();printf(",\"counts_complete\":true,\"initialized\":%s,\"available\":%s,"
           "\"last_error\":%d,\"phase_and_flags\":%" PRIu32 ",\"last_x\":",
           host.initialized?"true":"false",b->available?"true":"false",
           b->last_error,host.context.inputs.phase_and_flags);
    if(host.initialized)point(b->estimate);else printf("null");
    printf(",\"quantization\":{\"scope\":\"successfully_encoded_records_before_offer;decoded_minus_original\","
           "\"records\":%" PRIu64 ",\"dt_s\":",host.records_encoded);
    stat_json(&host.dt);printf(",\"current_A\":");stat_json(&host.current);
    printf(",\"voltage_V\":");stat_json(&host.voltage);
    printf(",\"half_ties_V_I_T_dt\":[");
    for(i=0;i<4u;i++)printf("%s%" PRIu64,i?",":"",host.ties[i]);
    printf("],\"low_rails_V_I_T\":[");
    for(i=0;i<3u;i++)printf("%s%" PRIu64,i?",":"",host.low_rails[i]);
    printf("],\"high_rails_V_I_T\":[");
    for(i=0;i<3u;i++)printf("%s%" PRIu64,i?",":"",host.high_rails[i]);
    printf("]},\"source_elapsed_s\":");number(total(&host.source_elapsed));
    printf(",\"candidate_context_bytes\":%zu,\"host_workspace_bytes\":%zu,"
           "\"host_stdio_buffers_bytes\":%zu,\"truth_reads\":0,\"historical_candidate_reads\":0,"
           "\"original_fitter_calls\":0,\"source_generations\":0,\"retries\":0,"
           "\"coverage_validated\":false,\"target_measured\":false}\n",
           sizeof(re_context),sizeof(host),sizeof(input_buffer)+sizeof(output_buffer));
    if(fflush(stdout)!=0 || ferror(stdout))return 1;
    return failed?1:0;
}

int main(int argc,char **argv)
{
    const char *path=NULL,*source=NULL;
    FILE *input;
    uint64_t index;
    unsigned i;
    int status;
    if(argc==2 && strcmp(argv[1],"--help")==0) {
        puts("host_probe --observations PATH --records 504000 --source-id HEX64 --rounds-per-block 1");return 0;
    }
    if(argc!=9) { fputs("Expected four explicit host-probe arguments\n",stderr);return 2; }
    if(strcmp(argv[1],"--observations") || strcmp(argv[3],"--records") || strcmp(argv[4],"504000") ||
       strcmp(argv[5],"--source-id") || strcmp(argv[7],"--rounds-per-block") || strcmp(argv[8],"1")) {
        fputs("Canonical host-probe argument contract differs\n",stderr);return 2;
    }
    path=argv[2];source=argv[6];
    if(hex_source(source,host.source_id)) { fputs("Invalid source ID\n",stderr);return 2; }
    if(setvbuf(stdout,(char *)output_buffer,_IOFBF,sizeof(output_buffer))!=0)return 2;
    printf("{\"schema\":\"" HP_SCHEMA "\",\"kind\":\"header\",\"source_id\":\"%s\","
           "\"records_requested\":504000,\"block_records\":16,\"rounds_per_block\":1,"
           "\"coordinate_names\":[",source);
    for(i=0;i<16u;i++)printf("%s\"%s\"",i?",":"",coordinate_names[i]);
    printf("],\"coordinate_semantics\":\"original_entering_chart;endpoint_states_separate\","
           "\"sigma_V\":0.001,\"likelihood\":\"decoded_point_Gaussian_quantized_input_approximation\","
           "\"calibration\":{\"V_offset\":1.5,\"V_gain\":0.0009765625,"
           "\"I_offset\":-0.256,\"I_gain\":0.000125,\"T_offset\":-40,\"T_gain\":0.0625,"
           "\"seconds_per_tick\":%.17g,\"synthetic_temperature_C\":25},"
           "\"rounding\":\"floor(q+0.5);reject_outside_span_before_rounding\","
           "\"candidate_context_bytes\":%zu,\"temperature_compensation\":false,"
           "\"history_fidelity_verified\":false,\"coverage_validated\":false}\n",
           hp_fixture_calibration.seconds_per_tick,sizeof(re_context));
    input=fopen(path,"rb");
    if(!input)return finish(NULL,"input_open",-205);
    if(setvbuf(input,(char *)input_buffer,_IOFBF,sizeof(input_buffer))!=0)
        return finish(input,"input_buffer",-206);
    status=re_init(&host.context,host.source_id,&hp_fixture_calibration);
    if(status!=CH_OK)return finish(input,"initialization",status);
    host.initialized=1;
    status=snapshot("initial",CH_STOP_NONE,UINT32_MAX,0);
    if(status!=CH_OK)return finish(input,"initial_query",status);
    for(index=0;index<HP_CANONICAL_RECORDS;index++) {
        size_t bytes=fread(host.record,1,HP_RECORD_BYTES,input);
        if(bytes!=HP_RECORD_BYTES)return finish(input,"input_short_or_read_error",-207);
        host.records_read++;
        status=hp_decode_record(host.record,&host.observation);
        if(status!=HP_OK)return finish(input,"record_decode",status);
        status=hp_encode(index,&host.observation,&host.raw,&host.error);
        if(status!=HP_OK)return finish(input,"record_encoding",status);
        host.records_encoded++;
        if(record_statistics())return finish(input,"quantization_statistics",-208);
        status=re_offer(&host.context,host.source_id,index,&host.raw);
        if(status!=CH_OK)return finish(input,"offer",status);
        host.records_offered++;
        status=re_admit(&host.context);
        if(status!=CH_OK)return finish(input,"admit",status);
        host.records_admitted++;
        if(host.context.inputs.ingress_count!=0u ||
           host.context.inputs.block_count!=host.records_admitted-host.context.core.bank.next_index)
            return finish(input,"ownership_accounting",-209);
        if(host.context.inputs.block_count==16u) {
            uint64_t accepted_before=host.context.core.bank.accepted_steps;
            uint32_t stop,fraction;
            status=re_process(&host.context,1u);
            if(status!=CH_OK)return finish(input,"process",status);
            host.blocks_committed++;
            stop=host.context.core.result.evidence.stop_reason;
            fraction=host.context.core.result.evidence.fraction;
            if(host.context.core.bank.next_index!=host.records_admitted ||
               host.context.inputs.block_count!=0u || host.context.inputs.ingress_count!=0u ||
               !within_work_caps())return finish(input,"post_commit_accounting",-210);
            status=snapshot("block",stop,fraction,accepted_before);
            if(status!=CH_OK)return finish(input,"post_commit_query",status);
        }
    }
    if(fgetc(input)!=EOF || ferror(input))return finish(input,"input_trailing_or_read_error",-211);
    if(host.context.core.bank.next_index!=HP_CANONICAL_RECORDS ||
       host.context.core.bank.qr_rows!=HP_CANONICAL_RECORDS || host.blocks_committed!=UINT64_C(31500) ||
       host.snapshots!=UINT64_C(31501) || !within_work_caps())
        return finish(input,"final_accounting",-212);
    return finish(input,"complete",0);
}
