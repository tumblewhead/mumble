/* Fabricated online/reconstruction qualification only. Not canonical inference. */
#define FP_NO_MAIN
#include "backend.c"

static int same_bank(const re_context *a,const re_context *b)
{
    ch_bank x=a->core.bank,y=b->core.bank;
    x.model_steps=y.model_steps=0;x.query_evaluations=y.query_evaluations=0;
    x.prior_evaluations=y.prior_evaluations=0;x.proposal_rounds=y.proposal_rounds=0;
    x.accepted_steps=y.accepted_steps=0;
    return !memcmp(&x,&y,sizeof(x)) && !memcmp(&a->inputs,&b->inputs,sizeof(a->inputs)) &&
        !memcmp(&a->calibration,&b->calibration,sizeof(a->calibration));
}
static int write_expected(FILE *f,re_context *c)
{
    double v[27];ch_result *r=&c->core.result.evidence;
    memcpy(c->core.workspace.query.point,c->core.bank.estimate,16*sizeof(double));
    if(re_query(c,0,1))return -1;
    values(c,v);
    return fwrite(&c->core.bank.next_index,8,1,f)!=1 || fwrite(v,8,27,f)!=27 ||
        fwrite(&r->flags,4,1,f)!=1 || fwrite(&c->inputs.phase_and_flags,4,1,f)!=1 ||
        fwrite(&c->core.bank.available,4,1,f)!=1;
}
int main(int argc,char **argv)
{
    re_context online,replay,loaded;unsigned char id[32]={1};
    char obs_path[4096],expected_path[4096],snapshot_path[4096],nodes_path[4096];
    FILE *obs,*expected,*nodes;unsigned mode,i,j,assertions=0;uint64_t accepted=0;
    const char *id_text="0100000000000000000000000000000000000000000000000000000000000000";
    if(argc!=2)return 2;
    for(mode=0;mode<4;mode++) {
        snprintf(obs_path,sizeof(obs_path),"%s/case%u.observations.bin",argv[1],mode);
        snprintf(expected_path,sizeof(expected_path),"%s/case%u.expected.bin",argv[1],mode);
        snprintf(snapshot_path,sizeof(snapshot_path),"%s/case%u.bank.bin",argv[1],mode);
        snprintf(nodes_path,sizeof(nodes_path),"%s/case%u.nodes.bin",argv[1],mode);
        obs=fopen(obs_path,"wbx");expected=fopen(expected_path,"wbx");nodes=fopen(nodes_path,"wbx");
        if(!obs || !expected || !nodes)return 3;
        if(re_init(&online,id,&hp_fixture_calibration) || re_init(&replay,id,&hp_fixture_calibration))return 4;
        if(write_expected(expected,&online))return 5;
        for(i=0;i<96;i++) {
            uint64_t index=i;double data[3];hp_observation observation;
            adc12_raw_sample raw={0,{0,0,0}};adc12_reading decoded;hp_quantization_error error;
            data[0]=mode==0?0.:(mode==1?1./35.:(i%9==0?0.:.01*(i%7+1)));
            data[1]=mode==0?0.:(mode==3?.2:(i%13<6?.09:-.07));
            data[2]=3.78+.003*(i%11)-.05*data[1];
            if(fwrite(&index,8,1,obs)!=1 || fwrite(data,8,3,obs)!=3)return 6;
            observation.index=index;observation.dt_s=data[0];observation.current_A=data[1];observation.voltage_V=data[2];
            if(hp_encode(index,&observation,&raw,&error) || adc12_convert(&raw,&hp_fixture_calibration,&decoded))return 7;
            if(re_offer(&online,id,index,&raw) || re_admit(&online) || re_offer(&replay,id,index,&raw) || re_admit(&replay))return 8;
            if(i%16==15) {
                if(re_process(&online,1))return 9;
                memcpy(replay.core.bank.estimate,online.core.bank.estimate,16*sizeof(double));
                if(re_commit(&replay) || !same_bank(&online,&replay))return 10;
                assertions++;
                if(write_expected(expected,&online))return 11;
                memcpy(replay.core.workspace.query.point,replay.core.bank.estimate,16*sizeof(double));
                if(re_query(&replay,0,1))return 12;
                {
                    double a[27],b[27];values(&online,a);values(&replay,b);
                    if(memcmp(a,b,sizeof(a)) || online.core.result.evidence.flags!=replay.core.result.evidence.flags)return 13;
                    assertions+=28;
                }
            }
        }
        accepted+=online.core.bank.accepted_steps;
        for(i=0;i<5;i++) {
            double x[16];memcpy(x,online.core.bank.estimate,sizeof(x));
            if(i)x[i==1||i==2?5:11]+=(i%2?1.:-1.)*.0001;
            if(fwrite(x,8,16,nodes)!=16)return 14;
        }
        if(fclose(obs) || fclose(expected) || fclose(nodes))return 15;
        checked=0;
        if(capture(obs_path,expected_path,snapshot_path,id_text,96))return 16;
        if(checkpoint_load(snapshot_path,&loaded) || !same_bank(&online,&loaded))return 17;
        assertions++;
        /* Dump the frozen polynomial for an independent Decimal evaluator. */
        printf("{\"kind\":\"polynomial_fixture\",\"case\":%u,\"origin\":",mode);vector(loaded.core.bank.origin,16);
        printf(",\"upper\":");vector(loaded.core.bank.upper,703);
        printf(",\"public_sd\":");vector(ch_public_sd,16);printf("}\n");
        if(evaluate(obs_path,snapshot_path,nodes_path,96,5))return 18;
        for(j=0;j<sizeof(loaded.auxiliary);j++)if(((unsigned char *)&loaded.auxiliary)[j])return 19;
        assertions++;
    }
    if(!accepted)return 20;
    printf("{\"kind\":\"qualification\",\"cases\":4,\"assertions\":%u,\"online_accepted_steps\":%" PRIu64
           ",\"canonical_observation_reads\":0,\"truth_reads\":0}\n",assertions,accepted);
    return fflush(stdout) || ferror(stdout)?1:0;
}
