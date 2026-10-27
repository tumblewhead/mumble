/* Host-only causal-error attribution. No estimator changes or optimization.
 * Including the frozen engine exposes its exact QR append implementation. */
#include "../live_anchor_integration_001/rolling_engine.c"
#include "../live_anchor_integration_001/host_input.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

enum { MAX_CHECKS=8, MAX_NODES=545, MAX_SELECTED=9 };
typedef struct {
    char magic[8];uint64_t bank_bytes,input_bytes,calibration_bytes;
    ch_bank bank;lab_input_store inputs;adc12_calibration calibration;
} snapshot;
typedef struct { re_sum cost,gradient[16]; } aggregate;
static re_context saved,oracle;
static ch_jet rolling,exact[MAX_CHECKS];
static double points[MAX_NODES][16],anchor[16],origin[16],check_x[MAX_CHECKS][16];
static uint64_t checkpoints[MAX_CHECKS];
static uint32_t selected[MAX_SELECTED];
static aggregate windows[MAX_CHECKS][2],blocks[MAX_CHECKS][3];
static re_sum direct_cost[MAX_SELECTED];
static uint64_t merge_steps,reference_steps,qr_count;
static double max_origin_residual_gap,max_origin_derivative_gap;

static int read_bytes(FILE *f,void *p,size_t n) { return fread(p,1,n,f)==n?0:-201; }
static int expected(FILE *f,uint64_t index,double *x)
{
    uint64_t found;
    if(fseek(f,(long)((index/16)*236),SEEK_SET) || read_bytes(f,&found,8) || found!=index ||
       read_bytes(f,x,128))return -202;
    return 0;
}
static int load_snapshot(const char *path)
{
    snapshot s;FILE *f=fopen(path,"rb");int status;
    if(!f)return -203;
    status=read_bytes(f,&s,sizeof(s)) || fgetc(f)!=EOF;fclose(f);
    if(status || memcmp(s.magic,"FPSH001",8) || s.bank_bytes!=sizeof(s.bank) ||
       s.input_bytes!=sizeof(s.inputs) || s.calibration_bytes!=sizeof(s.calibration) ||
       s.inputs.block_count || s.inputs.ingress_count || !s.bank.available ||
       s.inputs.next_ingress_sequence!=s.bank.next_index ||
       (s.inputs.phase_and_flags&RE_PHASE_MASK)!=RE_PHASE_READY ||
       memcmp(&s.calibration,&hp_fixture_calibration,sizeof(s.calibration)))return -204;
    saved.core.bank=s.bank;saved.inputs=s.inputs;saved.calibration=s.calibration;
    memcpy(anchor,s.bank.estimate,sizeof(anchor));return 0;
}
static int poly(const double *row,const double *o,const double *x,double *r,double *g)
{
    double d[16];re_sum sum={0,0};unsigned i,a,b;
    for(i=0;i<16;i++) {d[i]=(x[i]-o[i])/ch_public_sd[i];if(g)g[i]=row[20+i];}
    if(add(&sum,row[36]))return -205;
    for(i=0;i<16;i++)if(add(&sum,row[20+i]*d[i]))return -205;
    for(i=0;i<20;i++) {
        a=ch_pair[i][0];b=ch_pair[i][1];
        if(add(&sum,row[i]*d[a]*d[b]))return -205;
        if(g){g[a]+=row[i]*d[b];g[b]+=row[i]*d[a];}
    }
    *r=total(&sum);
    if(g)for(i=0;i<16;i++)g[i]/=ch_public_sd[i];
    return isfinite(*r)?0:-205;
}
static int accumulate(aggregate *a,double r,const double *g)
{
    unsigned j;if(add(&a->cost,.5*r*r))return -206;
    for(j=0;j<16;j++)if(add(&a->gradient[j],r*g[j]))return -206;
    return 0;
}
static void vector_out(const double *v,unsigned n)
{
    unsigned i;putchar('[');for(i=0;i<n;i++)printf("%s%.17g",i?",":"",v[i]);putchar(']');
}
static void aggregate_out(const aggregate *a)
{
    unsigned j;printf("{\"cost\":%.17g,\"gradient\":[",total(&a->cost));
    for(j=0;j<16;j++)printf("%s%.17g",j?",":"",total(&a->gradient[j]));
    printf("]}");
}
static int execute(int argc,char **argv)
{
    FILE *obs,*expf,*f;uint64_t prefix,i;unsigned nc,nn,ns,j,k,w=0;int status;
    scm_model_state ref;scm_model_row ref_row;
    double theta[7],alpha[9],jac[7],rref,gref[16],rpoly,gpoly[16],row[37],exactrow[37],mu;
    hp_observation observation;hp_quantization_error error;
    adc12_raw_sample raw;adc12_reading decoded;scm_sample sample;
    unsigned char bytes[32];
    if(argc!=11)return -200;
    prefix=strtoull(argv[5],NULL,10);nc=(unsigned)strtoul(argv[7],NULL,10);
    nn=(unsigned)strtoul(argv[8],NULL,10);ns=(unsigned)strtoul(argv[10],NULL,10);
    if(!prefix || prefix>252000 || prefix%16 || !nc || nc>MAX_CHECKS ||
       !nn || nn>MAX_NODES || !ns || ns>MAX_SELECTED)return -200;
    status=load_snapshot(argv[3]);if(status)return status;
    if(saved.core.bank.next_index!=prefix)return -207;
    f=fopen(argv[4],"rb");if(!f)return -208;
    status=read_bytes(f,points,nn*128) || fgetc(f)!=EOF;fclose(f);if(status)return -208;
    if(memcmp(points[0],anchor,128))return -209;
    f=fopen(argv[6],"rb");if(!f)return -210;
    status=read_bytes(f,checkpoints,nc*8) || fgetc(f)!=EOF;fclose(f);if(status)return -210;
    f=fopen(argv[9],"rb");if(!f)return -211;
    status=read_bytes(f,selected,ns*4) || fgetc(f)!=EOF;fclose(f);if(status)return -211;
    for(j=0;j<ns;j++)if(selected[j]>=nn)return -211;
    obs=fopen(argv[1],"rb");expf=fopen(argv[2],"rb");if(!obs || !expf)return -212;
    for(j=0;j<nc;j++) {
        if(!checkpoints[j] || checkpoints[j]>prefix || checkpoints[j]%16 ||
           (j && checkpoints[j]<=checkpoints[j-1]))return -213;
        if(expected(expf,checkpoints[j],check_x[j]) || rm_init_jet(&exact[j],check_x[j]))return -214;
    }
    if(checkpoints[nc-1]!=prefix || memcmp(check_x[nc-1],anchor,128))return -213;
    if(expected(expf,0,origin) || rm_init_jet(&rolling,origin))return -215;
    if(re_init(&oracle,saved.core.bank.source_id,&hp_fixture_calibration))return -215;
    memcpy(oracle.core.bank.origin,anchor,128);memcpy(oracle.core.bank.estimate,anchor,128);
    for(j=0;j<5;j++)theta[j]=anchor[j];
    theta[5]=anchor[11];theta[6]=anchor[5];
    for(j=0;j<5;j++)alpha[j]=anchor[6+j];
    for(j=0;j<3;j++)alpha[5+j]=anchor[12+j];
    alpha[8]=anchor[10]*anchor[15];
    if(scm_model_init(&ref,3,theta))return -216;
    for(i=0;i<prefix;i++) {
        if(i%16==0) {
            double next[16];
            if(expected(expf,i+16,next) || rm_transport(&rolling,origin,next,&rolling))return -217;
            memcpy(origin,next,128);
        }
        if(read_bytes(obs,bytes,32) || hp_decode_record(bytes,&observation) ||
           hp_encode(i,&observation,&raw,&error) || adc12_convert(&raw,&hp_fixture_calibration,&decoded))return -218;
        sample.dt=decoded.dt_s;sample.current=decoded.current_A;sample.voltage=decoded.voltage_V;
        merge_steps++;if(rm_merge_step(&rolling,origin,&sample,RE_SIGMA_V,row))return -219;
        if(poly(row,origin,anchor,&rpoly,gpoly))return -220;
        reference_steps++;
        if(scm_model_step(&ref,NULL,decoded.dt_s,decoded.current_A,&ref_row) ||
           scm_model_predict(&ref_row,3,alpha,&mu,jac))return -221;
        rref=(mu-decoded.voltage_V)/RE_SIGMA_V;
        for(j=0;j<5;j++)gref[j]=jac[j];
        gref[5]=jac[6];gref[11]=jac[5];
        gref[6]=ref_row.X[0];for(j=0;j<3;j++){gref[7+j]=ref_row.X[1+j];gref[12+j]=ref_row.X[5+j];}
        gref[10]=ref_row.X[4]+ref_row.X[8]*anchor[15];gref[15]=ref_row.X[8]*anchor[10];
        for(j=0;j<16;j++)gref[j]/=RE_SIGMA_V;
        while(i>=checkpoints[w])w++;
        if(accumulate(&windows[w][0],rpoly,gpoly) || accumulate(&windows[w][1],rref,gref))return -222;
        for(j=0;j<ns;j++) {
            double r;if(poly(row,origin,points[selected[j]],&r,NULL) || add(&direct_cost[j],.5*r*r))return -223;
        }
        for(k=0;k<nc;k++)if(i<checkpoints[k]) {
            double r,g[16];
            merge_steps++;if(rm_merge_step(&exact[k],check_x[k],&sample,RE_SIGMA_V,exactrow))return -224;
            if(i+16>=checkpoints[k]) {
                if(poly(exactrow,check_x[k],anchor,&r,g))return -226;
                if(accumulate(&blocks[k][0],rpoly,gpoly) || accumulate(&blocks[k][1],r,g) ||
                   accumulate(&blocks[k][2],rref,gref))return -227;
            }
            if(k==nc-1) {
                if(poly(exactrow,check_x[k],anchor,&r,g))return -226;
                max_origin_residual_gap=fmax(max_origin_residual_gap,fabs(r-rref));
                for(j=0;j<16;j++)max_origin_derivative_gap=fmax(max_origin_derivative_gap,fabs(g[j]-gref[j]));
                qr_count++;if(qr_append(&oracle.core.bank,exactrow))return -225;
            }
        }
        oracle.core.bank.charge_min_Ah=fmin(oracle.core.bank.charge_min_Ah,ref.charge_Ah);
        oracle.core.bank.charge_max_Ah=fmax(oracle.core.bank.charge_max_Ah,ref.charge_Ah);
    }
    fclose(obs);fclose(expf);
    oracle.core.bank.jet=exact[nc-1];oracle.core.bank.next_index=prefix;
    oracle.inputs.next_ingress_sequence=prefix;
    memcpy(saved.core.workspace.query.point,anchor,128);if(re_query(&saved,1,0))return -228;
    printf("{\"kind\":\"saved_anchor\",\"cost\":%.17g,\"gradient\":",saved.core.result.evidence.likelihood_cost);
    vector_out(saved.core.workspace.query.gradient,16);printf("}\n");
    for(j=0;j<ns;j++)printf("{\"kind\":\"direct_row_sum\",\"index\":%u,\"cost\":%.17g}\n",selected[j],total(&direct_cost[j]));
    for(j=0;j<nc;j++) {
        printf("{\"kind\":\"window\",\"begin\":%" PRIu64 ",\"end\":%" PRIu64 ",\"rolling_rows\":",j?checkpoints[j-1]:0,checkpoints[j]);
        aggregate_out(&windows[j][0]);printf(",\"original_recurrence\":");aggregate_out(&windows[j][1]);printf("}\n");
        printf("{\"kind\":\"block_decomposition\",\"begin\":%" PRIu64 ",\"end\":%" PRIu64 ",\"rolling_rows\":",checkpoints[j]-16,checkpoints[j]);
        aggregate_out(&blocks[j][0]);printf(",\"exact_origin_rows\":");aggregate_out(&blocks[j][1]);
        printf(",\"original_recurrence\":");aggregate_out(&blocks[j][2]);printf("}\n");
    }
    for(j=0;j<nn;j++) {
        memcpy(oracle.core.workspace.query.point,points[j],128);
        status=re_query(&oracle,0,0);
        printf("{\"kind\":\"oracle_node\",\"index\":%u,\"status\":%d",j,status);
        if(!status)printf(",\"cost\":%.17g,\"cost_absolute_scale\":%.17g",oracle.core.result.evidence.likelihood_cost,
                         oracle.core.result.evidence.cost_absolute_scale);
        printf("}\n");
    }
    printf("{\"kind\":\"terminal\",\"prefix\":%" PRIu64 ",\"merge_steps\":%" PRIu64
           ",\"reference_steps\":%" PRIu64 ",\"qr_rows\":%" PRIu64 ",\"oracle_queries\":%u,"
           "\"optimizer_calls\":0,\"truth_reads\":0,\"candidate_updates\":0,"
           "\"max_origin_residual_gap\":%.17g,\"max_origin_derivative_gap\":%.17g}\n",
           prefix,merge_steps,reference_steps,qr_count,nn,max_origin_residual_gap,max_origin_derivative_gap);
    return 0;
}
int main(int argc,char **argv)
{
    int status=execute(argc,argv);
    if(status)fprintf(stderr,"localization stopped: %d\n",status);
    return status || fflush(stdout) || ferror(stdout)?1:0;
}
