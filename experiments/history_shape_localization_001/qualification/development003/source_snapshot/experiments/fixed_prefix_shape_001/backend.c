/* Host-only forensic capture and fixed-node reference. No optimizer calls.
 * Binary checkpoint is explicitly local ABI, never a firmware persistence ABI.
 * The supervisor binds every input/source/output by SHA256 before use. */
#include "../live_anchor_integration_001/rolling_engine.h"
#include "../live_anchor_integration_001/host_input.h"
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef char binary64[(sizeof(double)==8 && DBL_MANT_DIG==53) ? 1 : -1];
typedef struct {
    char magic[8];
    uint64_t bank_bytes, input_bytes, calibration_bytes;
    ch_bank bank;
    lab_input_store inputs;
    adc12_calibration calibration;
} fp_checkpoint;
typedef struct {
    uint64_t index;
    double values[27]; /* x16, elapsed, likelihood, prior, total, endpoint7 */
    uint32_t flags, phase, available;
} fp_expected;
typedef struct {
    double cost, allowance, endpoint[5];
    uint64_t steps, predictions, records;
    int status;
} fp_reference;

static re_context ctx;
static uint64_t checked;

static double up(double x) { return nextafter(x, INFINITY); }
static double plus(double a,double b) { return up(a+b); }
static double times(double a,double b) { return up(a*b); }
static double guard(uint64_t n,double scale)
{
    double nu=times((double)n,0x1p-53);
    double g=up(nu/nextafter(1.-nu,-INFINITY));
    return plus(times(g,scale),times((double)n,0x0.0000000000001p-1022));
}
static void vector(const double *v,unsigned n)
{
    unsigned i;putchar('[');
    for(i=0;i<n;i++)printf("%s%.17g",i?",":"",v[i]);
    putchar(']');
}
static int read_exact(FILE *f,void *p,size_t n) { return fread(p,1,n,f)==n?0:-1; }
static int read_expected(FILE *f,fp_expected *e)
{
    return read_exact(f,&e->index,8) || read_exact(f,e->values,sizeof(e->values)) ||
        read_exact(f,&e->flags,4) || read_exact(f,&e->phase,4) || read_exact(f,&e->available,4);
}
static void values(const re_context *c,double out[27])
{
    const ch_result *r=&c->core.result.evidence;
    memcpy(out,c->core.bank.estimate,16*sizeof(double));
    out[16]=c->core.bank.jet.model.elapsed;
    out[17]=r->likelihood_cost;out[18]=r->prior_cost;out[19]=r->total_cost;
    out[20]=r->detail.endpoint.SOC;
    memcpy(out+21,r->detail.endpoint.v,3*sizeof(double));
    out[24]=r->detail.endpoint.h;out[25]=r->detail.endpoint.min_support_slack;
    out[26]=r->detail.endpoint.min_endpoint_slack;
}
static int parity(re_context *c,const fp_expected *e)
{
    double actual[27];unsigned i;int status;
    memcpy(c->core.workspace.query.point,c->core.bank.estimate,16*sizeof(double));
    status=re_query(c,0,1);if(status)return status;
    values(c,actual);
    for(i=0;i<27;i++)if(!isfinite(e->values[i]) || memcmp(actual+i,e->values+i,8)) {
        fprintf(stderr,"Snapshot parity failure index=%" PRIu64 " field=%u actual=%a expected=%a\n",
                e->index,i,actual[i],e->values[i]);return -101;
    }
    if(c->core.bank.next_index!=e->index || c->core.result.evidence.flags!=e->flags ||
       c->inputs.phase_and_flags!=e->phase || c->core.bank.available!=e->available)return -102;
    checked++;return 0;
}
static int record(FILE *f,uint64_t index,adc12_raw_sample *raw,adc12_reading *decoded)
{
    unsigned char bytes[32];hp_observation observation;hp_quantization_error error;
    if(read_exact(f,bytes,sizeof(bytes)))return -103;
    if(hp_decode_record(bytes,&observation) || hp_encode(index,&observation,raw,&error))return -104;
    return adc12_convert(raw,&hp_fixture_calibration,decoded);
}
static int source_id(const char *s,unsigned char id[32])
{
    unsigned i;if(strlen(s)!=64)return -1;
    for(i=0;i<32;i++) {
        unsigned a,b;char x=s[2*i],y=s[2*i+1];
        if(x>='0'&&x<='9')a=(unsigned)(x-'0');else if(x>='a'&&x<='f')a=(unsigned)(x-'a'+10);else return -1;
        if(y>='0'&&y<='9')b=(unsigned)(y-'0');else if(y>='a'&&y<='f')b=(unsigned)(y-'a'+10);else return -1;
        id[i]=(unsigned char)(16*a+b);
    }
    return 0;
}
static void canonical_inputs(lab_input_store *out,const lab_input_store *in)
{
    unsigned i;
    memset(out,0,sizeof(*out));
    for(i=0;i<LAB_BLOCK_DEPTH+LAB_INGRESS_DEPTH;i++) {
        adc12_raw_sample *a=i<LAB_BLOCK_DEPTH?out->retained+i:out->ingress+i-LAB_BLOCK_DEPTH;
        const adc12_raw_sample *b=i<LAB_BLOCK_DEPTH?in->retained+i:in->ingress+i-LAB_BLOCK_DEPTH;
        a->interval_ticks=b->interval_ticks;a->codes.voltage=b->codes.voltage;
        a->codes.current=b->codes.current;a->codes.temperature=b->codes.temperature;
    }
    out->next_ingress_sequence=in->next_ingress_sequence;
    out->ingress_head=in->ingress_head;out->ingress_count=in->ingress_count;
    out->block_count=in->block_count;out->phase_and_flags=in->phase_and_flags;
}
static void checkpoint_pack(fp_checkpoint *s,const re_context *c)
{
    memset(s,0,sizeof(*s));memcpy(s->magic,"FPSH001",8);
    s->bank_bytes=sizeof(s->bank);s->input_bytes=sizeof(s->inputs);
    s->calibration_bytes=sizeof(s->calibration);
    s->bank=c->core.bank;canonical_inputs(&s->inputs,&c->inputs);s->calibration=c->calibration;
}
static int checkpoint_load(const char *path,re_context *c)
{
    fp_checkpoint s;FILE *f=fopen(path,"rb");int bad;
    if(!f)return -105;
    bad=read_exact(f,&s,sizeof(s)) || fgetc(f)!=EOF || ferror(f);fclose(f);
    if(bad || memcmp(s.magic,"FPSH001",8) || s.bank_bytes!=sizeof(s.bank) ||
       s.input_bytes!=sizeof(s.inputs) || s.calibration_bytes!=sizeof(s.calibration) ||
       s.inputs.block_count || s.inputs.ingress_count || !s.bank.available ||
       s.inputs.next_ingress_sequence!=s.bank.next_index ||
       (s.inputs.phase_and_flags&RE_PHASE_MASK)!=RE_PHASE_READY ||
       memcmp(&s.calibration,&hp_fixture_calibration,sizeof(s.calibration)))return -106;
    memset(c,0,sizeof(*c));c->core.bank=s.bank;c->inputs=s.inputs;c->calibration=s.calibration;
    return 0;
}
static int capture(const char *observations,const char *expected,const char *snapshot,
                   const char *id_text,uint64_t prefix)
{
    FILE *obs=NULL,*expf=NULL,*out=NULL;fp_expected e;fp_checkpoint s;
    unsigned char id[32];uint64_t i;int status=-107;
    adc12_raw_sample raw={0,{0,0,0}};adc12_reading decoded;
    if(source_id(id_text,id) || prefix>252000 || prefix%16)return -108;
    obs=fopen(observations,"rb");expf=fopen(expected,"rb");
    if(!obs || !expf)goto done;
    status=re_init(&ctx,id,&hp_fixture_calibration);if(status)goto done;
    if(read_expected(expf,&e) || e.index!=0){status=-109;goto done;}
    status=parity(&ctx,&e);if(status)goto done;
    for(i=0;i<prefix;i++) {
        status=record(obs,i,&raw,&decoded);if(status)goto done;
        status=re_offer(&ctx,id,i,&raw);if(status)goto done;
        status=re_admit(&ctx);if(status)goto done;
        if(ctx.inputs.block_count==16) {
            if(read_expected(expf,&e) || e.index!=i+1){status=-110;goto done;}
            memcpy(ctx.core.bank.estimate,e.values,16*sizeof(double));
            status=re_commit(&ctx);if(status)goto done;
            status=parity(&ctx,&e);if(status)goto done;
            if(checked%1000==0) {
                printf("{\"kind\":\"progress\",\"checked_snapshots\":%" PRIu64 "}\n",checked);fflush(stdout);
            }
        }
    }
    if(fgetc(expf)!=EOF || ferror(expf)){status=-111;goto done;}
    memcpy(ctx.core.workspace.query.point,ctx.core.bank.estimate,16*sizeof(double));
    status=re_query(&ctx,1,1);if(status)goto done;
    if(ctx.core.bank.model_steps!=2*prefix || ctx.core.bank.qr_rows!=prefix ||
       ctx.core.bank.query_evaluations!=2*(prefix/16)+2 ||
       ctx.core.bank.prior_evaluations!=prefix/16+2 ||
       ctx.core.bank.proposal_rounds || ctx.core.bank.accepted_steps ||
       checked!=prefix/16+1){status=-112;goto done;}
    checkpoint_pack(&s,&ctx);out=fopen(snapshot,"wbx");if(!out){status=-113;goto done;}
    if(fwrite(&s,1,sizeof(s),out)!=sizeof(s)){status=-114;goto done;}
    if(fclose(out)){out=NULL;status=-115;goto done;}out=NULL;
    printf("{\"kind\":\"capture\",\"prefix\":%" PRIu64 ",\"checked_snapshots\":%" PRIu64 ",\"anchor\":",prefix,checked);
    vector(ctx.core.bank.estimate,16);printf(",\"metric_packed_lower\":");vector(ctx.core.workspace.query.packed,136);
    printf(",\"public_sd\":");vector(ch_public_sd,16);printf(",\"lower\":");vector(ch_lower,16);
    printf(",\"upper\":");vector(ch_upper,16);
    printf(",\"charge_min_Ah\":%.17g,\"charge_max_Ah\":%.17g,\"charge_Ah\":%.17g,"
           "\"model_steps\":%" PRIu64 ",\"qr_rows\":%" PRIu64 ",\"query_evaluations\":%" PRIu64
           ",\"prior_evaluations\":%" PRIu64 ",\"optimizer_calls\":0,\"truth_reads\":0,"
           "\"ABI\":{\"checkpoint_bytes\":%zu,\"bank_bytes\":%zu,\"inputs_bytes\":%zu,\"calibration_bytes\":%zu,"
           "\"bank_offset\":%zu,\"inputs_offset\":%zu,\"calibration_offset\":%zu,\"double_bytes\":8,\"compiler\":\"%s\"}}\n",
           ctx.core.bank.charge_min_Ah,ctx.core.bank.charge_max_Ah,ctx.core.bank.jet.model.charge_Ah,
           ctx.core.bank.model_steps,ctx.core.bank.qr_rows,ctx.core.bank.query_evaluations,ctx.core.bank.prior_evaluations,
           sizeof(s),sizeof(s.bank),sizeof(s.inputs),sizeof(s.calibration),offsetof(fp_checkpoint,bank),
           offsetof(fp_checkpoint,inputs),offsetof(fp_checkpoint,calibration),__VERSION__);
done:
    if(obs)fclose(obs);
    if(expf)fclose(expf);
    if(out)fclose(out);
    if(status) {
        fprintf(stderr,"Capture stopped status=%d checked=%" PRIu64 " committed=%" PRIu64 "\n",status,checked,ctx.core.bank.next_index);
        printf("{\"kind\":\"capture_failure\",\"code\":%d,\"checked_snapshots\":%" PRIu64
               ",\"committed\":%" PRIu64 ",\"model_steps\":%" PRIu64 ",\"qr_rows\":%" PRIu64
               ",\"query_evaluations\":%" PRIu64 ",\"prior_evaluations\":%" PRIu64 "}\n",
               status,checked,ctx.core.bank.next_index,ctx.core.bank.model_steps,ctx.core.bank.qr_rows,
               ctx.core.bank.query_evaluations,ctx.core.bank.prior_evaluations);
    }
    return status;
}

static fp_reference reference(FILE *obs,const double x[16],uint64_t prefix)
{
    fp_reference out={0};scm_model_state model;scm_model_row row;
    double theta[7],alpha[9],sum=0.,correction=0.,sum_upper=0.,term_allowance=0.;
    adc12_raw_sample raw={0,{0,0,0}};adc12_reading decoded;
    unsigned j;uint64_t i;
    for(j=0;j<16;j++)if(!isfinite(x[j]) || x[j]<ch_lower[j] || x[j]>ch_upper[j]){out.status=-120;return out;}
    for(j=0;j<5;j++)theta[j]=x[j];
    theta[5]=x[11];theta[6]=x[5];
    for(j=0;j<5;j++)alpha[j]=x[6+j];
    for(j=0;j<3;j++)alpha[5+j]=x[12+j];
    alpha[8]=x[10]*x[15];
    out.status=scm_model_init(&model,3,theta);if(out.status)return out;
    if(fseek(obs,0,SEEK_SET)){out.status=-121;return out;}
    for(i=0;i<prefix;i++) {
        double mu,r,cost,next,a,epsilon,local;
        out.status=record(obs,i,&raw,&decoded);if(out.status)return out;out.records++;
        out.steps++;out.status=scm_model_step(&model,NULL,decoded.dt_s,decoded.current_A,&row);
        if(out.status)return out;
        out.predictions++;out.status=scm_model_predict(&row,3,alpha,&mu,NULL);if(out.status)return out;
#ifdef FP_NO_MAIN
        printf("{\"kind\":\"computed_operand\",\"index\":%" PRIu64 ",\"mu\":%.17g,\"V\":%.17g,\"I\":%.17g,\"dt\":%.17g}\n",
               i,mu,decoded.voltage_V,decoded.current_A,decoded.dt_s);
#endif
        r=(mu-decoded.voltage_V)/RE_SIGMA_V;cost=.5*r*r;next=sum+cost;
        if(!isfinite(cost) || !isfinite(next)){out.status=-122;return out;}
        correction+=fabs(sum)>=fabs(cost)?(sum-next)+cost:(cost-next)+sum;sum=next;
        sum_upper=plus(sum_upper,cost);
        /* Computed mu and decoded V are fixed operands. This deliberately
         * excludes forward error of recurrence, prediction and libm. */
        a=up(plus(fabs(mu),fabs(decoded.voltage_V))/RE_SIGMA_V);
        epsilon=guard(8,a);
        local=plus(times(epsilon,plus(fabs(r),times(.5,epsilon))),guard(4,cost));
        term_allowance=plus(term_allowance,local);
    }
    out.cost=sum+correction;
    out.allowance=plus(guard(8*prefix+32,sum_upper),term_allowance);
    out.endpoint[0]=model.z0-model.charge_Ah/model.Q;
    for(j=0;j<3;j++)out.endpoint[j+1]=x[j+7]*model.f[j]+x[j+12]*model.a[j];
    out.endpoint[4]=model.hb+x[15]*model.ha;
    if(!isfinite(out.cost) || !isfinite(out.allowance)){out.status=-123;return out;}
    for(j=0;j<5;j++)if(!isfinite(out.endpoint[j])){out.status=-124;return out;}
    return out;
}
static int evaluate(const char *observations,const char *snapshot,const char *nodes,uint64_t prefix,unsigned count)
{
    FILE *obs=NULL,*nf=NULL;unsigned k,j;int status=checkpoint_load(snapshot,&ctx);
    uint64_t steps=0,predicts=0,queries=ctx.core.bank.query_evaluations;
    if(status || count>545 || !count || prefix>252000 || ctx.core.bank.next_index!=prefix)return -130;
    obs=fopen(observations,"rb");nf=fopen(nodes,"rb");if(!obs || !nf){status=-131;goto done;}
    for(k=0;k<count;k++) {
        double x[16],rep_endpoint[5]={0},rep_cost=0.,rep_allowance=0.;int represented;
        fp_reference ref;
        if(read_exact(nf,x,sizeof(x))){status=-132;goto done;}
        for(j=0;j<16;j++)if(!isfinite(x[j])){status=-136;goto done;}
        memcpy(ctx.core.workspace.query.point,x,sizeof(x));represented=re_query(&ctx,0,0);
        if(!represented && (ctx.core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID))represented=-133;
        if(!represented) {
            rep_cost=ctx.core.result.evidence.likelihood_cost;
            rep_allowance=guard(16384,ctx.core.result.evidence.cost_absolute_scale);
            rep_endpoint[0]=ctx.core.result.evidence.detail.endpoint.SOC;
            for(j=0;j<3;j++)rep_endpoint[j+1]=ctx.core.result.evidence.detail.endpoint.v[j];
            rep_endpoint[4]=ctx.core.result.evidence.detail.endpoint.h;
        }
        ref=reference(obs,x,prefix);steps+=ref.steps;predicts+=ref.predictions;
        printf("{\"kind\":\"node\",\"index\":%u,\"x\":",k);vector(x,16);
        printf(",\"status\":\"%s\",\"represented_status\":%d,\"reference_status\":%d,\"model_steps\":%" PRIu64,
               !represented&&!ref.status?"available":"unavailable",represented,ref.status,ref.steps);
        if(!represented && !ref.status) {
            printf(",\"represented_likelihood_cost\":%.17g,\"reference_likelihood_cost\":%.17g,"
                   "\"represented_cost_allowance\":%.17g,\"reference_cost_allowance\":%.17g,\"represented_endpoint\":",
                   rep_cost,ref.cost,rep_allowance,ref.allowance);
            vector(rep_endpoint,5);printf(",\"reference_endpoint\":");vector(ref.endpoint,5);
        } else printf(",\"reason\":\"represented_status_%d_reference_status_%d\"",represented,ref.status);
        printf("}\n");if(fflush(stdout) || ferror(stdout)){status=-134;goto done;}
    }
    if(fgetc(nf)!=EOF || ferror(nf)){status=-135;goto done;}
    printf("{\"kind\":\"terminal\",\"nodes\":%u,\"model_steps\":%" PRIu64 ",\"predict_calls\":%" PRIu64
           ",\"represented_queries\":%" PRIu64 ",\"optimizer_calls\":0,\"prior_calls\":0,\"truth_reads\":0}\n",
           count,steps,predicts,ctx.core.bank.query_evaluations-queries);
done:
    if(obs)fclose(obs);
    if(nf)fclose(nf);
    return status;
}
#ifndef FP_NO_MAIN
int main(int argc,char **argv)
{
    uint16_t endian=1;uint64_t prefix;char *end;int result;
    if(*(unsigned char *)&endian!=1 || argc!=7)return 2;
    prefix=strtoull(argv[6],&end,10);if(*end || prefix>252000)return 2;
    if(!strcmp(argv[1],"capture"))result=capture(argv[2],argv[3],argv[4],argv[5],prefix);
    else if(!strcmp(argv[1],"evaluate")) {
        unsigned long count=strtoul(argv[5],&end,10);if(*end || count>545)return 2;
        result=evaluate(argv[2],argv[3],argv[4],prefix,(unsigned)count);
    } else return 2;
    if(result)fprintf(stderr,"Backend stopped: %d\n",result);
    return result || fflush(stdout) || ferror(stdout)?1:0;
}
#endif
