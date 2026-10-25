#define _POSIX_C_SOURCE 200809L
#include "scm_session_checkpoint.h"
#include <dirent.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Persistence tests use a constructed fit-result fixture, not an optimized
 * estimate or a truth oracle. No optimizer is called here. The primary M1
 * trajectory runner separately checks fresh-process continuation of real fits.
 */
static int checks,failures,rejections;
#define CHECK(c,m) do{checks++;if(!(c)){fprintf(stderr,"FAIL %s (line %d)\n",m,__LINE__);failures++;}}while(0)
#define REQUIRE(c,m) do{int required_ok=!!(c);CHECK(required_ok,m);if(!required_ok)exit(2);}while(0)

static unsigned char *read_file(const char *path,size_t *size)
{
    FILE *f=fopen(path,"rb");long n;unsigned char *data;
    REQUIRE(f!=NULL,"open checkpoint for independent read");
    REQUIRE(fseek(f,0,SEEK_END)==0,"seek checkpoint");n=ftell(f);
    REQUIRE(n>0,"nonempty checkpoint");REQUIRE(fseek(f,0,SEEK_SET)==0,"rewind checkpoint");
    data=malloc((size_t)n);REQUIRE(data!=NULL,"test buffer allocation");
    REQUIRE(fread(data,1,(size_t)n,f)==(size_t)n,"read checkpoint bytes");
    REQUIRE(fclose(f)==0,"close checkpoint read");*size=(size_t)n;return data;
}

static void write_file(const char *path,const unsigned char *data,size_t size)
{
    FILE *f=fopen(path,"wb");REQUIRE(f!=NULL,"open fault fixture");
    REQUIRE(fwrite(data,1,size,f)==size,"write fault fixture");
    REQUIRE(fclose(f)==0,"close fault fixture");
}

static void put_u64(unsigned char *p,uint64_t value)
{
    unsigned i;for(i=0;i<8;i++)p[i]=(unsigned char)(value>>(8*i));
}

static void put_double(unsigned char *p,double value)
{
    uint64_t bits;memcpy(&bits,&value,sizeof(bits));put_u64(p,bits);
}

static void refresh_crc(unsigned char *data,size_t size)
{
    uint32_t crc=UINT32_MAX;size_t i;int j;
    for(i=0;i<size-4;i++) {
        crc^=data[i];
        for(j=0;j<8;j++)crc=(crc>>1)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    crc=~crc;for(i=0;i<4;i++)data[size-4+i]=(unsigned char)(crc>>(8*i));
}

static void same_file(const char *a,const char *b)
{
    size_t na,nb;unsigned char *aa=read_file(a,&na),*bb=read_file(b,&nb);
    CHECK(na==nb,"canonical checkpoint lengths match");
    CHECK(na==nb && !memcmp(aa,bb,na),"canonical checkpoint bytes match");
    free(aa);free(bb);
}

static void configure(scm_session_config *config)
{
    unsigned i;scm_session_config_default(config);
    for(i=0;i<SCM_SESSION_SOURCE_BYTES;i++)config->source_id[i]=(unsigned char)(73+3*i);
    config->starts=1;config->max_iterations=2;config->max_history_samples=96;
    memset(config->fit_checkpoints,0,sizeof(config->fit_checkpoints));
    config->schedule_count=2;config->fit_checkpoints[0]=24;config->fit_checkpoints[1]=48;
}

static void ingest_to(scm_session *s,uint64_t end)
{
    while(s->next_index<end) {
        uint64_t k=s->next_index;
        scm_sample sample={k%7?1./35.:.037,k%11<6?.04:-.025,3.75+.0001*(double)(k%5)};
        REQUIRE(scm_session_ingest(s,s->config.source_id,k,&sample,1)==0,"ingest ordered fixture");
    }
}

static void constructed_fit_fixture(scm_session *s)
{
    scm_fit_result *f=&s->fit;int i;
    REQUIRE(scm_session_fit_due(s),"fixture at first scheduled fit");
    memset(f,0,sizeof(*f));scm_default_theta(s->config.modes,0,f->theta);
    for(i=0;i<4;i++)f->alpha[i]=.12;
    f->alpha[4]=.02;f->alpha[5]=.004;f->alpha[6]=-.003;f->alpha[7]=.002;f->alpha[8]=.01;
    for(i=0;i<SCM_MAX_PARAMETERS;i++) {
        f->coordinate_scales[i]=.1+(double)i*.01;
        f->joint_normal[i*SCM_MAX_PARAMETERS+i]=1.+i;
    }
    f->joint_normal[1]=f->joint_normal[SCM_MAX_PARAMETERS]=.125;
    f->objective=1.25;f->objective_full=1.25;f->voltage_rmse=.001;
    f->elapsed_cpu_s=12.5;f->basis_seconds=7.25;
    f->projected_gradient=.5;f->max_inner_kkt=1e-9;
    f->status=1;f->termination_reason=1;f->iterations=2;f->evaluations=5;f->starts=1;
    f->samples=s->count;f->features=16;f->data_bytes=s->count*sizeof(scm_sample);
    f->workspace_bytes=8192;f->retained_bytes=f->data_bytes+8192;
    f->setup_peak_bytes=f->retained_bytes;f->unexcited_theta_mask=1u<<3;
    f->elapsed_physical_s=s->epoch_elapsed_s;f->charge_Ah=s->epoch_charge_Ah;
    s->has_fit=1;s->fit_attempts=s->fit_results=1;
    s->last_fit_next_index=s->last_fit_attempt_index=s->next_index;s->schedule_cursor=1;
    s->last_problem_auxiliary_bytes=8192;s->peak_fit_owned_bytes=scm_session_owned_bytes(s)+8192;
    REQUIRE(scm_session_rebuild(s)==0,"constructed state satisfies lifecycle invariants");
}

static void compare_live(const scm_session *a,const scm_session *b)
{
    scm_session_query_result qa,qb;scm_fit_result fa=a->fit,fb=b->fit;
    CHECK(scm_session_query(a,&qa,NULL,NULL)==0 && scm_session_query(b,&qb,NULL,NULL)==0,"query restored states");
    CHECK(!memcmp(&qa,&qb,sizeof(qa)),"restored lifecycle/query values match exactly");
    CHECK(a->count==b->count && a->capacity==b->capacity,"journal count and capacity preserved");
    CHECK(a->count==b->count && (!a->count || !memcmp(a->samples,b->samples,a->count*sizeof(scm_sample))),"journal doubles preserved exactly");
    CHECK(a->count==b->count && (!a->count || !memcmp(a->voltage_present,b->voltage_present,a->count)),"voltage-presence flags preserved");
    CHECK(!memcmp(&a->model,&b->model,sizeof(a->model)),"carried model reconstructed exactly");
    fa.elapsed_cpu_s=fb.elapsed_cpu_s=fa.basis_seconds=fb.basis_seconds=0;
    CHECK(!memcmp(&fa,&fb,sizeof(fa)),"complete fit diagnostics and warm start preserved");
}

static void rejected_unchanged(scm_session *s,const scm_session_config *expected,
    const char *path,int error)
{
    scm_session before;scm_sample samples[96];unsigned char present[96];int rc;
    REQUIRE(s->count<=96,"bounded test fixture");memcpy(&before,s,sizeof(before));
    if(s->count){memcpy(samples,s->samples,s->count*sizeof(*samples));memcpy(present,s->voltage_present,s->count);}
    rc=scm_session_checkpoint_restore(s,expected,path);rejections++;
    CHECK(rc==error,"restore rejects fault with expected error");
    CHECK(!memcmp(&before,s,sizeof(before)),"rejected restore leaves live state byte-identical");
    CHECK(!s->count || !memcmp(samples,s->samples,s->count*sizeof(*samples)),"rejected restore preserves live journal");
    CHECK(!s->count || !memcmp(present,s->voltage_present,s->count),"rejected restore preserves missing-V flags");
}

static int directory_entries(const char *path)
{
    DIR *dir=opendir(path);struct dirent *entry;int count=0;
    REQUIRE(dir!=NULL,"inspect temporary output directory");
    while((entry=readdir(dir))!=NULL)if(strcmp(entry->d_name,".") && strcmp(entry->d_name,".."))count++;
    REQUIRE(closedir(dir)==0,"close directory inspection");return count;
}

int main(void)
{
    char directory[]="/tmp/scm-checkpoint-XXXXXX",base[256],roundtrip[256],fault[256],blocked[256];
    scm_session original={0},restored={0},edge={0};scm_session_config config,wrong;
    unsigned char *canonical,*mutated;size_t size,journal_start;int before_entries;
    uint64_t attempts,results;double known_clock;
    REQUIRE(mkdtemp(directory)!=NULL,"create isolated checkpoint test directory");
    REQUIRE(snprintf(base,sizeof(base),"%s/base.bin",directory)>0,"checkpoint path");
    REQUIRE(snprintf(roundtrip,sizeof(roundtrip),"%s/roundtrip.bin",directory)>0,"roundtrip path");
    REQUIRE(snprintf(fault,sizeof(fault),"%s/fault.bin",directory)>0,"fault path");
    REQUIRE(snprintf(blocked,sizeof(blocked),"%s/directory-target",directory)>0,"blocked publish path");
    configure(&config);REQUIRE(scm_session_init(&original,&config)==0,"initialize checkpoint source");
    ingest_to(&original,24);constructed_fit_fixture(&original);ingest_to(&original,27);
    REQUIRE(scm_session_checkpoint_save(&original,base)==0,"save complete fitted checkpoint");
    canonical=read_file(base,&size);CHECK(size==2808+25*original.count,"explicit format has complete byte accounting");
    journal_start=size-4-25*original.count;
    REQUIRE(scm_session_checkpoint_restore(&restored,&config,base)==0,"restore into fresh zeroed storage");
    CHECK(restored.fit.elapsed_cpu_s==0 && restored.fit.basis_seconds==0,"noncausal runtime timings canonicalized");
    compare_live(&original,&restored);
    CHECK(restored.samples!=original.samples && restored.voltage_present!=original.voltage_present,"checkpoint owns independent decoded journal");
    CHECK(restored.fit_attempts==1 && restored.fit_results==1,"restore does not refit or recount historical evidence");
    REQUIRE(scm_session_checkpoint_save(&restored,roundtrip)==0,"save restored checkpoint");same_file(base,roundtrip);

    /* A live destination is used throughout all fault tests. */
    mutated=malloc(size+1);REQUIRE(mutated!=NULL,"mutation buffer allocation");
    memcpy(mutated,canonical,size);mutated[journal_start+3]^=1;write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_INTEGRITY);
    write_file(fault,canonical,size-1);rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_FORMAT);
    write_file(fault,canonical,20);rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_IO);
    memcpy(mutated,canonical,size);mutated[size]=0;write_file(fault,mutated,size+1);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_FORMAT);
    memcpy(mutated,canonical,size);mutated[8]=2;refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    memcpy(mutated,canonical,size);mutated[12]=2;refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    memcpy(mutated,canonical,size);mutated[16]^=1;refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    wrong=config;wrong.source_id[0]^=1;
    rejected_unchanged(&restored,&wrong,base,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    wrong=config;wrong.sigma=.002;
    rejected_unchanged(&restored,&wrong,base,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    wrong=config;wrong.fit_checkpoints[1]=49;
    rejected_unchanged(&restored,&wrong,base,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    wrong=config;wrong.fit_checkpoints[SCM_SESSION_MAX_CHECKPOINTS-1]=99;
    rejected_unchanged(&restored,&wrong,base,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    memcpy(mutated,canonical,size);mutated[32]^=1;refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE);
    /* Header32 + explicit config128 precede count/capacity. Correct checksums
     * exercise length/count validation beyond accidental corruption detection. */
    memcpy(mutated,canonical,size);put_u64(mutated+160,UINT64_MAX);refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_LIMIT);
    memcpy(mutated,canonical,size);put_u64(mutated+168,UINT64_MAX);refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_LIMIT);
    memcpy(mutated,canonical,size);put_u64(mutated+160,96);refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_FORMAT);
    memcpy(mutated,canonical,size);put_u64(mutated+24,UINT64_MAX);refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_LIMIT);
    memcpy(mutated,canonical,size);put_double(mutated+journal_start+8,.125);refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_STATE);
    memcpy(mutated,canonical,size);put_double(mutated+journal_start,NAN);refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_STATE);
    memcpy(mutated,canonical,size);mutated[journal_start+24]=2;refresh_crc(mutated,size);write_file(fault,mutated,size);
    rejected_unchanged(&restored,&config,fault,SCM_SESSION_CHECKPOINT_ERR_STATE);

    /* A successful restore over nonempty live storage also transfers ownership
     * only after validating the replacement. Continuation must reach the next
     * scheduled fit without using CPU timing as input or replaying old fits. */
    REQUIRE(scm_session_checkpoint_restore(&restored,&config,base)==0,"replace live session transactionally");
    ingest_to(&original,48);ingest_to(&restored,48);compare_live(&original,&restored);
    CHECK(scm_session_fit_due(&original) && scm_session_fit_due(&restored),"next fit schedule preserved");
    REQUIRE(scm_session_checkpoint_save(&original,base)==0,"save uninterrupted continuation");
    REQUIRE(scm_session_checkpoint_save(&restored,roundtrip)==0,"save restored continuation");same_file(base,roundtrip);

    /* Rename failure occurs after temporary writing: the directory target
     * survives and no abandoned temporary file may remain. */
    REQUIRE(mkdir(blocked,0700)==0,"create failing publish target");before_entries=directory_entries(directory);
    CHECK(scm_session_checkpoint_save(&original,blocked)==SCM_SESSION_CHECKPOINT_ERR_IO,"failed atomic publish reported");
    CHECK(directory_entries(directory)==before_entries && directory_entries(blocked)==0,"failed save cleans unique temporary output");
    CHECK(scm_session_checkpoint_save(&original,"")==SCM_SESSION_CHECKPOINT_ERR_ARGUMENT,"invalid save rejected");
    {
        double prior_voltage=original.samples[0].voltage;
        original.samples[0].voltage=NAN;
        CHECK(scm_session_checkpoint_save(&original,base)==SCM_SESSION_CHECKPOINT_ERR_STATE,"invalid state save rejected before publication");
        original.samples[0].voltage=prior_voltage;
    }
    same_file(base,roundtrip);

    /* Missing voltage remains explicit while known time/current persist. */
    REQUIRE(scm_session_checkpoint_restore(&edge,&config,roundtrip)==0,"create independent edge-state session");
    REQUIRE(scm_session_cold_reset(&edge)==0,"cold reset before edge-state journal");
    REQUIRE(scm_session_advance(&edge,config.source_id,edge.next_index,.123,-.031)==0,"retain missing-voltage interval");
    CHECK(edge.samples[0].voltage==0 && !edge.voltage_present[0],"missing voltage stored canonically");
    REQUIRE(scm_session_checkpoint_save(&edge,base)==0,"save missing-voltage state");
    REQUIRE(scm_session_checkpoint_restore(&restored,&config,base)==0,"restore missing-voltage state");compare_live(&edge,&restored);
    CHECK(restored.flags&SCM_SESSION_FLAG_MISSING_VOLTAGE,"missing-voltage flag persists");
    CHECK(scm_session_mark_unknown_gap(&edge)==SCM_SESSION_ERR_RECOVERY_REQUIRED,"mark unknown gap");
    REQUIRE(scm_session_checkpoint_save(&edge,base)==0,"save recovery-required state");
    REQUIRE(scm_session_checkpoint_restore(&restored,&config,base)==0,"restore recovery-required state");compare_live(&edge,&restored);
    CHECK(scm_session_advance(&restored,config.source_id,restored.next_index,.1,.02)==SCM_SESSION_ERR_RECOVERY_REQUIRED,"restored gap blocks invented advancement");
    attempts=edge.fit_attempts;results=edge.fit_results;known_clock=edge.elapsed_total_s;
    REQUIRE(scm_session_cold_reset(&edge)==0,"explicit cold reset clears recovery");
    REQUIRE(scm_session_checkpoint_save(&edge,base)==0,"save empty cold-reset state");
    REQUIRE(scm_session_checkpoint_restore(&restored,&config,base)==0,"restore cold-reset state");compare_live(&edge,&restored);
    CHECK(restored.count==0 && restored.capacity==0 && restored.cold_resets==2 && !restored.has_fit,"cold reset has no hidden history or warm start");
    CHECK(restored.flags==SCM_SESSION_FLAG_HISTORY_LOST,"cold reset uncertainty/loss flag persists");
    CHECK(restored.elapsed_total_s==known_clock && restored.fit_attempts==attempts && restored.fit_results==results,"cold reset preserves known clock and cumulative counts");
    REQUIRE(scm_session_checkpoint_save(&restored,roundtrip)==0,"save restored cold state");same_file(base,roundtrip);

    free(mutated);free(canonical);scm_session_destroy(&original);scm_session_destroy(&restored);scm_session_destroy(&edge);
    CHECK(unlink(base)==0 && unlink(roundtrip)==0 && unlink(fault)==0 && rmdir(blocked)==0 && rmdir(directory)==0,"clean test-owned files");
    printf("{\"test\":\"scm_session_checkpoint\",\"checks\":%d,\"failures\":%d,\"rejected_faults\":%d,"
        "\"optimizer_calls\":0,\"checkpoint_fixed_bytes\":2808,\"journal_bytes_per_sample\":25,"
        "\"scope\":\"host persistence and continuation; constructed fit fixture, no estimation or coverage claim\"}\n",checks,failures,rejections);
    return failures?1:0;
}
