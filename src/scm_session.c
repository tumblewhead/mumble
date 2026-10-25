#include "scm_session.h"
#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

static int live(const scm_session *s)
{
    return s && s->initialized==1 && scm_session_config_valid(&s->config) &&
        s->count<=s->capacity && s->capacity<=s->config.max_history_samples &&
        (!s->capacity || (s->samples && s->voltage_present)) &&
        s->epoch_begin<=s->next_index && s->next_index-s->epoch_begin==s->count &&
        s->schedule_cursor<=s->config.schedule_count;
}

void scm_session_config_default(scm_session_config *c)
{
    if(!c)return;
    memset(c,0,sizeof(*c));c->modes=3;c->starts=3;c->max_iterations=120;
    c->sigma=.001;c->max_history_samples=73500;c->schedule_count=4;
    c->fit_checkpoints[0]=350;c->fit_checkpoints[1]=31500;
    c->fit_checkpoints[2]=63000;c->fit_checkpoints[3]=73500;
}

int scm_session_config_valid(const scm_session_config *c)
{
    unsigned i;
    if(!c || !scm_model_ntheta(c->modes) || c->starts<1 || c->starts>100 ||
       c->max_iterations<1 || c->max_iterations>100000 || !isfinite(c->sigma) ||
       !(c->sigma>0) || !c->max_history_samples ||
       c->max_history_samples>(SIZE_MAX-sizeof(scm_session))/(sizeof(scm_sample)+1) ||
       c->schedule_count>SCM_SESSION_MAX_CHECKPOINTS)return 0;
    for(i=0;i<c->schedule_count;i++)
        if(!c->fit_checkpoints[i] || (i && c->fit_checkpoints[i]<=c->fit_checkpoints[i-1]))return 0;
    return 1;
}

int scm_session_config_equal(const scm_session_config *a,const scm_session_config *b)
{
    unsigned i;
    if(!scm_session_config_valid(a)||!scm_session_config_valid(b))return 0;
    if(memcmp(a->source_id,b->source_id,SCM_SESSION_SOURCE_BYTES) ||
       a->modes!=b->modes || a->starts!=b->starts || a->max_iterations!=b->max_iterations ||
       a->sigma!=b->sigma || a->max_history_samples!=b->max_history_samples ||
       a->schedule_count!=b->schedule_count)return 0;
    for(i=0;i<a->schedule_count;i++)if(a->fit_checkpoints[i]!=b->fit_checkpoints[i])return 0;
    return 1;
}

size_t scm_session_owned_bytes(const scm_session *s)
{
    if(!s || s->capacity>(SIZE_MAX-sizeof(*s))/(sizeof(scm_sample)+1))return SIZE_MAX;
    return sizeof(*s)+s->capacity*(sizeof(scm_sample)+1);
}

static int public_model(scm_session *s)
{
    double theta[SCM_MAX_THETA]={0};
    scm_default_theta(s->config.modes,0,theta);
    s->model_valid=scm_model_init(&s->model,s->config.modes,theta)==SCM_OK;
    s->prediction_valid=0;s->predicted_voltage_V=0;
    return s->model_valid?SCM_SESSION_OK:SCM_SESSION_ERR_STATE;
}

int scm_session_init(scm_session *s,const scm_session_config *c)
{
    scm_session next;
    if(!s || !scm_session_config_valid(c))return SCM_SESSION_ERR_ARGUMENT;
    memset(&next,0,sizeof(next));next.config=*c;next.initialized=1;
    if(public_model(&next))return SCM_SESSION_ERR_STATE;
    next.peak_owned_bytes=sizeof(next);*s=next;return SCM_SESSION_OK;
}

void scm_session_destroy(scm_session *s)
{
    if(!s)return;
    if(s->initialized==1){free(s->samples);free(s->voltage_present);}
    memset(s,0,sizeof(*s));
}

/* Two new buffers are allocated before either old buffer is released. A
 * failed allocation changes neither pointers nor existing journal contents.
 * Include the transient old+new requested buffers in the recorded peak. */
static int reserve(scm_session *s,size_t needed)
{
    scm_sample *samples;unsigned char *present;
    size_t capacity,old_bytes,new_bytes,peak;
    if(needed<=s->capacity)return SCM_SESSION_OK;
    capacity=s->capacity?s->capacity:1024;
    if(capacity>s->config.max_history_samples)capacity=(size_t)s->config.max_history_samples;
    while(capacity<needed) {
        if(capacity>s->config.max_history_samples/2){capacity=(size_t)s->config.max_history_samples;break;}
        capacity*=2;
    }
    if(capacity<needed)return SCM_SESSION_ERR_OVERFLOW;
    old_bytes=s->capacity*(sizeof(scm_sample)+1);new_bytes=capacity*(sizeof(scm_sample)+1);
    if(new_bytes>SIZE_MAX-sizeof(*s)-old_bytes)return SCM_SESSION_ERR_OVERFLOW;
    samples=malloc(capacity*sizeof(*samples));if(!samples)return SCM_SESSION_ERR_ALLOCATION;
    present=malloc(capacity);if(!present){free(samples);return SCM_SESSION_ERR_ALLOCATION;}
    if(s->count){memcpy(samples,s->samples,s->count*sizeof(*samples));memcpy(present,s->voltage_present,s->count);}
    free(s->samples);free(s->voltage_present);s->samples=samples;s->voltage_present=present;s->capacity=capacity;
    peak=sizeof(*s)+old_bytes+new_bytes;if(peak>s->peak_owned_bytes)s->peak_owned_bytes=peak;
    return SCM_SESSION_OK;
}

int scm_session_fit_due(const scm_session *s)
{
    return live(s) && !(s->flags&SCM_SESSION_FLAG_RECOVERY_REQUIRED) &&
        s->schedule_cursor<s->config.schedule_count &&
        s->next_index==s->config.fit_checkpoints[s->schedule_cursor];
}

int scm_session_ingest(scm_session *s,const unsigned char id[SCM_SESSION_SOURCE_BYTES],
    uint64_t index,const scm_sample *input,int voltage_present)
{
    scm_sample sample;scm_model_state model;scm_model_row row;
    double total,elapsed,charge,predicted=0;int valid,prediction=0,status;
    if(!s||!id||!input||(voltage_present!=0&&voltage_present!=1))return SCM_SESSION_ERR_ARGUMENT;
    if(!live(s))return SCM_SESSION_ERR_STATE;
    if(memcmp(id,s->config.source_id,SCM_SESSION_SOURCE_BYTES))return SCM_SESSION_ERR_SOURCE;
    if(index!=s->next_index)return SCM_SESSION_ERR_ORDER;
    if(index==UINT64_MAX || s->count>=s->config.max_history_samples)return SCM_SESSION_ERR_OVERFLOW;
    if(s->flags&SCM_SESSION_FLAG_RECOVERY_REQUIRED)return SCM_SESSION_ERR_RECOVERY_REQUIRED;
    if(s->schedule_cursor<s->config.schedule_count &&
       s->next_index>=s->config.fit_checkpoints[s->schedule_cursor])return SCM_SESSION_ERR_NOT_DUE;
    sample=*input;
    if(!isfinite(sample.dt)||!isfinite(sample.current)||(voltage_present&&!isfinite(sample.voltage)))
        return SCM_SESSION_ERR_NONFINITE;
    if(sample.dt<0)return SCM_SESSION_ERR_ARGUMENT;
    if(!voltage_present)sample.voltage=0;
    total=s->elapsed_total_s+sample.dt;elapsed=s->epoch_elapsed_s+sample.dt;
    charge=s->epoch_charge_Ah+sample.current*sample.dt/3600.;
    if(!isfinite(total)||!isfinite(elapsed)||!isfinite(charge))return SCM_SESSION_ERR_NONFINITE;
    model=s->model;valid=s->model_valid;
    if(valid) {
        status=scm_model_step(&model,NULL,sample.dt,sample.current,&row);
        if(status)valid=0;
        else if(s->has_fit)prediction=scm_model_predict(&row,s->config.modes,s->fit.alpha,&predicted,NULL)==SCM_OK;
    }
    status=reserve(s,s->count+1);if(status)return status;
    /* No fallible operation remains: retain known input even when this point
     * model leaves its domain. Its state/prediction then becomes unavailable. */
    s->samples[s->count]=sample;s->voltage_present[s->count]=(unsigned char)voltage_present;
    s->count++;s->next_index++;s->elapsed_total_s=total;s->epoch_elapsed_s=elapsed;s->epoch_charge_Ah=charge;
    s->model=model;s->model_valid=valid;s->prediction_valid=prediction;s->predicted_voltage_V=prediction?predicted:0;
    if(!voltage_present)s->flags|=SCM_SESSION_FLAG_MISSING_VOLTAGE;
    if(!valid)s->flags|=SCM_SESSION_FLAG_MODEL_UNAVAILABLE;
    return SCM_SESSION_OK;
}

int scm_session_advance(scm_session *s,const unsigned char id[SCM_SESSION_SOURCE_BYTES],
    uint64_t index,double dt,double current)
{
    scm_sample sample={dt,current,0};return scm_session_ingest(s,id,index,&sample,0);
}

static int reconstruct_model(const scm_session *s,const scm_fit_result *fit,int has_fit,
    scm_model_state *model,int *valid,double *prediction,int *prediction_valid)
{
    double theta[SCM_MAX_THETA]={0};scm_model_row row;size_t k;
    if(has_fit)memcpy(theta,fit->theta,sizeof(theta));else scm_default_theta(s->config.modes,0,theta);
    if(scm_model_init(model,s->config.modes,theta))return SCM_SESSION_ERR_STATE;
    *valid=1;*prediction_valid=0;*prediction=0;
    for(k=0;k<s->count;k++) {
        if(*valid) {
            if(scm_model_step(model,NULL,s->samples[k].dt,s->samples[k].current,&row))*valid=0;
            else if(has_fit)*prediction_valid=scm_model_predict(&row,s->config.modes,fit->alpha,prediction,NULL)==SCM_OK;
        }
        if(!*valid)*prediction_valid=0;
    }
    if(!*prediction_valid)*prediction=0;
    return SCM_SESSION_OK;
}

static int finite_fit(const scm_fit_result *f,int n)
{
    double lo[SCM_MAX_THETA],hi[SCM_MAX_THETA];int i,nt=scm_model_ntheta(n),na=scm_model_nalpha(n),d=nt+na;
    if(!nt)return 0;
    scm_theta_bounds(n,lo,hi);
    for(i=0;i<nt;i++)if(!isfinite(f->theta[i])||f->theta[i]<lo[i]-1e-8||f->theta[i]>hi[i]+1e-8)return 0;
    for(i=0;i<na;i++) {
        double lower=i<=n+1?0:(i==na-1?-.1:-.08),upper=i<=n?1:(i==n+1?.1:(i==na-1?.1:.08));
        if(!isfinite(f->alpha[i])||f->alpha[i]<lower-1e-8||f->alpha[i]>upper+1e-8)return 0;
    }
    if(fabs(f->alpha[na-1])>f->alpha[n+1]+1e-8)return 0;
    for(i=0;i<d*d;i++)if(!isfinite(f->joint_normal[i]))return 0;
    for(i=0;i<d;i++)if(!isfinite(f->coordinate_scales[i])||f->coordinate_scales[i]<=0)return 0;
    return isfinite(f->objective)&&f->objective>=0&&isfinite(f->objective_full)&&f->objective_full>=0&&
        isfinite(f->voltage_rmse)&&f->voltage_rmse>=0&&isfinite(f->projected_gradient)&&
        isfinite(f->max_inner_kkt)&&isfinite(f->elapsed_physical_s)&&isfinite(f->charge_Ah)&&
        f->status>=0&&f->status<=2&&f->starts>0&&f->starts<=100&&f->iterations>=0&&f->evaluations>=0;
}

int scm_session_fit(scm_session *s)
{
    scm_problem *problem;scm_fit_options options;scm_fit_result result;
    scm_model_state model;int status,valid,prediction_valid;double prediction;size_t auxiliary,owned;
    if(!live(s))return SCM_SESSION_ERR_STATE;
    if(s->flags&SCM_SESSION_FLAG_RECOVERY_REQUIRED)return SCM_SESSION_ERR_RECOVERY_REQUIRED;
    if(!scm_session_fit_due(s))return SCM_SESSION_ERR_NOT_DUE;
    if(s->fit_attempts==UINT64_MAX)return SCM_SESSION_ERR_OVERFLOW;
    s->fit_attempts++;s->last_fit_attempt_index=s->next_index;s->schedule_cursor++;
    if(s->flags&SCM_SESSION_FLAG_MISSING_VOLTAGE) {
        s->flags|=SCM_SESSION_FLAG_FIT_FAILED;s->last_fit_code=SCM_SESSION_ERR_MISSING_VOLTAGE;
        return s->last_fit_code;
    }
    if(!s->count){s->flags|=SCM_SESSION_FLAG_FIT_FAILED;s->last_fit_code=SCM_SESSION_ERR_STATE;return s->last_fit_code;}
    scm_fit_options_default(&options);options.starts=s->config.starts;options.max_iterations=s->config.max_iterations;
    if(s->has_fit){options.has_initial=1;memcpy(options.initial_theta,s->fit.theta,sizeof(options.initial_theta));}
    problem=scm_problem_create(s->samples,s->count,s->config.modes,s->config.sigma,NULL,SCM_FULL);
    if(!problem){s->flags|=SCM_SESSION_FLAG_FIT_FAILED;s->last_fit_code=SCM_SESSION_ERR_ALLOCATION;return s->last_fit_code;}
    memset(&result,0,sizeof(result));status=scm_fit(problem,&options,&result);scm_problem_destroy(problem);
    if(status || !finite_fit(&result,s->config.modes) ||
       reconstruct_model(s,&result,1,&model,&valid,&prediction,&prediction_valid) || !valid) {
        s->flags|=SCM_SESSION_FLAG_FIT_FAILED;s->last_fit_code=SCM_SESSION_ERR_FIT;return s->last_fit_code;
    }
    s->fit=result;s->has_fit=1;s->fit_results++;s->last_fit_next_index=s->next_index;
    s->last_fit_code=0;s->flags&=~(SCM_SESSION_FLAG_FIT_FAILED|SCM_SESSION_FLAG_MODEL_UNAVAILABLE);
    s->model=model;s->model_valid=valid;s->predicted_voltage_V=prediction;s->prediction_valid=prediction_valid;
    /* The reference's retained_bytes includes its BORROWED sample array.
     * Our journal already owns it; add only the problem's auxiliary storage. */
    auxiliary=result.retained_bytes>=result.data_bytes?result.retained_bytes-result.data_bytes:0;
    owned=scm_session_owned_bytes(s);s->last_problem_auxiliary_bytes=auxiliary;
    if(auxiliary<=SIZE_MAX-owned && owned+auxiliary>s->peak_fit_owned_bytes)s->peak_fit_owned_bytes=owned+auxiliary;
    return SCM_SESSION_OK;
}

const char *scm_session_status_name(scm_session_status status)
{
    switch(status) {
        case SCM_SESSION_TRACKING:return "tracking";
        case SCM_SESSION_RECOVERY_REQUIRED:return "recovery_required";
        case SCM_SESSION_POINT_UNAVAILABLE:return "point_unavailable";
        default:return "collecting";
    }
}

int scm_session_query(const scm_session *s,scm_session_query_result *out,
    scm_assessment *assessment,scm_assess_workspace *workspace)
{
    scm_fit_result current;double q,z;
    if(!live(s)||!out||((assessment==NULL)!=(workspace==NULL)))return SCM_SESSION_ERR_ARGUMENT;
    memset(out,0,sizeof(*out));if(assessment)memset(assessment,0,sizeof(*assessment));
    out->status=SCM_SESSION_COLLECTING;out->flags=s->flags;out->epoch_begin=s->epoch_begin;out->next_index=s->next_index;
    out->evidence_next_index=s->has_fit?s->last_fit_next_index:s->epoch_begin;
    out->evidence_age_samples=s->next_index-out->evidence_next_index;out->evidence_current=s->has_fit&&s->next_index==s->last_fit_next_index;
    out->cold_resets=s->cold_resets;out->fit_attempts=s->fit_attempts;out->fit_results=s->fit_results;
    out->last_fit_attempt_index=s->last_fit_attempt_index;out->elapsed_s=s->elapsed_total_s;
    out->epoch_elapsed_s=s->epoch_elapsed_s;out->epoch_charge_Ah=s->epoch_charge_Ah;
    out->optimizer_status=s->has_fit?s->fit.status:-1;out->last_fit_code=s->last_fit_code;
    out->fit_due=scm_session_fit_due(s);out->fitting_available=!(s->flags&(SCM_SESSION_FLAG_MISSING_VOLTAGE|SCM_SESSION_FLAG_RECOVERY_REQUIRED));
    out->history_samples=s->count;out->history_capacity=s->capacity;out->owned_bytes=scm_session_owned_bytes(s);
    out->peak_owned_bytes=s->peak_owned_bytes;out->last_problem_auxiliary_bytes=s->last_problem_auxiliary_bytes;out->peak_fit_owned_bytes=s->peak_fit_owned_bytes;
    if(s->flags&SCM_SESSION_FLAG_RECOVERY_REQUIRED){out->status=SCM_SESSION_RECOVERY_REQUIRED;return SCM_SESSION_OK;}
    if(!s->has_fit)return SCM_SESSION_OK;
    q=exp(s->fit.theta[s->config.modes+3]);z=s->fit.theta[s->config.modes+2]-s->epoch_charge_Ah/q;
    out->capacity_available=isfinite(q)&&q>0;out->capacity_Ah=out->capacity_available?q:0;
    out->point_available=s->model_valid&&isfinite(z)&&z>=0&&z<=1;out->current_soc=out->point_available?z:0;
    out->voltage_prediction_available=s->model_valid&&s->prediction_valid;out->predicted_voltage_V=out->voltage_prediction_available?s->predicted_voltage_V:0;
    out->status=out->point_available?SCM_SESSION_TRACKING:SCM_SESSION_POINT_UNAVAILABLE;
    if(assessment && out->point_available) {
        current=s->fit;current.charge_Ah=s->epoch_charge_Ah;current.elapsed_physical_s=s->epoch_elapsed_s;
        out->assessment_available=scm_assess(&current,s->config.modes,NULL,assessment,workspace)==0;
    }
    return SCM_SESSION_OK;
}

int scm_session_mark_unknown_gap(scm_session *s)
{
    if(!live(s))return SCM_SESSION_ERR_ARGUMENT;
    s->flags|=SCM_SESSION_FLAG_RECOVERY_REQUIRED;return SCM_SESSION_ERR_RECOVERY_REQUIRED;
}

int scm_session_cold_reset(scm_session *s)
{
    if(!live(s))return SCM_SESSION_ERR_STATE;
    if(s->cold_resets==UINT64_MAX)return SCM_SESSION_ERR_OVERFLOW;
    free(s->samples);free(s->voltage_present);s->samples=NULL;s->voltage_present=NULL;s->count=s->capacity=0;
    s->epoch_begin=s->next_index;s->epoch_start_elapsed_s=s->elapsed_total_s;s->epoch_elapsed_s=s->epoch_charge_Ah=0;
    s->cold_resets++;s->has_fit=0;s->last_fit_next_index=s->next_index;
    s->flags=SCM_SESSION_FLAG_HISTORY_LOST;s->last_fit_code=0;memset(&s->fit,0,sizeof(s->fit));
    s->last_problem_auxiliary_bytes=0;s->schedule_cursor=0;
    while(s->schedule_cursor<s->config.schedule_count &&
          s->config.fit_checkpoints[s->schedule_cursor]<=s->next_index)s->schedule_cursor++;
    return public_model(s);
}

int scm_session_rebuild(scm_session *s)
{
    double total,elapsed=0,charge=0,fit_time=0,fit_charge=0,prediction;
    scm_model_state model;size_t i,fit_count=0;unsigned missing=0;int valid,prediction_valid;
    const unsigned allowed=SCM_SESSION_FLAG_HISTORY_LOST|SCM_SESSION_FLAG_MISSING_VOLTAGE|
        SCM_SESSION_FLAG_RECOVERY_REQUIRED|SCM_SESSION_FLAG_FIT_FAILED|SCM_SESSION_FLAG_MODEL_UNAVAILABLE;
    if(!live(s)||s->flags&~allowed||s->has_fit<0||s->has_fit>1||s->fit_results>s->fit_attempts ||
       !isfinite(s->epoch_start_elapsed_s)||s->epoch_start_elapsed_s<0 ||
       !isfinite(s->elapsed_total_s)||!isfinite(s->epoch_elapsed_s)||!isfinite(s->epoch_charge_Ah))return SCM_SESSION_ERR_STATE;
    if((s->cold_resets!=0)!=((s->flags&SCM_SESSION_FLAG_HISTORY_LOST)!=0))return SCM_SESSION_ERR_STATE;
    if(s->last_fit_attempt_index>s->next_index || (!s->fit_attempts && s->last_fit_attempt_index))return SCM_SESSION_ERR_STATE;
    if(s->has_fit) {
        if(s->last_fit_next_index<=s->epoch_begin||s->last_fit_next_index>s->last_fit_attempt_index||!s->fit_results||
           !finite_fit(&s->fit,s->config.modes))return SCM_SESSION_ERR_STATE;
        fit_count=(size_t)(s->last_fit_next_index-s->epoch_begin);
        if(s->fit.samples!=fit_count)return SCM_SESSION_ERR_STATE;
    } else if(s->last_fit_next_index!=s->epoch_begin)return SCM_SESSION_ERR_STATE;
    for(i=0;i<s->schedule_cursor;i++)if(s->config.fit_checkpoints[i]>s->next_index)return SCM_SESSION_ERR_STATE;
    if(s->schedule_cursor<s->config.schedule_count && s->config.fit_checkpoints[s->schedule_cursor]<s->next_index)return SCM_SESSION_ERR_STATE;
    total=s->epoch_start_elapsed_s;
    for(i=0;i<s->count;i++) {
        const scm_sample *sample=&s->samples[i];unsigned present=s->voltage_present[i];
        if(present>1||!isfinite(sample->dt)||sample->dt<0||!isfinite(sample->current)||!isfinite(sample->voltage)||
           (!present&&sample->voltage!=0))return SCM_SESSION_ERR_STATE;
        if(!present)missing=1;
        total+=sample->dt;elapsed+=sample->dt;charge+=sample->current*sample->dt/3600.;
        if(!isfinite(total)||!isfinite(elapsed)||!isfinite(charge))return SCM_SESSION_ERR_STATE;
        if(i+1==fit_count){fit_time=elapsed;fit_charge=charge;}
    }
    if(total!=s->elapsed_total_s||elapsed!=s->epoch_elapsed_s||charge!=s->epoch_charge_Ah||
       missing!=((s->flags&SCM_SESSION_FLAG_MISSING_VOLTAGE)!=0))return SCM_SESSION_ERR_STATE;
    if(s->has_fit && (fit_time!=s->fit.elapsed_physical_s||fit_charge!=s->fit.charge_Ah))return SCM_SESSION_ERR_STATE;
    if(reconstruct_model(s,&s->fit,s->has_fit,&model,&valid,&prediction,&prediction_valid))return SCM_SESSION_ERR_STATE;
    s->model=model;s->model_valid=valid;s->predicted_voltage_V=prediction;s->prediction_valid=prediction_valid;
    if(valid)s->flags&=~SCM_SESSION_FLAG_MODEL_UNAVAILABLE;else s->flags|=SCM_SESSION_FLAG_MODEL_UNAVAILABLE;
    if(s->peak_owned_bytes<scm_session_owned_bytes(s))s->peak_owned_bytes=scm_session_owned_bytes(s);
    return SCM_SESSION_OK;
}
