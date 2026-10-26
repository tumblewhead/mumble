#include "boundary_transaction_capture.h"
#include <float.h>
#include <math.h>
#include <string.h>

#define D SCM_ONLINE_DIM
#define AT(i,j) ((i)*D+(j))

/* Binary64 constants of the inherited public supports. Constant arrays are
 * read-only configuration, not per-stream RAM or a fitted/truth-derived prior. */
static const double lower[D]={
    -4.199705077879927,-1.8971199848858813,.40546510810816438,
    1.6094379124341003,1.6094379124341003,-3.5065578973199818,
    0,0,0,0,0,0,-.25,-.25,-.25,-1
};
static const double upper[D]={
    -1.8971199848858813,.40546510810816438,3.4011973816621555,
    7.0900768357760917,7.0900768357760917,-2.3025850929940455,
    1,1,1,1,.1,1,.25,.25,.25,1
};

void scm_online_bounds(double lo[D],double hi[D])
{
    if(lo)memcpy(lo,lower,sizeof(lower));
    if(hi)memcpy(hi,upper,sizeof(upper));
}

void scm_online_config_default(scm_online_config *c)
{
    if(!c)return;
    memset(c,0,sizeof(*c));c->sigma_V=.001;c->max_dt_s=1.;c->max_abs_current_A=.25;
}

int scm_online_config_valid(const scm_online_config *c)
{
    return c && isfinite(c->sigma_V) && c->sigma_V>=1e-12 && c->sigma_V<=1. &&
        isfinite(c->max_dt_s) && c->max_dt_s>0 && c->max_dt_s<=1. &&
        isfinite(c->max_abs_current_A) && c->max_abs_current_A>0 && c->max_abs_current_A<=.25;
}

int scm_online_config_equal(const scm_online_config *a,const scm_online_config *b)
{
    return scm_online_config_valid(a)&&scm_online_config_valid(b)&&
        !memcmp(a->source_id,b->source_id,SCM_ONLINE_SOURCE_BYTES)&&
        a->sigma_V==b->sigma_V&&a->max_dt_s==b->max_dt_s&&a->max_abs_current_A==b->max_abs_current_A;
}

static void public_belief(scm_online *s)
{
    const double root12=3.4641016151377545871;
    int i;
    memset(s->mean,0,sizeof(s->mean));memset(s->factor,0,sizeof(s->factor));
    for(i=0;i<3;i++)s->mean[i]=lower[i]+.5*(upper[i]-lower[i]);
    s->mean[3]=5.0106352940962555;s->mean[4]=5.7037824746562009;
    s->mean[5]=-2.8134107167600364;
    for(i=6;i<=9;i++)s->mean[i]=.1;
    s->mean[10]=.024;s->mean[11]=.68;
    for(i=0;i<D;i++) {
        double width=upper[i]-lower[i];
        if(i==11)width=.75; /* entering SOC support [.2,.95] */
        if(i>=12&&i<=14)width=.16; /* entering v support [-.08,.08] */
        s->factor[AT(i,i)]=width/root12;
    }
    s->has_voltage=0;s->prediction_valid=0;s->excitation=0;
    s->last_current_A=s->last_prediction_V=s->last_innovation_V=0;
    s->last_innovation_variance_V2=s->innovation_ewma=0;
    s->last_gain_scale=s->last_max_gain_scale=s->minimum_gain_scale=1.;
    s->last_limited_mask=s->last_blocked_mask=0;
}

int scm_online_init(scm_online *s,const scm_online_config *c)
{
    scm_online_config configuration;
    if(!s||!scm_online_config_valid(c))return SCM_ONLINE_ERR_ARGUMENT;
    configuration=*c;memset(s,0,sizeof(*s));s->config=configuration;s->initialized=1;
    public_belief(s);return SCM_ONLINE_OK;
}

int scm_online_validate(const scm_online *s)
{
    int i,j;
    const unsigned allowed=SCM_ONLINE_FLAG_HISTORY_LOST|SCM_ONLINE_FLAG_RECOVERY_REQUIRED|
        SCM_ONLINE_FLAG_MODEL_UNAVAILABLE|SCM_ONLINE_FLAG_MISSING_VOLTAGE|
        SCM_ONLINE_FLAG_UPDATE_REJECTED|SCM_ONLINE_FLAG_GAIN_LIMITED;
    if(!s||s->initialized!=1||!scm_online_config_valid(&s->config)||s->flags&~allowed||s->excitation>3||
       s->epoch_begin>s->next_index||s->evidence_next_index<s->epoch_begin||s->evidence_next_index>s->next_index||
       s->prediction_count!=s->next_index||s->voltage_count>s->prediction_count||
       s->missing_voltage_count!=s->prediction_count-s->voltage_count||
       s->rejected_voltage_count>s->voltage_count||s->limited_gain_count>s->voltage_count||
       s->zero_gain_count>s->voltage_count||s->has_voltage<0||s->has_voltage>1||
       s->prediction_valid<0||s->prediction_valid>1)return SCM_ONLINE_ERR_STATE;
    if((s->cold_resets!=0)!=((s->flags&SCM_ONLINE_FLAG_HISTORY_LOST)!=0)||
       (!s->has_voltage&&s->evidence_next_index!=s->epoch_begin)||
       (s->has_voltage&&s->evidence_next_index==s->epoch_begin)||
       ((s->flags&SCM_ONLINE_FLAG_MODEL_UNAVAILABLE)&&
        (!(s->flags&SCM_ONLINE_FLAG_RECOVERY_REQUIRED)||s->prediction_valid)))return SCM_ONLINE_ERR_STATE;
    if(!isfinite(s->elapsed_s)||s->elapsed_s<0||!isfinite(s->epoch_elapsed_s)||
       s->epoch_elapsed_s<0||s->epoch_elapsed_s>s->elapsed_s||
       !isfinite(s->last_current_A)||fabs(s->last_current_A)>s->config.max_abs_current_A||
       !isfinite(s->last_prediction_V)||!isfinite(s->last_innovation_V)||
       !isfinite(s->last_innovation_variance_V2)||s->last_innovation_variance_V2<0||
       !isfinite(s->last_gain_scale)||s->last_gain_scale<0||s->last_gain_scale>1||
       !isfinite(s->last_max_gain_scale)||s->last_max_gain_scale<s->last_gain_scale||s->last_max_gain_scale>1||
       !isfinite(s->minimum_gain_scale)||s->minimum_gain_scale<0||s->minimum_gain_scale>1||
       !isfinite(s->innovation_ewma)||s->innovation_ewma<0||s->innovation_ewma>1e12)return SCM_ONLINE_ERR_STATE;
    if((s->last_limited_mask|s->last_blocked_mask)&~((1u<<D)-1u)||
       (s->last_blocked_mask&~s->last_limited_mask))return SCM_ONLINE_ERR_STATE;
    for(i=0;i<D;i++)if(!isfinite(s->mean[i])||s->mean[i]<lower[i]||s->mean[i]>upper[i])return SCM_ONLINE_ERR_STATE;
    for(i=0;i<D;i++)for(j=0;j<D;j++)if(!isfinite(s->factor[AT(i,j)])||
        (j>i&&s->factor[AT(i,j)]!=0)||(i==j&&s->factor[AT(i,j)]<0))return SCM_ONLINE_ERR_STATE;
    return SCM_ONLINE_OK;
}

static int predict(const scm_online *old,scm_online *next,double dt,double current)
{
    int i,j,k;double q,a,om,derivative,derivative_R,charge;
    charge=current*dt/(3600.*exp(old->mean[5]));
    next->mean[11]=old->mean[11]-charge;
    for(j=0;j<D;j++)next->factor[AT(11,j)]=old->factor[AT(11,j)]+charge*old->factor[AT(5,j)];
    for(i=0;i<3;i++) {
        k=12+i;q=dt/exp(old->mean[i]);a=exp(-q);om=-expm1(-q);
        derivative=q*a*(old->mean[k]-old->mean[7+i]*current);derivative_R=om*current;
        next->mean[k]=a*old->mean[k]+om*old->mean[7+i]*current;
        for(j=0;j<D;j++)next->factor[AT(k,j)]=a*old->factor[AT(k,j)]+
            derivative*old->factor[AT(i,j)]+derivative_R*old->factor[AT(7+i,j)];
    }
    if(current!=0&&dt!=0) {
        double sign=current>0?1.:-1.;k=current>0?3:4;
        q=exp(old->mean[k])*(fabs(current)/3600.)*dt;a=exp(-q);om=-expm1(-q);
        derivative=-q*a*(old->mean[15]-sign);
        next->mean[15]=a*old->mean[15]+om*sign;
        for(j=0;j<D;j++)next->factor[AT(15,j)]=a*old->factor[AT(15,j)]+derivative*old->factor[AT(k,j)];
    }
    for(i=0;i<D;i++)if(!isfinite(next->mean[i])||next->mean[i]<lower[i]||next->mean[i]>upper[i])return -1;
    for(i=0;i<D*D;i++)if(!isfinite(next->factor[i]))return -1;
    return 0;
}

static int observation(const scm_online *s,double current,double *voltage,double gradient[D])
{
    double u,slope;
    if(scm_ocv_eval(NULL,s->mean[11],&u,&slope))return -1;
    *voltage=u-s->mean[6]*current-s->mean[12]-s->mean[13]-s->mean[14]-s->mean[10]*s->mean[15];
    if(gradient) {
        memset(gradient,0,D*sizeof(double));gradient[6]=-current;gradient[10]=-s->mean[15];
        gradient[11]=slope;gradient[12]=gradient[13]=gradient[14]=-1.;gradient[15]=-s->mean[10];
    }
    return isfinite(*voltage)?0:-1;
}

/* Right orthogonal rotations of [[sigma,h^T L],[0,L]], in descending column
 * order, produce [[sd,0],[g,Lopt]] without a second matrix. Descending order
 * preserves lower shape because the accumulated noise column is zero above
 * the current pivot. For the chosen normalized gain t, Joseph covariance is
 * Lopt*Lopt^T+(g-t)*(g-t)^T. An ascending appended-column rotation pass restores
 * a lower factor. No subtraction of covariance matrices, rank threshold,
 * variance floor, process noise, forgetting, or observation re-use is added.
 * s is a disposable candidate; predicted is the committed valid prediction. */

void fixture_capture_reset(boundary_capture *capture)
{
    if(!capture)return;
    memset(capture,0,sizeof(*capture));
    capture->coordinate=capture->column=capture->boundary_coordinate=-1;
}

static int fixture_capture_fail(boundary_capture *capture,int stage,int coordinate,int column)
{
    if(capture) {
        capture->stage=stage;capture->coordinate=coordinate;capture->column=column;
    }
    return -1;
}

static void fixture_record_boundary(boundary_capture *capture,int coordinate,
    double mean,double gain,double standard,double change,double scale,double selected,double proposed)
{
    if(!capture)return;
    capture->boundary_coordinate=coordinate;capture->mean_before=mean;
    capture->raw_gain=gain;capture->standard=standard;capture->raw_change=change;
    capture->scale=scale;capture->selected_gain=selected;capture->proposed_mean=proposed;
}

static int correct(const scm_online *predicted,scm_online *s,double voltage,scm_online_workspace *w,boundary_capture *capture)
{
    int i,j,active=0,any_gain=0;unsigned limited=0,blocked=0;
    double prediction,innovation,sd,standard,minimum=1.,maximum=0.;
    if(observation(s,s->last_current_A,&prediction,w->observation_gradient))return fixture_capture_fail(capture,BOUNDARY_STAGE_OBSERVATION,-1,-1);
    innovation=voltage-prediction;if(!isfinite(innovation))return fixture_capture_fail(capture,BOUNDARY_STAGE_INNOVATION,-1,-1);
    for(j=0;j<D;j++) {
        double value=0;
        for(i=j;i<D;i++)value+=s->factor[AT(i,j)]*w->observation_gradient[i];
        if(!isfinite(value))return fixture_capture_fail(capture,BOUNDARY_STAGE_PROJECTION,-1,j);
        w->projected_gradient[j]=value;w->covariance_gradient[j]=0.;
    }
    sd=s->config.sigma_V;
    for(j=D-1;j>=0;j--) {
        double r=hypot(sd,w->projected_gradient[j]),c,rotation;
        if(!isfinite(r)||r<=0||r>sqrt(DBL_MAX))return fixture_capture_fail(capture,BOUNDARY_STAGE_INNOVATION_SD,-1,j);
        c=sd/r;rotation=w->projected_gradient[j]/r;sd=r;
        for(i=j;i<D;i++) {
            double x=w->covariance_gradient[i],y=s->factor[AT(i,j)];
            double gain=c*x+rotation*y,factor=-rotation*x+c*y;
            if(!isfinite(gain)||!isfinite(factor))return fixture_capture_fail(capture,BOUNDARY_STAGE_OPTIMAL_ROTATION,i,j);
            w->covariance_gradient[i]=gain;s->factor[AT(i,j)]=factor;
        }
    }
    standard=innovation/sd;if(!isfinite(standard))return fixture_capture_fail(capture,BOUNDARY_STAGE_STANDARD,-1,-1);
    for(i=0;i<D;i++) {
        double gain=w->covariance_gradient[i],change=gain*standard,lambda=1.,limit,t,value;
        if(!isfinite(change))return fixture_capture_fail(capture,BOUNDARY_STAGE_RAW_CHANGE,i,-1);
        if(change>0){limit=(upper[i]-s->mean[i])/change;if(limit<lambda)lambda=limit;}
        else if(change<0){limit=(lower[i]-s->mean[i])/change;if(limit<lambda)lambda=limit;}
        lambda=fmax(0.,fmin(1.,lambda));if(lambda<1.)lambda*=1.-1e-9;
        t=lambda*gain;w->correction[i]=t;
        if(gain!=0) {
            active=1;minimum=fmin(minimum,lambda);maximum=fmax(maximum,lambda);
            if(lambda<1.)limited|=1u<<i;
            if(t==0)blocked|=1u<<i;
        }
        if(t!=0)any_gain=1;
        value=s->mean[i]+t*standard;
        if(i==9||!isfinite(value)||value<lower[i]||value>upper[i])
            fixture_record_boundary(capture,i,s->mean[i],gain,standard,change,lambda,t,value);
        if(!isfinite(value)||value<lower[i]||value>upper[i])
            return fixture_capture_fail(capture,BOUNDARY_STAGE_MEAN_DOMAIN,i,-1);
        if(t!=0&&standard!=0)s->mean[i]=value;
    }
    if(!active)maximum=1.;
    if(!any_gain) {
        memcpy(s->mean,predicted->mean,sizeof(s->mean));
        memcpy(s->factor,predicted->factor,sizeof(s->factor));
    } else {
        for(i=0;i<D;i++)w->covariance_gradient[i]-=w->correction[i];
        for(j=0;j<D;j++) {
            double r,c,rotation;
            if(w->covariance_gradient[j]==0)continue; /* Includes a zero pivot. */
            r=hypot(s->factor[AT(j,j)],w->covariance_gradient[j]);
            if(!isfinite(r)||r<=0)return fixture_capture_fail(capture,BOUNDARY_STAGE_JOSEPH_SD,j,j);
            c=s->factor[AT(j,j)]/r;rotation=w->covariance_gradient[j]/r;
            s->factor[AT(j,j)]=r;w->covariance_gradient[j]=0.;
            for(i=j+1;i<D;i++) {
                double x=s->factor[AT(i,j)],y=w->covariance_gradient[i];
                double factor=c*x+rotation*y,remainder=-rotation*x+c*y;
                if(!isfinite(factor)||!isfinite(remainder))return fixture_capture_fail(capture,BOUNDARY_STAGE_JOSEPH_ROTATION,i,j);
                s->factor[AT(i,j)]=factor;w->covariance_gradient[i]=remainder;
            }
        }
    }
    s->last_innovation_V=innovation;s->last_innovation_variance_V2=sd*sd;
    s->last_gain_scale=minimum;s->last_max_gain_scale=maximum;
    s->last_limited_mask=limited;s->last_blocked_mask=blocked;
    if(minimum<s->minimum_gain_scale)s->minimum_gain_scale=minimum;
    if(limited){s->limited_gain_count++;s->flags|=SCM_ONLINE_FLAG_GAIN_LIMITED;}
    if(!any_gain)s->zero_gain_count++;
    else {s->has_voltage=1;s->evidence_next_index=s->next_index;}
    {
        double clipped=fmin(fabs(standard),1e6),nis=clipped*clipped;
        s->innovation_ewma+=(nis-s->innovation_ewma)/1024.;
    }
    /* The query voltage is evaluated at the corrected current point. The
     * innovation above remains the pre-correction innovation. */
    if(observation(s,s->last_current_A,&s->last_prediction_V,NULL))return fixture_capture_fail(capture,BOUNDARY_STAGE_FINAL_OBSERVATION,-1,-1);
    if(scm_online_validate(s))return fixture_capture_fail(capture,BOUNDARY_STAGE_VALIDATION,-1,-1);
    return 0;
}

int fixture_ingest(scm_online *s,const unsigned char id[SCM_ONLINE_SOURCE_BYTES],
    uint64_t index,const scm_sample *input,int voltage_present,scm_online_workspace *w,boundary_capture *capture)
{
    scm_online *next;double elapsed,epoch_elapsed;int failed;
    fixture_capture_reset(capture);
    if(!s||!id||!input||!w||(voltage_present!=0&&voltage_present!=1))return SCM_ONLINE_ERR_ARGUMENT;
    if(scm_online_validate(s))return SCM_ONLINE_ERR_STATE;
    if(memcmp(id,s->config.source_id,SCM_ONLINE_SOURCE_BYTES))return SCM_ONLINE_ERR_SOURCE;
    if(index!=s->next_index)return SCM_ONLINE_ERR_ORDER;
    if(s->flags&SCM_ONLINE_FLAG_RECOVERY_REQUIRED)return SCM_ONLINE_ERR_RECOVERY_REQUIRED;
    if(!isfinite(input->dt)||!isfinite(input->current)||(voltage_present&&!isfinite(input->voltage)))return SCM_ONLINE_ERR_NONFINITE;
    if(input->dt<0||input->dt>s->config.max_dt_s||fabs(input->current)>s->config.max_abs_current_A)return SCM_ONLINE_ERR_DOMAIN;
    if(index==UINT64_MAX||s->prediction_count==UINT64_MAX||
       (voltage_present&&(s->voltage_count==UINT64_MAX||s->rejected_voltage_count==UINT64_MAX||
        s->limited_gain_count==UINT64_MAX||s->zero_gain_count==UINT64_MAX))||
       (!voltage_present&&s->missing_voltage_count==UINT64_MAX))return SCM_ONLINE_ERR_OVERFLOW;
    elapsed=s->elapsed_s+input->dt;epoch_elapsed=s->epoch_elapsed_s+input->dt;
    if(!isfinite(elapsed)||!isfinite(epoch_elapsed)||
       (input->dt>0&&(elapsed==s->elapsed_s||epoch_elapsed==s->epoch_elapsed_s)))return SCM_ONLINE_ERR_OVERFLOW;
    next=&w->candidate;*next=*s;
    failed=predict(s,next,input->dt,input->current);
    if(!failed)failed=observation(next,input->current,&next->last_prediction_V,NULL);
    if(failed)*next=*s; /* Retain old valid belief; its current-state claim ends. */
    next->next_index++;next->prediction_count++;next->elapsed_s=elapsed;next->epoch_elapsed_s=epoch_elapsed;
    next->last_current_A=input->current;
    next->flags&=~(SCM_ONLINE_FLAG_MISSING_VOLTAGE|SCM_ONLINE_FLAG_UPDATE_REJECTED|SCM_ONLINE_FLAG_GAIN_LIMITED);
    if(voltage_present)next->voltage_count++;
    else {next->missing_voltage_count++;next->flags|=SCM_ONLINE_FLAG_MISSING_VOLTAGE;}
    if(input->dt>0&&input->current>0)next->excitation|=1u;
    if(input->dt>0&&input->current<0)next->excitation|=2u;
    if(failed) {
        next->flags|=SCM_ONLINE_FLAG_RECOVERY_REQUIRED|SCM_ONLINE_FLAG_MODEL_UNAVAILABLE;
        next->prediction_valid=0;
        if(voltage_present){next->rejected_voltage_count++;next->flags|=SCM_ONLINE_FLAG_UPDATE_REJECTED;}
        *s=*next;return SCM_ONLINE_ACCEPTED_RECOVERY;
    }
    next->prediction_valid=1;
    *s=*next; /* The disposable correction cannot overwrite this prediction. */
    if(voltage_present) {
        if(correct(s,next,input->voltage,w,capture)) {
            s->rejected_voltage_count++;s->flags|=SCM_ONLINE_FLAG_UPDATE_REJECTED;
        } else *s=*next;
    }
    return SCM_ONLINE_OK;
}

const char *scm_online_status_name(scm_online_status status)
{
    switch(status) {
        case SCM_ONLINE_UNEXCITED:return "unexcited";
        case SCM_ONLINE_UNRESOLVED:return "unresolved";
        case SCM_ONLINE_PROVISIONAL:return "provisional";
        default:return "unknown";
    }
}

int scm_online_query(const scm_online *s,scm_online_query_result *out)
{
    int i,j;double q,sdz,sdq,relative;int ranges;
    if(!out||scm_online_validate(s))return SCM_ONLINE_ERR_ARGUMENT;
    memset(out,0,sizeof(*out));out->flags=s->flags;out->excitation=s->excitation;
#define COPY(field) out->field=s->field
    COPY(epoch_begin);COPY(next_index);COPY(evidence_next_index);COPY(prediction_count);COPY(voltage_count);
    COPY(missing_voltage_count);COPY(rejected_voltage_count);COPY(limited_gain_count);COPY(zero_gain_count);COPY(cold_resets);
    COPY(elapsed_s);COPY(epoch_elapsed_s);COPY(last_innovation_V);COPY(last_innovation_variance_V2);
    COPY(last_gain_scale);COPY(last_max_gain_scale);COPY(minimum_gain_scale);COPY(innovation_ewma);
    COPY(last_limited_mask);COPY(last_blocked_mask);
#undef COPY
    out->evidence_age_samples=s->next_index-s->evidence_next_index;
    out->state_bytes=sizeof(*s);out->workspace_bytes=sizeof(scm_online_workspace);
    memcpy(out->mean,s->mean,sizeof(out->mean));
    for(i=0;i<D;i++)for(j=0;j<D;j++)out->coordinate_sd[i]=hypot(out->coordinate_sd[i],s->factor[AT(i,j)]);
    if(!s->has_voltage||(s->flags&SCM_ONLINE_FLAG_RECOVERY_REQUIRED))return SCM_ONLINE_OK;
    out->point_available=1;out->capacity_available=s->excitation!=0;
    out->prediction_available=s->prediction_valid;out->current_soc=s->mean[11];
    q=exp(s->mean[5]);out->capacity_Ah=q;out->predicted_voltage_V=s->last_prediction_V;
    sdz=out->coordinate_sd[11];sdq=out->coordinate_sd[5];
    out->soc_local_lower=s->mean[11]-2*sdz;out->soc_local_upper=s->mean[11]+2*sdz;
    out->capacity_local_lower_Ah=exp(s->mean[5]-2*sdq);out->capacity_local_upper_Ah=exp(s->mean[5]+2*sdq);
    ranges=isfinite(out->soc_local_lower)&&isfinite(out->soc_local_upper)&&
        isfinite(out->capacity_local_lower_Ah)&&isfinite(out->capacity_local_upper_Ah);
    if(!ranges){out->soc_local_lower=out->soc_local_upper=out->capacity_local_lower_Ah=out->capacity_local_upper_Ah=0;}
    out->local_ranges_available=ranges;
    relative=ranges?fmax(q-out->capacity_local_lower_Ah,out->capacity_local_upper_Ah-q)/q:INFINITY;
    out->soc_local_precision_hard=ranges&&2*sdz<=.10;out->soc_local_precision_preferred=ranges&&2*sdz<=.005;
    out->capacity_local_precision_hard=ranges&&relative<=.05;out->capacity_local_precision_preferred=ranges&&relative<=.005;
    out->soc_status=ranges&&out->soc_local_precision_hard&&out->soc_local_lower>=0&&out->soc_local_upper<=1?
        SCM_ONLINE_PROVISIONAL:SCM_ONLINE_UNRESOLVED;
    out->capacity_status=!s->excitation?SCM_ONLINE_UNEXCITED:
        ranges&&out->capacity_local_precision_hard&&out->capacity_local_lower_Ah>=.03&&out->capacity_local_upper_Ah<=.10?
        SCM_ONLINE_PROVISIONAL:SCM_ONLINE_UNRESOLVED;
    return SCM_ONLINE_OK;
}

int scm_online_mark_unknown_gap(scm_online *s)
{
    if(scm_online_validate(s))return SCM_ONLINE_ERR_STATE;
    s->flags|=SCM_ONLINE_FLAG_RECOVERY_REQUIRED;return SCM_ONLINE_ERR_RECOVERY_REQUIRED;
}

int scm_online_cold_reset(scm_online *s)
{
    if(scm_online_validate(s))return SCM_ONLINE_ERR_STATE;
    if(s->cold_resets==UINT64_MAX)return SCM_ONLINE_ERR_OVERFLOW;
    s->epoch_begin=s->next_index;s->evidence_next_index=s->next_index;s->epoch_elapsed_s=0;
    s->cold_resets++;s->flags=SCM_ONLINE_FLAG_HISTORY_LOST;public_belief(s);
    return SCM_ONLINE_OK;
}

int fixture_select(scm_online *s,scm_online_workspace *w,double standard,boundary_capture *capture)
{
    int i,active=0,any_gain=0;unsigned limited=0,blocked=0;
    double minimum=1.,maximum=0.;
    fixture_capture_reset(capture);
    for(i=0;i<D;i++) {
        double gain=w->covariance_gradient[i],change=gain*standard,lambda=1.,limit,t,value;
        if(!isfinite(change))return fixture_capture_fail(capture,BOUNDARY_STAGE_RAW_CHANGE,i,-1);
        if(change>0){limit=(upper[i]-s->mean[i])/change;if(limit<lambda)lambda=limit;}
        else if(change<0){limit=(lower[i]-s->mean[i])/change;if(limit<lambda)lambda=limit;}
        lambda=fmax(0.,fmin(1.,lambda));if(lambda<1.)lambda*=1.-1e-9;
        t=lambda*gain;w->correction[i]=t;
        if(gain!=0) {
            active=1;minimum=fmin(minimum,lambda);maximum=fmax(maximum,lambda);
            if(lambda<1.)limited|=1u<<i;
            if(t==0)blocked|=1u<<i;
        }
        if(t!=0)any_gain=1;
        value=s->mean[i]+t*standard;
        if(i==9||!isfinite(value)||value<lower[i]||value>upper[i])
            fixture_record_boundary(capture,i,s->mean[i],gain,standard,change,lambda,t,value);
        if(!isfinite(value)||value<lower[i]||value>upper[i])
            return fixture_capture_fail(capture,BOUNDARY_STAGE_MEAN_DOMAIN,i,-1);
        if(t!=0&&standard!=0)s->mean[i]=value;
    }
    if(!active)maximum=1.;
    s->last_gain_scale=minimum;s->last_max_gain_scale=maximum;
    s->last_limited_mask=limited;s->last_blocked_mask=blocked;
    (void)any_gain;
    return 0;
}
