#define _POSIX_C_SOURCE 200809L
#include "scm_session_checkpoint.h"
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define HEADER_BYTES 32u
#define FIXED_PAYLOAD_LIMIT 8192u
#define JOURNAL_RECORD_BYTES 25u
#define NUMERIC_FORMAT_BINARY64_LE 1u
#define MODEL_TAG UINT64_C(0x4d31465245463031) /* M1FREF01 */
#if SCM_SESSION_MODEL_VERSION != 1u
#error "Update the checkpoint model tag for a new session model version"
#endif
static const unsigned char magic[8]={'S','C','M','S','E','S','S','1'};

typedef struct {
    FILE *file;
    uint32_t crc;
    uint64_t bytes;
    int reading, measuring, error;
} codec;

static uint32_t crc_bytes(uint32_t crc,const unsigned char *p,size_t n)
{
    size_t i;int k;
    for(i=0;i<n;i++) {
        crc^=p[i];
        for(k=0;k<8;k++)crc=(crc>>1)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    return crc;
}

static int numeric_format_supported(void)
{
    double one=1.;uint64_t bits=0;
    if(CHAR_BIT!=8 || sizeof(double)!=8 || sizeof(uint64_t)!=8 ||
       sizeof(uint32_t)!=4 || DBL_MANT_DIG!=53 || DBL_MAX_EXP!=1024 ||
       sizeof(int)<4)return 0;
    memcpy(&bits,&one,8);
    return bits==UINT64_C(0x3ff0000000000000);
}

static void bytes(codec *c,void *data,size_t n)
{
    if(c->error)return;
    if((uint64_t)n>UINT64_MAX-c->bytes){c->error=SCM_SESSION_CHECKPOINT_ERR_LIMIT;return;}
    if(!c->measuring) {
        size_t done=c->reading?fread(data,1,n,c->file):fwrite(data,1,n,c->file);
        if(done!=n){c->error=SCM_SESSION_CHECKPOINT_ERR_IO;return;}
        c->crc=crc_bytes(c->crc,data,n);
    }
    c->bytes+=(uint64_t)n;
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
    int64_t decoded;
#if INT_MAX > INT32_MAX || INT_MIN < INT32_MIN
    if(!c->reading && (*value<INT32_MIN || *value>INT32_MAX)) {
        c->error=SCM_SESSION_CHECKPOINT_ERR_LIMIT;return;
    }
#endif
    u32(c,&v);if(c->error || !c->reading)return;
    decoded=v<=INT32_MAX?(int64_t)v:(int64_t)v-INT64_C(4294967296);
    if(decoded<INT_MIN || decoded>INT_MAX){c->error=SCM_SESSION_CHECKPOINT_ERR_LIMIT;return;}
    *value=(int)decoded;
}

static void natural(codec *c,unsigned *value)
{
    uint32_t v=c->reading?0:(uint32_t)*value;
#if UINT_MAX > UINT32_MAX
    if(!c->reading && (uint64_t)*value>UINT32_MAX){c->error=SCM_SESSION_CHECKPOINT_ERR_LIMIT;return;}
#endif
    u32(c,&v);
    if(c->reading && !c->error)*value=(unsigned)v;
}

static void size_value(codec *c,size_t *value)
{
    uint64_t v=c->reading?0:(uint64_t)*value;
    u64(c,&v);if(c->error || !c->reading)return;
    if(v>SIZE_MAX){c->error=SCM_SESSION_CHECKPOINT_ERR_LIMIT;return;}
    *value=(size_t)v;
}

static void real(codec *c,double *value)
{
    uint64_t bits=0;double v;
    if(c->error)return;
    if(!c->reading) {
        if(!isfinite(*value)){c->error=SCM_SESSION_CHECKPOINT_ERR_STATE;return;}
        memcpy(&bits,value,8);
    }
    u64(c,&bits);if(c->error || !c->reading)return;
    memcpy(&v,&bits,8);
    if(!isfinite(v)){c->error=SCM_SESSION_CHECKPOINT_ERR_STATE;return;}
    *value=v;
}

static void real_array(codec *c,double *values,size_t n)
{
    size_t i;for(i=0;i<n && !c->error;i++)real(c,&values[i]);
}

static void configuration(codec *c,scm_session_config *v)
{
    unsigned i;
    bytes(c,v->source_id,SCM_SESSION_SOURCE_BYTES);
    integer(c,&v->modes);integer(c,&v->starts);integer(c,&v->max_iterations);
    real(c,&v->sigma);u64(c,&v->max_history_samples);natural(c,&v->schedule_count);
    for(i=0;i<SCM_SESSION_MAX_CHECKPOINTS;i++)u64(c,&v->fit_checkpoints[i]);
}

static void fit_result(codec *c,scm_fit_result *f)
{
    double timing=0;
    real_array(c,f->theta,SCM_MAX_THETA);real_array(c,f->alpha,SCM_MAX_ALPHA);
    real(c,&f->objective);real(c,&f->objective_full);real(c,&f->voltage_rmse);
    /* Timing does not affect inference or the next warm start. Canonical zero
     * makes deterministic checkpoints comparable across fresh processes. */
    real(c,&timing);
    if(c->reading){if(timing!=0)c->error=SCM_SESSION_CHECKPOINT_ERR_FORMAT;f->elapsed_cpu_s=0;}
    real(c,&f->projected_gradient);real(c,&f->max_inner_kkt);
    integer(c,&f->status);integer(c,&f->termination_reason);integer(c,&f->iterations);
    integer(c,&f->evaluations);integer(c,&f->converged_starts);integer(c,&f->starts);
    integer(c,&f->active_linear_constraints);integer(c,&f->active_outer_bounds);
    size_value(c,&f->samples);size_value(c,&f->features);size_value(c,&f->blocks);
    size_value(c,&f->data_bytes);size_value(c,&f->basis_bytes);size_value(c,&f->payload_bytes);
    size_value(c,&f->workspace_bytes);size_value(c,&f->retained_bytes);size_value(c,&f->setup_peak_bytes);
    timing=0;real(c,&timing);
    if(c->reading){if(timing!=0)c->error=SCM_SESSION_CHECKPOINT_ERR_FORMAT;f->basis_seconds=0;}
    real(c,&f->basis_max_orthogonality);real(c,&f->max_discarded_column_norm);
    real_array(c,f->joint_normal,SCM_MAX_PARAMETERS*SCM_MAX_PARAMETERS);
    real_array(c,f->coordinate_scales,SCM_MAX_PARAMETERS);
    natural(c,&f->unexcited_theta_mask);
    real(c,&f->elapsed_physical_s);real(c,&f->charge_Ah);
}

/* Write mode does not modify any field. A single decoder handles exactly the
 * same explicit field sequence; the save entry point casts const only for
 * this shared codec, whose writes are guarded by c->reading. */
static void payload(codec *c,scm_session *s,const scm_session_config *expected,uint64_t length)
{
    size_t i;
    configuration(c,&s->config);if(c->error)return;
    if(c->reading && (!scm_session_config_valid(&s->config) ||
       !scm_session_config_equal(&s->config,expected))) {
        c->error=SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE;return;
    }
    if(c->reading)for(i=0;i<SCM_SESSION_MAX_CHECKPOINTS;i++)
        if(s->config.fit_checkpoints[i]!=expected->fit_checkpoints[i]) {
            c->error=SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE;return;
        }
    size_value(c,&s->count);size_value(c,&s->capacity);
    if(s->count>s->capacity || (uint64_t)s->capacity>s->config.max_history_samples ||
       s->capacity>SIZE_MAX/sizeof(*s->samples)) {
        c->error=SCM_SESSION_CHECKPOINT_ERR_LIMIT;return;
    }
    u64(c,&s->epoch_begin);u64(c,&s->next_index);u64(c,&s->cold_resets);
    u64(c,&s->fit_attempts);u64(c,&s->fit_results);u64(c,&s->last_fit_next_index);
    u64(c,&s->last_fit_attempt_index);natural(c,&s->schedule_cursor);natural(c,&s->flags);
    integer(c,&s->has_fit);integer(c,&s->last_fit_code);
    real(c,&s->epoch_start_elapsed_s);real(c,&s->elapsed_total_s);
    real(c,&s->epoch_elapsed_s);real(c,&s->epoch_charge_Ah);
    fit_result(c,&s->fit);
    size_value(c,&s->peak_owned_bytes);size_value(c,&s->last_problem_auxiliary_bytes);
    size_value(c,&s->peak_fit_owned_bytes);
    if(c->error)return;
    if(c->reading && (c->bytes>HEADER_BYTES+length ||
       (uint64_t)s->count>(UINT64_MAX-c->bytes)/JOURNAL_RECORD_BYTES ||
       c->bytes+(uint64_t)s->count*JOURNAL_RECORD_BYTES!=HEADER_BYTES+length)) {
        c->error=SCM_SESSION_CHECKPOINT_ERR_FORMAT;return;
    }
    if(c->reading && s->capacity) {
        s->samples=malloc(s->capacity*sizeof(*s->samples));
        s->voltage_present=malloc(s->capacity);
        if(!s->samples || !s->voltage_present){c->error=SCM_SESSION_CHECKPOINT_ERR_ALLOC;return;}
    }
    for(i=0;i<s->count && !c->error;i++) {
        real(c,&s->samples[i].dt);real(c,&s->samples[i].current);
        real(c,&s->samples[i].voltage);bytes(c,&s->voltage_present[i],1);
    }
}

static void header(codec *c,uint64_t *payload_bytes)
{
    unsigned char signature[8];uint32_t version=SCM_SESSION_CHECKPOINT_VERSION;
    uint32_t numeric=NUMERIC_FORMAT_BINARY64_LE;uint64_t model=MODEL_TAG;
    if(!c->reading)memcpy(signature,magic,sizeof(signature));
    bytes(c,signature,sizeof(signature));u32(c,&version);u32(c,&numeric);
    u64(c,&model);u64(c,payload_bytes);
    if(c->error)return;
    if(memcmp(signature,magic,8) || version!=SCM_SESSION_CHECKPOINT_VERSION ||
       numeric!=NUMERIC_FORMAT_BINARY64_LE || model!=MODEL_TAG)
        c->error=SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE;
}

static int read_crc(FILE *f,uint32_t *crc)
{
    unsigned char b[4];unsigned i;
    if(fread(b,1,4,f)!=4)return SCM_SESSION_CHECKPOINT_ERR_IO;
    *crc=0;for(i=0;i<4;i++)*crc|=(uint32_t)b[i]<<(8*i);
    return 0;
}

/* Verify the framing and checksum before an untrusted payload can request an
 * allocation. Decode computes the checksum again, binding decoded bytes to
 * the checked record even if the caller violates immutable-file ownership. */
static int validate_frame(FILE *f,const scm_session_config *expected,uint64_t *length)
{
    struct stat st;codec c={f,UINT32_MAX,0,1,0,0};
    unsigned char buffer[256];uint32_t stored;uint64_t remaining,limit;
    int rc;
    header(&c,length);if(c.error)return c.error;
    if(expected->max_history_samples>(UINT64_MAX-FIXED_PAYLOAD_LIMIT)/JOURNAL_RECORD_BYTES)
        return SCM_SESSION_CHECKPOINT_ERR_LIMIT;
    limit=FIXED_PAYLOAD_LIMIT+expected->max_history_samples*JOURNAL_RECORD_BYTES;
    if(*length>limit || *length>UINT64_MAX-HEADER_BYTES-4u)return SCM_SESSION_CHECKPOINT_ERR_LIMIT;
    if(fstat(fileno(f),&st) || !S_ISREG(st.st_mode) || st.st_size<0)
        return SCM_SESSION_CHECKPOINT_ERR_IO;
    if((uint64_t)st.st_size!=HEADER_BYTES+*length+4u)return SCM_SESSION_CHECKPOINT_ERR_FORMAT;
    remaining=*length;
    while(remaining && !c.error) {
        size_t take=remaining>sizeof(buffer)?sizeof(buffer):(size_t)remaining;
        bytes(&c,buffer,take);remaining-=take;
    }
    if(c.error)return c.error;
    rc=read_crc(f,&stored);if(rc)return rc;
    if(stored!=~c.crc)return SCM_SESSION_CHECKPOINT_ERR_INTEGRITY;
    if(fgetc(f)!=EOF || ferror(f))return SCM_SESSION_CHECKPOINT_ERR_FORMAT;
    if(fseek(f,0,SEEK_SET))return SCM_SESSION_CHECKPOINT_ERR_IO;
    return 0;
}

int scm_session_checkpoint_save(const scm_session *s,const char *path)
{
    codec measure={NULL,UINT32_MAX,0,0,1,0},writer;
    char *temporary=NULL;FILE *f=NULL;size_t length;uint64_t payload_bytes;
    int fd=-1,rc=SCM_SESSION_CHECKPOINT_ERR_IO;unsigned i;unsigned char checksum[4];uint32_t crc;
    if(!s || !path || !*path || !s->initialized || !scm_session_config_valid(&s->config))
        return SCM_SESSION_CHECKPOINT_ERR_ARGUMENT;
    if(!numeric_format_supported())return SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE;
    if(s->count>s->capacity || (s->capacity && (!s->samples || !s->voltage_present)))
        return SCM_SESSION_CHECKPOINT_ERR_STATE;
    payload(&measure,(scm_session*)s,NULL,0);
    if(measure.error)return measure.error;
    payload_bytes=measure.bytes;
    length=strlen(path);if(length>SIZE_MAX-12)return SCM_SESSION_CHECKPOINT_ERR_LIMIT;
    temporary=malloc(length+12);if(!temporary)return SCM_SESSION_CHECKPOINT_ERR_ALLOC;
    memcpy(temporary,path,length);memcpy(temporary+length,".tmp.XXXXXX",12);
    fd=mkstemp(temporary);if(fd<0)goto done;
    f=fdopen(fd,"wb");if(!f)goto done;fd=-1;
    writer=(codec){f,UINT32_MAX,0,0,0,0};
    header(&writer,&payload_bytes);payload(&writer,(scm_session*)s,NULL,0);
    if(writer.error){rc=writer.error;goto done;}
    if(writer.bytes!=HEADER_BYTES+payload_bytes){rc=SCM_SESSION_CHECKPOINT_ERR_STATE;goto done;}
    crc=~writer.crc;for(i=0;i<4;i++)checksum[i]=(unsigned char)(crc>>(8*i));
    if(fwrite(checksum,1,4,f)!=4 || fflush(f) || fsync(fileno(f)))goto done;
    if(fclose(f)){f=NULL;goto done;}f=NULL;
    if(rename(temporary,path))goto done;
    rc=0;
done:
    if(f)fclose(f);
    if(fd>=0)close(fd);
    if(temporary){if(rc)unlink(temporary);free(temporary);}
    return rc;
}

int scm_session_checkpoint_restore(scm_session *destination,
    const scm_session_config *expected,const char *path)
{
    scm_session candidate;FILE *f=NULL;codec reader;uint64_t length=0,decoded_length=0;
    uint32_t stored;int rc;
    if(!destination || !expected || !path || !*path || !scm_session_config_valid(expected))
        return SCM_SESSION_CHECKPOINT_ERR_ARGUMENT;
    if(!numeric_format_supported())return SCM_SESSION_CHECKPOINT_ERR_INCOMPATIBLE;
    memset(&candidate,0,sizeof(candidate));
    f=fopen(path,"rb");if(!f)return SCM_SESSION_CHECKPOINT_ERR_IO;
    rc=validate_frame(f,expected,&length);if(rc)goto done;
    candidate.initialized=1;
    reader=(codec){f,UINT32_MAX,0,1,0,0};
    header(&reader,&decoded_length);
    if(!reader.error && decoded_length!=length)reader.error=SCM_SESSION_CHECKPOINT_ERR_FORMAT;
    payload(&reader,&candidate,expected,length);
    rc=reader.error;if(rc)goto done;
    if(reader.bytes!=HEADER_BYTES+length){rc=SCM_SESSION_CHECKPOINT_ERR_FORMAT;goto done;}
    rc=read_crc(f,&stored);if(rc)goto done;
    if(stored!=~reader.crc){rc=SCM_SESSION_CHECKPOINT_ERR_INTEGRITY;goto done;}
    if(fgetc(f)!=EOF || ferror(f)){rc=SCM_SESSION_CHECKPOINT_ERR_FORMAT;goto done;}
    if(scm_session_rebuild(&candidate)){rc=SCM_SESSION_CHECKPOINT_ERR_STATE;goto done;}
    if(fclose(f)){f=NULL;rc=SCM_SESSION_CHECKPOINT_ERR_IO;goto done;}f=NULL;
    /* All fallible operations precede transfer of ownership. */
    scm_session_destroy(destination);*destination=candidate;
    memset(&candidate,0,sizeof(candidate));rc=0;
done:
    if(f)fclose(f);
    scm_session_destroy(&candidate);
    return rc;
}
