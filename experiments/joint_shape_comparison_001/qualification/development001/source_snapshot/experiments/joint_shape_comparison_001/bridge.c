/* Explicit host diagnostic adapter. Inherited reference arithmetic is unchanged.
 * Renaming main (rather than FP_NO_MAIN) keeps per-sample debug output disabled. */
#define main inherited_backend_main
#include "../fixed_prefix_shape_001/backend.c"
#undef main

static int metric(const char *snapshot)
{
    uint64_t steps, queries, priors;
    int status=checkpoint_load(snapshot,&ctx);
    if(status)return status;
    steps=ctx.core.bank.model_steps;queries=ctx.core.bank.query_evaluations;
    priors=ctx.core.bank.prior_evaluations;
    memcpy(ctx.core.workspace.query.point,ctx.core.bank.estimate,16*sizeof(double));
    status=re_query(&ctx,1,1);if(status)return status;
    if(ctx.core.result.evidence.flags&CH_FLAG_ENDPOINT_INVALID)return -140;
    printf("{\"kind\":\"metric\",\"prefix\":%" PRIu64 ",\"anchor\":",ctx.core.bank.next_index);
    vector(ctx.core.bank.estimate,16);
    printf(",\"metric_packed_lower\":");vector(ctx.core.workspace.query.packed,136);
    printf(",\"public_sd\":");vector(ch_public_sd,16);
    printf(",\"lower\":");vector(ch_lower,16);printf(",\"upper\":");vector(ch_upper,16);
    printf(",\"charge_min_Ah\":%.17g,\"charge_max_Ah\":%.17g,\"charge_Ah\":%.17g,"
           "\"model_steps\":%" PRIu64 ",\"query_evaluations\":%" PRIu64 ",\"prior_evaluations\":%" PRIu64
           ",\"optimizer_calls\":0,\"truth_reads\":0,\"compiler\":\"%s\",\"checkpoint_bytes\":%zu}\n",
           ctx.core.bank.charge_min_Ah,ctx.core.bank.charge_max_Ah,ctx.core.bank.jet.model.charge_Ah,
           ctx.core.bank.model_steps-steps,ctx.core.bank.query_evaluations-queries,
           ctx.core.bank.prior_evaluations-priors,__VERSION__,sizeof(fp_checkpoint));
    return 0;
}

int main(int argc,char **argv)
{
    uint16_t endian=1;int result;char *end;uint64_t prefix;unsigned long count;
    if(*(unsigned char *)&endian!=1)return 2;
    if(argc==3 && !strcmp(argv[1],"metric"))result=metric(argv[2]);
    else if(argc==7 && !strcmp(argv[1],"evaluate")) {
        count=strtoul(argv[5],&end,10);if(*end || !count || count>545)return 2;
        prefix=strtoull(argv[6],&end,10);if(*end || prefix>252000)return 2;
        result=evaluate(argv[2],argv[3],argv[4],prefix,(unsigned)count);
    } else return 2;
    if(result)fprintf(stderr,"Diagnostic bridge stopped: %d\n",result);
    return result || fflush(stdout) || ferror(stdout)?1:0;
}
