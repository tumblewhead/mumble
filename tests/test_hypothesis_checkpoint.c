#define _POSIX_C_SOURCE 200809L
#include "scm_hypothesis_checkpoint.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Small deterministic persistence/continuation fixtures only. Record arrays
 * and duplicated banks below are test-oracle storage, not estimator SRAM. */
static int checks,failures;
static scm_hypothesis original,destination,before,fresh;
static scm_hypothesis_workspace work;
static unsigned char canonical[SCM_HYPOTHESIS_CHECKPOINT_BYTES];
static unsigned char mutated[SCM_HYPOTHESIS_CHECKPOINT_BYTES+1];
static unsigned char host_buffer[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES];
#define CHECK(x,label) do{checks++;if(!(x)){fprintf(stderr,"FAIL %s at%d\n",label,__LINE__);failures++;}}while(0)
#define REQUIRE(x,label) do{int ok=!!(x);CHECK(ok,label);if(!ok)exit(2);}while(0)
typedef struct {unsigned char *data;size_t size,position,fail_after;} memory_stream;
static size_t memory_read(void *context,void *data,size_t n)
{
    memory_stream *m=context;size_t available=m->size-m->position;
    if(m->position>=m->fail_after)return 0;
    if(available>m->fail_after-m->position)available=m->fail_after-m->position;
    if(n>available)n=available;
    memcpy(data,m->data+m->position,n);m->position+=n;return n;
}
static size_t memory_write(void *context,const void *data,size_t n)
{
    memory_stream *m=context;size_t available=m->size-m->position;
    if(m->position>=m->fail_after)return 0;
    if(available>m->fail_after-m->position)available=m->fail_after-m->position;
    if(n>available)n=available;
    memcpy(m->data+m->position,data,n);m->position+=n;return n;
}
static void encode(unsigned char *data,const scm_hypothesis *state)
{
    memory_stream m={data,SCM_HYPOTHESIS_CHECKPOINT_BYTES,0,SIZE_MAX};
    REQUIRE(scm_hypothesis_checkpoint_encode(state,memory_write,&m)==0,"encode valid complete bank");
    CHECK(m.position==SCM_HYPOTHESIS_CHECKPOINT_BYTES,"canonical fixed3004-byte record");
}
static int decode(scm_hypothesis *state,const scm_hypothesis_config *config,
    unsigned char *data,size_t actual_size,size_t claimed_size,size_t fail_after)
{
    memory_stream m={data,actual_size,0,fail_after};
    return scm_hypothesis_checkpoint_decode(state,config,memory_read,&m,claimed_size,&work);
}
static void rejected(const scm_hypothesis_config *config,size_t actual_size,size_t claimed_size,
    size_t fail_after,int expected_code)
{
    before=destination;
    CHECK(decode(&destination,config,mutated,actual_size,claimed_size,fail_after)==expected_code,"fault has explicit status");
    CHECK(!memcmp(&before,&destination,sizeof(before)),"failed decode preserves live bank bytes");
}
static void put_u32(unsigned char *p,uint32_t value)
{unsigned k;for(k=0;k<4;k++)p[k]=(unsigned char)(value>>(8*k));}
static void put_real(unsigned char *p,double value)
{uint64_t bits;unsigned k;memcpy(&bits,&value,8);for(k=0;k<8;k++)p[k]=(unsigned char)(bits>>(8*k));}
static void seal(unsigned char *p)
{
    size_t i;int k;uint32_t crc=UINT32_MAX;
    for(i=0;i<SCM_HYPOTHESIS_CHECKPOINT_BYTES-4;i++){
        crc^=p[i];for(k=0;k<8;k++)crc=(crc>>1)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    put_u32(p+SCM_HYPOTHESIS_CHECKPOINT_BYTES-4,~crc);
}
static void write_file(const char *path,const unsigned char *data,size_t n)
{
    FILE *f=fopen(path,"wb");REQUIRE(f!=NULL,"open fixture file");
    REQUIRE(fwrite(data,1,n,f)==n,"write fixture file");REQUIRE(fclose(f)==0,"close fixture file");
}
static void read_file(const char *path,unsigned char *data)
{
    FILE *f=fopen(path,"rb");REQUIRE(f!=NULL,"open saved record");
    REQUIRE(fread(data,1,SCM_HYPOTHESIS_CHECKPOINT_BYTES,f)==SCM_HYPOTHESIS_CHECKPOINT_BYTES,"host record length");
    CHECK(fgetc(f)==EOF&&!ferror(f),"host record has no suffix");REQUIRE(fclose(f)==0,"close saved record");
}
static void fixture(const scm_hypothesis_config *config)
{
    unsigned i;
    REQUIRE(scm_hypothesis_init(&original,config,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT)==0,"initialize public split fixture");
    for(i=0;i<SCM_HYPOTHESIS_COMPONENTS;i++){
        scm_hypothesis_component *s=&original.component[i];
        s->next_index=s->prediction_count=s->voltage_count=1;
        s->elapsed_s=s->epoch_elapsed_s=.1;s->last_current_A=.001;s->excitation=1;
        s->prediction_valid=1;s->last_prediction_V=3.8;s->last_innovation_variance_V2=1e-6;
        s->factor[SCM_HYPOTHESIS_FACTOR_INDEX(1,0)]=.002;
    }
    original.component[0].has_voltage=1;original.component[0].evidence_next_index=1;
    original.component[0].mean[SCM_ONLINE_Z]+=.001;
    original.component[0].last_gain_scale=original.component[0].minimum_gain_scale=0;
    original.component[0].last_max_gain_scale=.75;
    original.component[0].last_limited_mask=(1u<<SCM_ONLINE_R0)|(1u<<SCM_ONLINE_LOG_Q);
    original.component[0].last_blocked_mask=1u<<SCM_ONLINE_R0;
    original.component[0].limited_gain_count=1;original.component[0].flags=SCM_ONLINE_FLAG_GAIN_LIMITED;
    original.component[1].zero_gain_count=1;
    original.header.generation=1;original.header.bank_evidence_next_index=1;
    original.header.flags|=SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE;
    original.log_weight[0]=log(.25);original.log_weight[1]=log(.75);
    REQUIRE(scm_hypothesis_validate(&original)==0,"fixture has distinct valid conditional cursors and weights");
}
int main(void)
{
    scm_hypothesis_config config,wrong;memory_stream stream;
    char directory[]="/tmp/mumble_hypothesis_checkpoint_XXXXXX";
    char path[256],fault[256];unsigned j;int i;
    scm_hypothesis_config_default(&config);
    for(j=0;j<SCM_ONLINE_SOURCE_BYTES;j++)config.source_id[j]=(unsigned char)(j+31);
    fixture(&config);before=original;encode(canonical,&original);
    CHECK(!memcmp(&before,&original,sizeof(original)),"encode never mutates inference state");
    CHECK(!memcmp(canonical,"SCMHYP01",8)&&canonical[8]==1,"distinct bank format identity");
    REQUIRE(decode(&destination,&config,canonical,sizeof(canonical),sizeof(canonical),SIZE_MAX)==0,"restore fresh bank");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"all fields and canonical padding restore exactly");
    CHECK(destination.component[0].evidence_next_index==1&&destination.component[1].evidence_next_index==0&&
        destination.header.bank_evidence_next_index==1,"distinct evidence cursors are preserved");
    encode(mutated,&destination);CHECK(!memcmp(canonical,mutated,sizeof(canonical)),"re-encoded bytes are exact");

    memcpy(mutated,canonical,sizeof(canonical));mutated[100]^=1;
    rejected(&config,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_INTEGRITY);
    memcpy(mutated,canonical,sizeof(canonical));
    rejected(&config,sizeof(canonical)-1,sizeof(canonical)-1,SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT);
    rejected(&config,sizeof(mutated),sizeof(mutated),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT);
    rejected(&config,sizeof(canonical),sizeof(canonical),123,SCM_HYPOTHESIS_CHECKPOINT_ERR_IO);
    rejected(&config,sizeof(canonical),sizeof(canonical),sizeof(canonical)-1,SCM_HYPOTHESIS_CHECKPOINT_ERR_IO);
    rejected(&config,sizeof(canonical),10,SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT);
    memcpy(mutated,canonical,sizeof(canonical));mutated[8]=2;
    rejected(&config,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE);
    memcpy(mutated,canonical,sizeof(canonical));memcpy(mutated,"SCMONLN2",8);
    rejected(&config,2456,2456,SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE);
    memcpy(mutated,canonical,sizeof(canonical));put_real(mutated+216,-1.);seal(mutated);
    rejected(&config,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE);
    memcpy(mutated,canonical,sizeof(canonical));put_real(mutated+2952,NAN);seal(mutated);
    rejected(&config,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE);
    memcpy(mutated,canonical,sizeof(canonical));put_u32(mutated+2988,3);seal(mutated);
    rejected(&config,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE);
    memcpy(mutated,canonical,sizeof(canonical));put_real(mutated+2952,0.);seal(mutated);
    rejected(&config,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE);
    memcpy(mutated,canonical,sizeof(canonical));wrong=config;wrong.source_id[0]^=1;
    rejected(&wrong,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE);
    wrong=config;wrong.sigma_V*=2;
    rejected(&wrong,sizeof(canonical),sizeof(canonical),SIZE_MAX,SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE);
    stream=(memory_stream){mutated,sizeof(mutated),0,123};before=original;
    CHECK(scm_hypothesis_checkpoint_encode(&original,memory_write,&stream)==SCM_HYPOTHESIS_CHECKPOINT_ERR_IO,"short write is explicit");
    CHECK(!memcmp(&before,&original,sizeof(original)),"short write preserves live bank");
    CHECK(scm_hypothesis_checkpoint_encode(NULL,memory_write,&stream)==SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT,"null encode argument");
    CHECK(scm_hypothesis_checkpoint_decode(NULL,&config,memory_read,&stream,sizeof(canonical),&work)==SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT,"null decode destination");

    before=original;original.log_weight[0]=-0.;original.log_weight[1]=-1000.;
    REQUIRE(scm_hypothesis_validate(&original)==0,"finite log weight survives linear underflow");
    encode(mutated,&original);
    REQUIRE(decode(&destination,&config,mutated,sizeof(canonical),sizeof(canonical),SIZE_MAX)==0,"underflowed display weight restores");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"both hypotheses and finite log weights persist through display underflow");
    original=before;destination=original;

    REQUIRE(mkdtemp(directory)!=NULL,"temporary host directory");
    REQUIRE(snprintf(path,sizeof(path),"%s/base.bin",directory)>0,"host base path");
    REQUIRE(snprintf(fault,sizeof(fault),"%s/fault.bin",directory)>0,"host fault path");
    REQUIRE(scm_hypothesis_checkpoint_save(&original,path,host_buffer)==0,"host save");
    read_file(path,mutated);CHECK(!memcmp(canonical,mutated,sizeof(canonical)),"host and callback encoders agree");
    before=original;original.component[0].mean[SCM_ONLINE_Z]=-1.;
    CHECK(scm_hypothesis_checkpoint_save(&original,path,host_buffer)==SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE,"invalid host save rejected before replacement");
    read_file(path,mutated);CHECK(!memcmp(canonical,mutated,sizeof(canonical)),"invalid save preserves existing record");original=before;
    memset(&destination,0xa5,sizeof(destination));
    REQUIRE(scm_hypothesis_checkpoint_restore(&destination,&config,path,&work,host_buffer)==0,"host restore over arbitrary destination");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"host restore exact");
    memcpy(mutated,canonical,sizeof(canonical));mutated[100]^=1;write_file(fault,mutated,sizeof(canonical));before=destination;
    CHECK(scm_hypothesis_checkpoint_restore(&destination,&config,fault,&work,host_buffer)==SCM_HYPOTHESIS_CHECKPOINT_ERR_INTEGRITY,"host corrupt record rejected");
    CHECK(!memcmp(&before,&destination,sizeof(before)),"host failure is byte-atomic");
    CHECK(unlink(path)==0&&unlink(fault)==0&&rmdir(directory)==0,"remove owned host fixture files");

    for(i=0;i<32;i++){
        scm_sample sample={.01+(i%3)*.001,(i<16?.002:-.001),3.75+.00001*i};
        uint64_t index=original.component[0].next_index;
        REQUIRE(scm_hypothesis_ingest(&original,config.source_id,index,&sample,1,&work)==0,"uninterrupted tiny stream accepted");
        REQUIRE(scm_hypothesis_ingest(&destination,config.source_id,index,&sample,1,&work)==0,"restored tiny stream accepted");
        CHECK(!memcmp(&original,&destination,sizeof(original)),"continued bank is byte-exact after each input");
        if(i==15){encode(canonical,&original);memset(&destination,0x5a,sizeof(destination));
            REQUIRE(decode(&destination,&config,canonical,sizeof(canonical),sizeof(canonical),SIZE_MAX)==0,"midstream fresh destination restore");}
    }
    before=original;
    REQUIRE(scm_hypothesis_cold_reset(&original)==0,"explicit cold reset");
    REQUIRE(scm_hypothesis_init(&fresh,&config,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT)==0,"fresh public comparison");
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++){
        CHECK(original.component[j].next_index==before.component[j].next_index&&original.component[j].prediction_count==before.component[j].prediction_count,"cold reset retains physical source ledger");
        CHECK(original.component[j].epoch_begin==before.component[j].next_index&&original.component[j].evidence_next_index==original.component[j].epoch_begin&&!original.component[j].has_voltage,"cold reset clears conditional evidence explicitly");
        CHECK(original.component[j].cold_resets==before.component[j].cold_resets+1&&original.component[j].flags&SCM_ONLINE_FLAG_HISTORY_LOST,"cold reset records lost belief");
        CHECK(!memcmp(original.component[j].mean,fresh.component[j].mean,sizeof(fresh.component[j].mean))&&
              !memcmp(original.component[j].factor,fresh.component[j].factor,sizeof(fresh.component[j].factor)),"cold reset recreates public split without truth");
    }
    CHECK(original.header.flags&SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT,"cold reset retains initialization mode");
    CHECK(!(original.header.flags&SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE)&&original.header.bank_evidence_next_index==original.component[0].next_index,"cold reset clears bank evidence at new epoch");
    CHECK(!memcmp(original.log_weight,fresh.log_weight,sizeof(fresh.log_weight)),"cold reset gives public equal weights");
    encode(canonical,&original);
    REQUIRE(decode(&destination,&config,canonical,sizeof(canonical),sizeof(canonical),SIZE_MAX)==0,"cold checkpoint restores");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"cold checkpoint roundtrip exact");
    printf("{\"schema\":\"mumble_hypothesis_checkpoint_tests_v1\",\"checks\":%d,\"failed_checks\":%d,\"checkpoint_bytes\":%u,\"tiny_stream_input_deliveries\":64,\"cell_trace_deliveries\":0}\n",checks,failures,SCM_HYPOTHESIS_CHECKPOINT_BYTES);
    return failures?1:0;
}
