#define _POSIX_C_SOURCE 200809L
#include "scm_online_checkpoint.h"
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define HEADER_BYTES 32u
#define PAYLOAD_BYTES (SCM_ONLINE_CHECKPOINT_BYTES-HEADER_BYTES-4u)
#define MODEL_TAG UINT64_C(0x41345352454b4632) /* A4SREKF2 */
#if SCM_ONLINE_MODEL_VERSION != 2u
#error "Update the online checkpoint model tag for a new model version"
#endif
static const unsigned char magic[8]={'S','C','M','O','N','L','N','2'};
typedef struct {FILE *file;uint32_t crc;size_t count;int reading,error;} codec;

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
    if(n>SCM_ONLINE_CHECKPOINT_BYTES-c->count){c->error=SCM_ONLINE_CHECKPOINT_ERR_FORMAT;return;}
    done=c->reading?fread(data,1,n,c->file):fwrite(data,1,n,c->file);
    if(done!=n){c->error=SCM_ONLINE_CHECKPOINT_ERR_IO;return;}
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
    if(!c->reading&&*value<0){c->error=SCM_ONLINE_CHECKPOINT_ERR_STATE;return;}
    u32(c,&v);if(c->error||!c->reading)return;
    if(v>INT_MAX){c->error=SCM_ONLINE_CHECKPOINT_ERR_STATE;return;}
    *value=(int)v;
}
static void natural(codec *c,unsigned *value)
{
    uint32_t v=c->reading?0:(uint32_t)*value;
#if UINT_MAX > UINT32_MAX
    if(!c->reading&&*value>UINT32_MAX){c->error=SCM_ONLINE_CHECKPOINT_ERR_STATE;return;}
#endif
    u32(c,&v);if(c->reading&&!c->error)*value=(unsigned)v;
}
static void real(codec *c,double *value)
{
    uint64_t bits=0;double v;
    if(c->error)return;
    if(!c->reading){if(!isfinite(*value)){c->error=SCM_ONLINE_CHECKPOINT_ERR_STATE;return;}memcpy(&bits,value,8);}
    u64(c,&bits);if(c->error||!c->reading)return;
    memcpy(&v,&bits,8);if(!isfinite(v)){c->error=SCM_ONLINE_CHECKPOINT_ERR_STATE;return;}*value=v;
}
static void real_array(codec *c,double *values,size_t n)
{size_t i;for(i=0;i<n&&!c->error;i++)real(c,&values[i]);}

static void header(codec *c)
{
    unsigned char signature[8];uint32_t version=SCM_ONLINE_CHECKPOINT_VERSION,numeric=1;
    uint64_t model=MODEL_TAG,length=PAYLOAD_BYTES;
    if(!c->reading)memcpy(signature,magic,8);
    bytes(c,signature,8);u32(c,&version);u32(c,&numeric);u64(c,&model);u64(c,&length);
    if(c->error)return;
    if(memcmp(signature,magic,8)||version!=SCM_ONLINE_CHECKPOINT_VERSION||numeric!=1||model!=MODEL_TAG)
        c->error=SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE;
    else if(length!=PAYLOAD_BYTES)c->error=SCM_ONLINE_CHECKPOINT_ERR_FORMAT;
}
/* Shared field order. Writes through these pointers occur only while reading. */
static void payload(codec *c,scm_online *s)
{
    bytes(c,s->config.source_id,SCM_ONLINE_SOURCE_BYTES);
    real(c,&s->config.sigma_V);real(c,&s->config.max_dt_s);real(c,&s->config.max_abs_current_A);
    real_array(c,s->mean,SCM_ONLINE_DIM);real_array(c,s->factor,SCM_ONLINE_DIM*SCM_ONLINE_DIM);
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
static int checksum(FILE *f,uint32_t crc,int reading)
{
    unsigned char b[4];uint32_t stored=0;unsigned i;
    if(reading) {
        if(fread(b,1,4,f)!=4)return SCM_ONLINE_CHECKPOINT_ERR_IO;
        for(i=0;i<4;i++)stored|=(uint32_t)b[i]<<(8*i);
        if(stored!=~crc)return SCM_ONLINE_CHECKPOINT_ERR_INTEGRITY;
    } else {
        crc=~crc;for(i=0;i<4;i++)b[i]=(unsigned char)(crc>>(8*i));
        if(fwrite(b,1,4,f)!=4)return SCM_ONLINE_CHECKPOINT_ERR_IO;
    }
    return 0;
}
int scm_online_checkpoint_save(const scm_online *s,const char *path,scm_online_workspace *work)
{
    char temporary[SCM_ONLINE_CHECKPOINT_PATH_CAPACITY+12];size_t n;
    FILE *f=NULL;codec c;int fd=-1,rc=SCM_ONLINE_CHECKPOINT_ERR_IO;
    if(!s||!path||!work||!*path)return SCM_ONLINE_CHECKPOINT_ERR_ARGUMENT;
    n=strlen(path);if(n>=SCM_ONLINE_CHECKPOINT_PATH_CAPACITY)return SCM_ONLINE_CHECKPOINT_ERR_ARGUMENT;
    if(!binary64_supported())return SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE;
    if(scm_online_validate(s))return SCM_ONLINE_CHECKPOINT_ERR_STATE;
    memcpy(temporary,path,n);memcpy(temporary+n,".tmp.XXXXXX",12);
    fd=mkstemp(temporary);if(fd<0)return SCM_ONLINE_CHECKPOINT_ERR_IO;
    f=fdopen(fd,"wb");if(!f)goto done;fd=-1;
    if(setvbuf(f,(char*)work->observation_gradient,_IOFBF,sizeof(work->observation_gradient)))goto done;
    c=(codec){f,UINT32_MAX,0,0,0};header(&c);payload(&c,(scm_online*)s);
    if(c.error){rc=c.error;goto done;}
    if(c.count!=SCM_ONLINE_CHECKPOINT_BYTES-4){rc=SCM_ONLINE_CHECKPOINT_ERR_FORMAT;goto done;}
    rc=checksum(f,c.crc,0);if(rc)goto done;rc=SCM_ONLINE_CHECKPOINT_ERR_IO;
    if(fflush(f)||fsync(fileno(f)))goto done;
    if(fclose(f)){f=NULL;goto done;}f=NULL;
    if(rename(temporary,path))goto done;
    rc=0;
done:
    if(f)fclose(f);
    if(fd>=0)close(fd);
    if(rc)unlink(temporary);
    return rc;
}
int scm_online_checkpoint_restore(scm_online *s,const scm_online_config *expected,
    const char *path,scm_online_workspace *work)
{
    FILE *f;codec c;struct stat st;int rc=SCM_ONLINE_CHECKPOINT_ERR_IO;
    if(!s||!expected||!path||!work||!*path||!scm_online_config_valid(expected))return SCM_ONLINE_CHECKPOINT_ERR_ARGUMENT;
    if(strlen(path)>=SCM_ONLINE_CHECKPOINT_PATH_CAPACITY)return SCM_ONLINE_CHECKPOINT_ERR_ARGUMENT;
    if(!binary64_supported())return SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE;
    f=fopen(path,"rb");if(!f)return SCM_ONLINE_CHECKPOINT_ERR_IO;
    if(setvbuf(f,(char*)work->observation_gradient,_IOFBF,sizeof(work->observation_gradient)))goto done;
    if(fstat(fileno(f),&st)||!S_ISREG(st.st_mode))goto done;
    if(st.st_size<(off_t)HEADER_BYTES){rc=SCM_ONLINE_CHECKPOINT_ERR_FORMAT;goto done;}
    c=(codec){f,UINT32_MAX,0,1,0};header(&c);
    rc=c.error;if(rc)goto done;
    if(st.st_size!=(off_t)SCM_ONLINE_CHECKPOINT_BYTES){rc=SCM_ONLINE_CHECKPOINT_ERR_FORMAT;goto done;}
    memset(&work->candidate,0,sizeof(work->candidate));
    payload(&c,&work->candidate);
    rc=c.error;if(rc)goto done;
    if(c.count!=SCM_ONLINE_CHECKPOINT_BYTES-4){rc=SCM_ONLINE_CHECKPOINT_ERR_FORMAT;goto done;}
    rc=checksum(f,c.crc,1);if(rc)goto done;
    if(fgetc(f)!=EOF||ferror(f)){rc=SCM_ONLINE_CHECKPOINT_ERR_FORMAT;goto done;}
    if(!scm_online_config_equal(&work->candidate.config,expected)){rc=SCM_ONLINE_CHECKPOINT_ERR_INCOMPATIBLE;goto done;}
    if(scm_online_validate(&work->candidate)){rc=SCM_ONLINE_CHECKPOINT_ERR_STATE;goto done;}
    if(fclose(f)){f=NULL;rc=SCM_ONLINE_CHECKPOINT_ERR_IO;goto done;}f=NULL;
    *s=work->candidate;rc=0;
done:
    if(f)fclose(f);
    return rc;
}
