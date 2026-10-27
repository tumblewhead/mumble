/* External finite harness. No archive or accepted-anchor API enters candidate. */
#include "rolling_engine.h"
#include "features.h"
#include "../live_anchor_integration_001/host_input.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
typedef struct {
    char magic[8];uint64_t bank_bytes,input_bytes,calibration_bytes;
    ch_bank bank;lab_input_store inputs;adc12_calibration calibration;
} sh_snapshot;
size_t sh_context_bytes(void){return sizeof(re_context);}
size_t sh_snapshot_bytes(void){return sizeof(sh_snapshot);}
int sh_save(const char *path,const re_context *c)
{
    sh_snapshot s;FILE *f;unsigned i;
    memset(&s,0,sizeof(s));memcpy(s.magic,SH_BANK_MAGIC,8);
    s.bank_bytes=sizeof(s.bank);s.input_bytes=sizeof(s.inputs);s.calibration_bytes=sizeof(s.calibration);
    s.bank=c->core.bank;s.calibration=c->calibration;
    for(i=0;i<24;i++) {
        const adc12_raw_sample *a=i<16?c->inputs.retained+i:c->inputs.ingress+i-16;
        adc12_raw_sample *b=i<16?s.inputs.retained+i:s.inputs.ingress+i-16;
        b->interval_ticks=a->interval_ticks;b->codes=a->codes;
    }
    s.inputs.next_ingress_sequence=c->inputs.next_ingress_sequence;
    s.inputs.ingress_head=c->inputs.ingress_head;s.inputs.ingress_count=c->inputs.ingress_count;
    s.inputs.block_count=c->inputs.block_count;s.inputs.phase_and_flags=c->inputs.phase_and_flags;
    f=fopen(path,"wbx");if(!f)return -101;
    i=fwrite(&s,1,sizeof(s),f)==sizeof(s);if(fclose(f))i=0;return i?0:-102;
}
int sh_load(const char *path,re_context *c)
{
    sh_snapshot s;FILE *f=fopen(path,"rb");int bad;
    if(!f)return -103;
    bad=fread(&s,1,sizeof(s),f)!=sizeof(s) || fgetc(f)!=EOF;fclose(f);
    if(bad || memcmp(s.magic,SH_BANK_MAGIC,8) || s.bank_bytes!=sizeof(s.bank) ||
       s.input_bytes!=sizeof(s.inputs) || s.calibration_bytes!=sizeof(s.calibration) ||
       s.inputs.block_count || s.inputs.ingress_count || !s.bank.available ||
       s.inputs.next_ingress_sequence!=s.bank.next_index ||
       (s.inputs.phase_and_flags&RE_PHASE_MASK)!=RE_PHASE_READY ||
       memcmp(&s.calibration,&hp_fixture_calibration,sizeof(s.calibration)))return -104;
    memset(c,0,sizeof(*c));c->core.bank=s.bank;c->inputs=s.inputs;c->calibration=s.calibration;return 0;
}
#ifndef SH_NO_MAIN
static re_context ctx;
static void vector(const double *x,unsigned n)
{
    unsigned i;putchar('[');for(i=0;i<n;i++)printf("%s%.17g",i?",":"",x[i]);putchar(']');
}
static int expected(FILE *f,uint64_t index,double *x)
{
    unsigned char row[236];uint64_t actual;
    if(fread(row,1,236,f)!=236)return -105;
    memcpy(&actual,row,8);if(actual!=index)return -106;
    memcpy(x,row+8,128);return 0;
}
static int source_id(const char *s,unsigned char *id)
{
    unsigned i;if(strlen(s)!=64)return -107;
    for(i=0;i<32;i++) {
        unsigned a,b;char x=s[2*i],y=s[2*i+1];
        if(x>='0'&&x<='9')a=(unsigned)(x-'0');else if(x>='a'&&x<='f')a=(unsigned)(x-'a'+10);else return -107;
        if(y>='0'&&y<='9')b=(unsigned)(y-'0');else if(y>='a'&&y<='f')b=(unsigned)(y-'a'+10);else return -107;
        id[i]=(unsigned char)(a*16+b);
    }return 0;
}
static int run(int argc,char **argv)
{
    FILE *obs,*expf,*nf;uint64_t i,prefix;unsigned nodes,k;unsigned char id[32],bytes[32];
    hp_observation o;hp_quantization_error error;adc12_raw_sample raw;int status;char *end;
    if(argc!=9 || strcmp(argv[1],"run"))return -108;
    prefix=strtoull(argv[6],&end,10);if(*end || !prefix || prefix>252000 || prefix%16)return -108;
    nodes=(unsigned)strtoul(argv[7],&end,10);if(*end || !nodes || nodes>545)return -108;
    if(source_id(argv[8],id) || re_init(&ctx,id,&hp_fixture_calibration))return -109;
    obs=fopen(argv[2],"rb");expf=fopen(argv[3],"rb");nf=fopen(argv[4],"rb");
    if(!obs || !expf || !nf)return -110;
    if(expected(expf,0,ctx.core.workspace.query.point) ||
       memcmp(ctx.core.workspace.query.point,ch_public_mean,128))return -111;
    for(i=0;i<prefix;i++) {
        if(fread(bytes,1,32,obs)!=32 || hp_decode_record(bytes,&o) || hp_encode(i,&o,&raw,&error))return -112;
        if(re_offer(&ctx,id,i,&raw) || re_admit(&ctx))return -113;
        if(ctx.inputs.block_count==16) {
            if(expected(expf,i+1,ctx.core.bank.estimate))return -114;
            status=re_commit(&ctx);if(status){fprintf(stderr,"commit at %" PRIu64 " status %d\n",i+1,status);return status;}
        }
    }
    if(fgetc(expf)!=EOF || sh_save(argv[5],&ctx))return -115;
    for(k=0;k<nodes;k++) {
        if(fread(ctx.core.workspace.query.point,8,16,nf)!=16)return -116;
        status=re_query(&ctx,0,0);
        if(!status && (ctx.core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID))status=-117;
        printf("{\"kind\":\"node\",\"index\":%u,\"status\":%d,\"x\":",k,status);vector(ctx.core.workspace.query.point,16);
        if(!status) {
            printf(",\"cost\":%.17g,\"absolute_scale\":%.17g,\"SOC\":%.17g,\"h\":%.17g,\"v\":",
                   ctx.core.result.evidence.likelihood_cost,ctx.core.result.evidence.cost_absolute_scale,
                   ctx.core.result.evidence.detail.endpoint.SOC,ctx.core.result.evidence.detail.endpoint.h);
            vector(ctx.core.result.evidence.detail.endpoint.v,3);
        }
        printf("}\n");if(fflush(stdout) || ferror(stdout))return -118;
    }
    if(fgetc(nf)!=EOF)return -119;
    fclose(obs);fclose(expf);fclose(nf);
    printf("{\"kind\":\"terminal\",\"prefix\":%" PRIu64 ",\"model_steps\":%" PRIu64 ",\"qr_rows\":%" PRIu64
           ",\"query_evaluations\":%" PRIu64 ",\"prior_evaluations\":%" PRIu64 ",\"nodes\":%u,"
           "\"optimizer_calls\":0,\"truth_reads\":0,\"reference_steps\":0,\"context_bytes\":%zu,\"analytic_attenuation\":%d}\n",
           prefix,ctx.core.bank.model_steps,ctx.core.bank.qr_rows,ctx.core.bank.query_evaluations,
           ctx.core.bank.prior_evaluations,nodes,sizeof(ctx),SH_ANALYTIC_ATTENUATION);
    return 0;
}
int main(int argc,char **argv)
{
    int status=run(argc,argv);if(status)fprintf(stderr,"structured harness stopped %d\n",status);
    return status || fflush(stdout) || ferror(stdout)?1:0;
}
#endif
