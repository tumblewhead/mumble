#ifndef SCM_HYPOTHESIS_NO_HOST_IO
#define _POSIX_C_SOURCE 200809L
#endif
#include "scm_hypothesis_checkpoint.h"
#include <float.h>
#include <limits.h>
#include <math.h>
#include <string.h>
#ifndef SCM_HYPOTHESIS_NO_HOST_IO
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

#define HEADER_BYTES 32u
#define PAYLOAD_BYTES (SCM_HYPOTHESIS_CHECKPOINT_BYTES-HEADER_BYTES-4u)
#define MODEL_TAG UINT64_C(0x48595032504b3031) /* HYP2PK01 */
#if SCM_HYPOTHESIS_MODEL_VERSION != 1u
#error "Update hypothesis checkpoint identity for a new model version"
#endif
static const unsigned char magic[8]={'S','C','M','H','Y','P','0','1'};
typedef struct {
    scm_hypothesis_checkpoint_read_fn read;
    scm_hypothesis_checkpoint_write_fn write;
    void *context;
    size_t count;
    uint32_t crc;
    int reading,error;
} codec;

static int binary64_supported(void)
{
    double one=1.;uint64_t bits=0;
    if(CHAR_BIT!=8||sizeof(double)!=8||DBL_MANT_DIG!=53||DBL_MAX_EXP!=1024||sizeof(int)<4)return 0;
    memcpy(&bits,&one,8);return bits==UINT64_C(0x3ff0000000000000);
}
static uint32_t crc_bytes(uint32_t crc,const unsigned char *p,size_t n)
{
    size_t i;int k;
    for(i=0;i<n;i++){crc^=p[i];for(k=0;k<8;k++)crc=(crc>>1)^((crc&1u)?UINT32_C(0xedb88320):0u);}
    return crc;
}
static void bytes(codec *c,void *data,size_t n)
{
    size_t done;
    if(c->error)return;
    if(n>SCM_HYPOTHESIS_CHECKPOINT_BYTES-4u-c->count){c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;return;}
    done=c->reading?c->read(c->context,data,n):c->write(c->context,data,n);
    if(done!=n){c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;return;}
    c->crc=crc_bytes(c->crc,data,n);c->count+=n;
}
static void u32(codec *c,uint32_t *value)
{
    unsigned char b[4];unsigned i;
    if(c->error)return;
    if(!c->reading)for(i=0;i<4;i++)b[i]=(unsigned char)(*value>>(8*i));
    bytes(c,b,4);if(c->error)return;
    if(c->reading){*value=0;for(i=0;i<4;i++)*value|=(uint32_t)b[i]<<(8*i);}
}
static void u64(codec *c,uint64_t *value)
{
    unsigned char b[8];unsigned i;
    if(c->error)return;
    if(!c->reading)for(i=0;i<8;i++)b[i]=(unsigned char)(*value>>(8*i));
    bytes(c,b,8);if(c->error)return;
    if(c->reading){*value=0;for(i=0;i<8;i++)*value|=(uint64_t)b[i]<<(8*i);}
}
static void integer(codec *c,int *value)
{
    uint32_t v=c->reading?0:(uint32_t)*value;
    if(!c->reading&&*value<0){c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;return;}
    u32(c,&v);if(c->error||!c->reading)return;
    if(v>INT_MAX){c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;return;}*value=(int)v;
}
static void natural(codec *c,unsigned *value)
{
    uint32_t v=c->reading?0:(uint32_t)*value;
#if UINT_MAX > UINT32_MAX
    if(!c->reading&&*value>UINT32_MAX){c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;return;}
#endif
    u32(c,&v);if(c->reading&&!c->error)*value=(unsigned)v;
}
static void real(codec *c,double *value)
{
    uint64_t bits=0;double v;
    if(c->error)return;
    if(!c->reading){if(!isfinite(*value)){c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;return;}memcpy(&bits,value,8);}
    u64(c,&bits);if(c->error||!c->reading)return;
    memcpy(&v,&bits,8);if(!isfinite(v)){c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;return;}*value=v;
}
static void real_array(codec *c,double *values,size_t n)
{size_t i;for(i=0;i<n&&!c->error;i++)real(c,&values[i]);}
static void header(codec *c)
{
    unsigned char signature[8];uint32_t version=SCM_HYPOTHESIS_CHECKPOINT_VERSION,numeric=1;
    uint64_t model=MODEL_TAG,length=PAYLOAD_BYTES;
    if(!c->reading)memcpy(signature,magic,8);
    bytes(c,signature,8);u32(c,&version);u32(c,&numeric);u64(c,&model);u64(c,&length);
    if(c->error)return;
    if(memcmp(signature,magic,8)||version!=SCM_HYPOTHESIS_CHECKPOINT_VERSION||numeric!=1||model!=MODEL_TAG)
        c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE;
    else if(length!=PAYLOAD_BYTES)c->error=SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;
}
/* Shared field order. Cast-away-const pointers are written only on decode. */
static void component_payload(codec *c,scm_hypothesis_component *s)
{
    bytes(c,s->config.source_id,SCM_ONLINE_SOURCE_BYTES);
    real(c,&s->config.sigma_V);real(c,&s->config.max_dt_s);real(c,&s->config.max_abs_current_A);
    real_array(c,s->mean,SCM_HYPOTHESIS_DIM);real_array(c,s->factor,SCM_HYPOTHESIS_FACTOR_ENTRIES);
#define U(field) u64(c,&s->field)
    U(epoch_begin);U(next_index);U(evidence_next_index);U(prediction_count);U(voltage_count);
    U(missing_voltage_count);U(rejected_voltage_count);U(limited_gain_count);U(zero_gain_count);U(cold_resets);
#undef U
#define R(field) real(c,&s->field)
    R(elapsed_s);R(epoch_elapsed_s);R(last_current_A);R(last_prediction_V);R(last_innovation_V);
    R(last_innovation_variance_V2);R(last_gain_scale);R(minimum_gain_scale);R(last_max_gain_scale);R(innovation_ewma);
#undef R
    natural(c,&s->last_limited_mask);natural(c,&s->last_blocked_mask);
    natural(c,&s->flags);natural(c,&s->excitation);
    integer(c,&s->initialized);integer(c,&s->has_voltage);integer(c,&s->prediction_valid);
}
static void payload(codec *c,scm_hypothesis *s)
{
    unsigned i;
    for(i=0;i<SCM_HYPOTHESIS_COMPONENTS;i++)component_payload(c,&s->component[i]);
    real_array(c,s->log_weight,SCM_HYPOTHESIS_COMPONENTS);
    u64(c,&s->header.generation);u64(c,&s->header.bank_evidence_next_index);
    u32(c,&s->header.flags);u32(c,&s->header.active_components);
    u32(c,&s->header.last_rejection_stage);u32(c,&s->header.last_rejection_component);
}
static int checksum(codec *c)
{
    unsigned char b[4];uint32_t stored=0;unsigned i;
    if(c->reading) {
        if(c->read(c->context,b,4)!=4)return SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;
        for(i=0;i<4;i++)stored|=(uint32_t)b[i]<<(8*i);
        if(stored!=~c->crc)return SCM_HYPOTHESIS_CHECKPOINT_ERR_INTEGRITY;
    } else {
        stored=~c->crc;for(i=0;i<4;i++)b[i]=(unsigned char)(stored>>(8*i));
        if(c->write(c->context,b,4)!=4)return SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;
    }
    c->count+=4;return 0;
}
int scm_hypothesis_checkpoint_encode(const scm_hypothesis *s,
    scm_hypothesis_checkpoint_write_fn write,void *context)
{
    codec c;int rc;
    if(!s||!write)return SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT;
    if(!binary64_supported())return SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE;
    if(scm_hypothesis_validate(s))return SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;
    c=(codec){NULL,write,context,0,UINT32_MAX,0,0};header(&c);payload(&c,(scm_hypothesis*)s);
    if(c.error)return c.error;
    if(c.count!=SCM_HYPOTHESIS_CHECKPOINT_BYTES-4)return SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;
    rc=checksum(&c);if(rc)return rc;
    return c.count==SCM_HYPOTHESIS_CHECKPOINT_BYTES?0:SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;
}
static int decode_stage(const scm_hypothesis_config *expected,
    scm_hypothesis_checkpoint_read_fn read,void *context,size_t record_bytes,scm_hypothesis_workspace *work)
{
    codec c;int rc;unsigned i;
    if(!expected||!read||!work||!scm_hypothesis_config_valid(expected))return SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT;
    if(!binary64_supported())return SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE;
    if(record_bytes<HEADER_BYTES)return SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;
    c=(codec){read,NULL,context,0,UINT32_MAX,1,0};header(&c);if(c.error)return c.error;
    if(record_bytes!=SCM_HYPOTHESIS_CHECKPOINT_BYTES)return SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;
    memset(&work->staged,0,sizeof(work->staged));payload(&c,&work->staged);
    if(c.error)return c.error;
    if(c.count!=SCM_HYPOTHESIS_CHECKPOINT_BYTES-4)return SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;
    rc=checksum(&c);if(rc)return rc;
    for(i=0;i<SCM_HYPOTHESIS_COMPONENTS;i++)
        if(!scm_hypothesis_config_equal(&work->staged.component[i].config,expected))return SCM_HYPOTHESIS_CHECKPOINT_ERR_INCOMPATIBLE;
    if(scm_hypothesis_validate(&work->staged))return SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;
    return 0;
}
int scm_hypothesis_checkpoint_decode(scm_hypothesis *s,const scm_hypothesis_config *expected,
    scm_hypothesis_checkpoint_read_fn read,void *context,size_t record_bytes,scm_hypothesis_workspace *work)
{
    int rc;if(!s)return SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT;
    rc=decode_stage(expected,read,context,record_bytes,work);if(rc)return rc;
    *s=work->staged;return 0;
}

#ifndef SCM_HYPOTHESIS_NO_HOST_IO
static size_t file_read(void *context,void *data,size_t n)
{return fread(data,1,n,(FILE*)context);}
static size_t file_write(void *context,const void *data,size_t n)
{return fwrite(data,1,n,(FILE*)context);}
int scm_hypothesis_checkpoint_save(const scm_hypothesis *s,const char *path,
    unsigned char buffer[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES])
{
    char temporary[SCM_HYPOTHESIS_CHECKPOINT_PATH_CAPACITY+12];size_t n;
    FILE *f=NULL;int fd=-1,rc=SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;
    if(!s||!path||!buffer||!*path)return SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT;
    n=strlen(path);if(n>=SCM_HYPOTHESIS_CHECKPOINT_PATH_CAPACITY)return SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT;
    if(scm_hypothesis_validate(s))return SCM_HYPOTHESIS_CHECKPOINT_ERR_STATE;
    memcpy(temporary,path,n);memcpy(temporary+n,".tmp.XXXXXX",12);
    fd=mkstemp(temporary);if(fd<0)return SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;
    f=fdopen(fd,"wb");if(!f)goto done;fd=-1;
    if(setvbuf(f,(char*)buffer,_IOFBF,SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES))goto done;
    rc=scm_hypothesis_checkpoint_encode(s,file_write,f);if(rc)goto done;
    rc=SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;if(fflush(f)||fsync(fileno(f)))goto done;
    if(fclose(f)){f=NULL;goto done;}f=NULL;
    if(rename(temporary,path))goto done;
    rc=0;
done:
    if(f)fclose(f);
    if(fd>=0)close(fd);
    if(rc)unlink(temporary);
    return rc;
}
int scm_hypothesis_checkpoint_restore(scm_hypothesis *s,const scm_hypothesis_config *expected,
    const char *path,scm_hypothesis_workspace *work,
    unsigned char buffer[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES])
{
    FILE *f;struct stat st;int rc=SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;
    if(!s||!expected||!path||!work||!buffer||!*path||!scm_hypothesis_config_valid(expected))return SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT;
    if(strlen(path)>=SCM_HYPOTHESIS_CHECKPOINT_PATH_CAPACITY)return SCM_HYPOTHESIS_CHECKPOINT_ERR_ARGUMENT;
    f=fopen(path,"rb");if(!f)return SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;
    if(setvbuf(f,(char*)buffer,_IOFBF,SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES))goto done;
    if(fstat(fileno(f),&st)||!S_ISREG(st.st_mode)||st.st_size<0)goto done;
    if((uintmax_t)st.st_size>(uintmax_t)SIZE_MAX){rc=SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;goto done;}
    rc=decode_stage(expected,file_read,f,(size_t)st.st_size,work);if(rc)goto done;
    if(fgetc(f)!=EOF||ferror(f)){rc=SCM_HYPOTHESIS_CHECKPOINT_ERR_FORMAT;goto done;}
    if(fclose(f)){f=NULL;rc=SCM_HYPOTHESIS_CHECKPOINT_ERR_IO;goto done;}f=NULL;
    *s=work->staged;rc=0;
done:
    if(f)fclose(f);
    return rc;
}
#endif
