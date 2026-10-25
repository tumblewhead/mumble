#define _POSIX_C_SOURCE 200809L
#include "scm_online_checkpoint.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Constructed fixed-state fixture, no observation updates or optimizations.
 * The committed primary separately demonstrates fresh-process continuation. */
static int checks,failures;
static scm_online original,destination,before;
static scm_online_workspace work;
static unsigned char canonical[SCM_ONLINE_CHECKPOINT_BYTES],mutated[SCM_ONLINE_CHECKPOINT_BYTES+1];
#define CHECK(x,label) do{checks++;if(!(x)){fprintf(stderr,"FAIL %s at%d\n",label,__LINE__);failures++;}}while(0)
#define REQUIRE(x,label) do{int ok=!!(x);CHECK(ok,label);if(!ok)exit(2);}while(0)

static void write_bytes(const char *path,const unsigned char *data,size_t n)
{
    FILE *f=fopen(path,"wb");REQUIRE(f!=NULL,"open fixture");
    REQUIRE(fwrite(data,1,n,f)==n,"write fixture");REQUIRE(fclose(f)==0,"close fixture");
}
static void read_bytes(const char *path,unsigned char *data)
{
    FILE *f=fopen(path,"rb");REQUIRE(f!=NULL,"open checkpoint");
    REQUIRE(fread(data,1,SCM_ONLINE_CHECKPOINT_BYTES,f)==SCM_ONLINE_CHECKPOINT_BYTES,"fixed checkpoint length");
    REQUIRE(fgetc(f)==EOF&&!ferror(f),"no trailing bytes");REQUIRE(fclose(f)==0,"close checkpoint");
}
static void rejected(const char *path,const scm_online_config *expected,int code)
{
    before=destination;
    CHECK(scm_online_checkpoint_restore(&destination,expected,path,&work)==code,"fault rejected explicitly");
    CHECK(!memcmp(&before,&destination,sizeof(before)),"rejected restore preserves live state byte-for-byte");
}
static void put_u32(unsigned char *p,uint32_t value)
{unsigned k;for(k=0;k<4;k++)p[k]=(unsigned char)(value>>(8*k));}
static void seal(unsigned char *p,size_t n)
{
    size_t i;int k;uint32_t crc=UINT32_MAX;
    for(i=0;i<n-4;i++){crc^=p[i];for(k=0;k<8;k++)crc=(crc>>1)^((crc&1u)?UINT32_C(0xedb88320):0u);}
    put_u32(p+n-4,~crc);
}
int main(void)
{
    scm_online_config config,wrong;char directory[]="/tmp/mumble_online_checkpoint_XXXXXX";
    char path[256],roundtrip[256],fault[256];size_t i;
    REQUIRE(mkdtemp(directory)!=NULL,"temporary directory");
    REQUIRE(snprintf(path,sizeof(path),"%s/base.bin",directory)>0,"base path");
    REQUIRE(snprintf(roundtrip,sizeof(roundtrip),"%s/roundtrip.bin",directory)>0,"roundtrip path");
    REQUIRE(snprintf(fault,sizeof(fault),"%s/fault.bin",directory)>0,"fault path");
    scm_online_config_default(&config);
    for(i=0;i<SCM_ONLINE_SOURCE_BYTES;i++)config.source_id[i]=(unsigned char)(i+31);
    REQUIRE(scm_online_init(&original,&config)==0,"initialize public fixture");
    original.mean[SCM_ONLINE_Z]+=.001;original.factor[SCM_ONLINE_DIM]=.002;
    /* Construct a nonempty ledger and nondefault diagnostics directly; no
     * observations are ingested to create this persistence-only fixture. */
    original.next_index=original.evidence_next_index=original.prediction_count=original.voltage_count=1;
    original.elapsed_s=original.epoch_elapsed_s=.1;original.has_voltage=original.prediction_valid=1;
    original.last_prediction_V=3.8;original.last_innovation_variance_V2=1e-6;
    original.last_gain_scale=original.minimum_gain_scale=0;original.last_max_gain_scale=.75;
    original.last_limited_mask=(1u<<SCM_ONLINE_R0)|(1u<<SCM_ONLINE_LOG_Q);
    original.last_blocked_mask=1u<<SCM_ONLINE_R0;
    original.limited_gain_count=1;original.flags=SCM_ONLINE_FLAG_GAIN_LIMITED;
    REQUIRE(scm_online_validate(&original)==0,"constructed finite correlated fixture");
    before=original;
    REQUIRE(scm_online_checkpoint_save(&original,path,&work)==0,"save complete state");
    CHECK(!memcmp(&before,&original,sizeof(original)),"save does not mutate inference state");
    read_bytes(path,canonical);
    CHECK(canonical[7]=='2'&&canonical[8]==2,"canonical version 2 identity");
    original.mean[SCM_ONLINE_Z]=-1;
    CHECK(scm_online_checkpoint_save(&original,path,&work)==SCM_ONLINE_CHECKPOINT_ERR_STATE,"invalid save rejected before replacing file");
    read_bytes(path,mutated);CHECK(!memcmp(canonical,mutated,SCM_ONLINE_CHECKPOINT_BYTES),"rejected save preserves prior checkpoint bytes");
    original=before;
    REQUIRE(scm_online_checkpoint_restore(&destination,&config,path,&work)==0,"restore fresh destination");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"full mean and square factor restored exactly");
    CHECK(destination.last_max_gain_scale==.75&&destination.last_limited_mask==original.last_limited_mask&&
        destination.last_blocked_mask==original.last_blocked_mask,"version 2 gain diagnostics restored exactly");
    REQUIRE(scm_online_checkpoint_save(&destination,roundtrip,&work)==0,"save restored state");
    read_bytes(roundtrip,mutated);CHECK(!memcmp(canonical,mutated,SCM_ONLINE_CHECKPOINT_BYTES),"canonical bytes exact");
    destination.mean[SCM_ONLINE_Z]-=.01;
    REQUIRE(scm_online_validate(&destination)==0,"different valid destination");
    REQUIRE(scm_online_checkpoint_restore(&destination,&config,path,&work)==0,"restore over nonempty state");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"replacement exact without second allocated state");

    memcpy(mutated,canonical,sizeof(canonical));mutated[100]^=1;
    write_bytes(fault,mutated,sizeof(canonical));rejected(fault,&config,SCM_ONLINE_CHECKPOINT_ERR_INTEGRITY);
    write_bytes(fault,canonical,sizeof(canonical)-1);rejected(fault,&config,SCM_ONLINE_CHECKPOINT_ERR_FORMAT);
    memcpy(mutated,canonical,sizeof(canonical));mutated[sizeof(canonical)]=0;
    write_bytes(fault,mutated,sizeof(mutated));rejected(fault,&config,SCM_ONLINE_CHECKPOINT_ERR_FORMAT);
    memcpy(mutated,canonical,sizeof(canonical));mutated[8]=3;
    write_bytes(fault,mutated,sizeof(canonical));rejected(fault,&config,SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE);
    /* A complete v1 record: remove v2 max-scale/masks, restore the original
     * header/model/2404-byte payload identity and recompute its CRC. */
    memcpy(mutated,canonical,2408);memcpy(mutated+2408,canonical+2416,8);
    memcpy(mutated+2416,canonical+2432,20);
    mutated[7]='1';put_u32(mutated+8,1);mutated[16]='1';put_u32(mutated+24,2404);put_u32(mutated+28,0);
    seal(mutated,2440);write_bytes(fault,mutated,2440);
    rejected(fault,&config,SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE);
    /* Valid v2 CRC with factor[0,1]=1: reject representation semantics,
     * rather than accepting a predecessor-style general square factor. */
    memcpy(mutated,canonical,sizeof(canonical));memset(mutated+224,0,8);mutated[230]=0xf0;mutated[231]=0x3f;
    seal(mutated,sizeof(canonical));write_bytes(fault,mutated,sizeof(canonical));
    rejected(fault,&config,SCM_ONLINE_CHECKPOINT_ERR_STATE);
    wrong=config;wrong.source_id[0]^=1;rejected(path,&wrong,SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE);
    wrong=config;wrong.sigma_V*=2;rejected(path,&wrong,SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE);

    CHECK(scm_online_mark_unknown_gap(&original)==SCM_ONLINE_ERR_RECOVERY_REQUIRED,"gap latch fixture");
    REQUIRE(scm_online_checkpoint_save(&original,path,&work)==0,"save unavailable state");
    REQUIRE(scm_online_checkpoint_restore(&destination,&config,path,&work)==0,"restore unavailable state");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"recovery flag and retained belief exact");
    REQUIRE(scm_online_cold_reset(&original)==0,"cold reset fixture");
    REQUIRE(scm_online_checkpoint_save(&original,path,&work)==0,"save public cold prior");
    REQUIRE(scm_online_checkpoint_restore(&destination,&config,path,&work)==0,"restore public cold prior");
    CHECK(!memcmp(&original,&destination,sizeof(original)),"cold reset state exact");
    before=original;
    CHECK(scm_online_checkpoint_save(&original,"",&work)==SCM_ONLINE_CHECKPOINT_ERR_ARGUMENT,"bad save path rejected");
    CHECK(!memcmp(&before,&original,sizeof(original)),"bad save preserves live state");
    REQUIRE(unlink(path)==0&&unlink(roundtrip)==0&&unlink(fault)==0&&rmdir(directory)==0,"remove test files");
    printf("{\"test\":\"online_checkpoint\",\"checks\":%d,\"failures\":%d,\"checkpoint_bytes\":%u,\"observation_updates\":0,\"optimizer_calls\":0}\n",checks,failures,SCM_ONLINE_CHECKPOINT_BYTES);
    return failures?1:0;
}
