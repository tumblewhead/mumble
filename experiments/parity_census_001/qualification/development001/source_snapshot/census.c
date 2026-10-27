/* Diagnostic adaptation: finite output differences are recorded, never gates.
 * Reuse the frozen backend's codec, record layout and checkpoint primitives.
 * No changes to that backend or to the inherited estimator implementation. */
#define FP_NO_MAIN
#include "../fixed_prefix_shape_001/backend.c"

static uint64_t mismatch_snapshots, floating_mismatches, integer_mismatches;

static int observe(FILE *out,const fp_expected *expected)
{
    fp_expected actual;unsigned k;int different=0,status;
    memcpy(ctx.core.workspace.query.point,ctx.core.bank.estimate,16*sizeof(double));
    status=re_query(&ctx,0,1);if(status)return status;
    actual.index=ctx.core.bank.next_index;values(&ctx,actual.values);
    actual.flags=ctx.core.result.evidence.flags;actual.phase=ctx.inputs.phase_and_flags;
    actual.available=ctx.core.bank.available;
    for(k=0;k<27;k++) {
        if(!isfinite(actual.values[k]))return -201;
        if(memcmp(actual.values+k,expected->values+k,8)) {
            floating_mismatches++;different=1;
        }
    }
    if(actual.index!=expected->index)return -202; /* chronology is structural */
    if(actual.flags!=expected->flags){integer_mismatches++;different=1;}
    if(actual.phase!=expected->phase){integer_mismatches++;different=1;}
    if(actual.available!=expected->available){integer_mismatches++;different=1;}
    if(different)mismatch_snapshots++;
    if(fwrite(&actual.index,8,1,out)!=1 || fwrite(actual.values,8,27,out)!=27 ||
       fwrite(&actual.flags,4,1,out)!=1 || fwrite(&actual.phase,4,1,out)!=1 ||
       fwrite(&actual.available,4,1,out)!=1)return -203;
    checked++;
    return 0;
}
static int expected_record(FILE *f,fp_expected *e,uint64_t index)
{
    unsigned k;
    if(read_expected(f,e) || e->index!=index)return -204;
    for(k=0;k<27;k++)if(!isfinite(e->values[k]))return -205;
    return 0;
}
int main(int argc,char **argv)
{
    FILE *obs=NULL,*expf=NULL,*actual=NULL,*bank=NULL;
    fp_expected expected;fp_checkpoint snapshot;uint64_t prefix,i=0;char *end;
    unsigned char id[32];uint16_t endian=1;int status=-206;
    adc12_raw_sample raw={0,{0,0,0}};adc12_reading decoded;
    (void)capture;(void)evaluate; /* Included frozen functions are not invoked. */
    if(argc!=7 || *(unsigned char *)&endian!=1)return 2;
    prefix=strtoull(argv[6],&end,10);
    if(*end || prefix>252000 || prefix%16 || source_id(argv[5],id))return 2;
    obs=fopen(argv[1],"rb");expf=fopen(argv[2],"rb");actual=fopen(argv[3],"wbx");
    if(!obs || !expf || !actual)goto done;
    status=re_init(&ctx,id,&hp_fixture_calibration);if(status)goto done;
    status=expected_record(expf,&expected,0);if(status)goto done;
    status=observe(actual,&expected);if(status)goto done;
    for(i=0;i<prefix;i++) {
        status=record(obs,i,&raw,&decoded);if(status)goto done;
        status=re_offer(&ctx,id,i,&raw);if(status)goto done;
        status=re_admit(&ctx);if(status)goto done;
        if(ctx.inputs.block_count==16) {
            status=expected_record(expf,&expected,i+1);if(status)goto done;
            memcpy(ctx.core.bank.estimate,expected.values,16*sizeof(double));
            status=re_commit(&ctx);if(status)goto done;
            status=observe(actual,&expected);if(status)goto done;
            if(checked%1000==0) {
                printf("{\"kind\":\"progress\",\"snapshots\":%" PRIu64 ",\"mismatch_snapshots\":%" PRIu64 "}\n",checked,mismatch_snapshots);
                if(fflush(stdout) || ferror(stdout)){status=-207;goto done;}
            }
        }
    }
    if(fgetc(expf)!=EOF || ferror(expf)){status=-208;goto done;}
    if(ctx.core.bank.model_steps!=2*prefix || ctx.core.bank.qr_rows!=prefix ||
       ctx.core.bank.query_evaluations!=2*(prefix/16)+1 ||
       ctx.core.bank.prior_evaluations!=prefix/16+1 ||
       ctx.core.bank.proposal_rounds || ctx.core.bank.accepted_steps ||
       checked!=prefix/16+1){status=-209;goto done;}
    checkpoint_pack(&snapshot,&ctx);memcpy(snapshot.magic,"FPSHC01",8);
    bank=fopen(argv[4],"wbx");if(!bank){status=-210;goto done;}
    if(fwrite(&snapshot,1,sizeof(snapshot),bank)!=sizeof(snapshot)){status=-211;goto done;}
done:
    if(obs && fclose(obs) && !status)status=-212;
    if(expf && fclose(expf) && !status)status=-213;
    if(actual && fclose(actual) && !status)status=-214;
    if(bank && fclose(bank) && !status)status=-215;
    printf("{\"kind\":\"terminal\",\"status\":\"%s\",\"code\":%d,\"snapshots\":%" PRIu64
           ",\"mismatch_snapshots\":%" PRIu64 ",\"floating_mismatches\":%" PRIu64
           ",\"integer_mismatches\":%" PRIu64 ",\"committed_records\":%" PRIu64
           ",\"model_steps\":%" PRIu64 ",\"qr_rows\":%" PRIu64 ",\"queries\":%" PRIu64
           ",\"prior_evaluations\":%" PRIu64 ",\"optimizer_calls\":0,\"truth_reads\":0,\"reference_passes\":0}\n",
           status?"structural_failure":"completed",status,checked,mismatch_snapshots,floating_mismatches,
           integer_mismatches,ctx.core.bank.next_index,ctx.core.bank.model_steps,ctx.core.bank.qr_rows,
           ctx.core.bank.query_evaluations,ctx.core.bank.prior_evaluations);
    if(status)fprintf(stderr,"Census stopped on structural failure %d after %" PRIu64 " snapshots\n",status,checked);
    return status || fflush(stdout) || ferror(stdout)?1:0;
}
