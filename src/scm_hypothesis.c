#include "scm_hypothesis.h"
#include <float.h>
#include <math.h>
#include <string.h>

#define D SCM_ONLINE_DIM
#define AT(i,j) SCM_HYPOTHESIS_FACTOR_INDEX(i,j)
#define N SCM_HYPOTHESIS_FACTOR_ENTRIES

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

void scm_hypothesis_bounds(double lo[D],double hi[D])
{
    if(lo)memcpy(lo,lower,sizeof(lower));
    if(hi)memcpy(hi,upper,sizeof(upper));
}

void scm_hypothesis_config_default(scm_hypothesis_config *c)
{
    if(!c)return;
    memset(c,0,sizeof(*c));c->sigma_V=.001;c->max_dt_s=1.;c->max_abs_current_A=.25;
}

int scm_hypothesis_config_valid(const scm_hypothesis_config *c)
{
    return c && isfinite(c->sigma_V) && c->sigma_V>=1e-12 && c->sigma_V<=1. &&
        isfinite(c->max_dt_s) && c->max_dt_s>0 && c->max_dt_s<=1. &&
        isfinite(c->max_abs_current_A) && c->max_abs_current_A>0 && c->max_abs_current_A<=.25;
}

int scm_hypothesis_config_equal(const scm_hypothesis_config *a,const scm_hypothesis_config *b)
{
    return scm_hypothesis_config_valid(a)&&scm_hypothesis_config_valid(b)&&
        !memcmp(a->source_id,b->source_id,SCM_ONLINE_SOURCE_BYTES)&&
        a->sigma_V==b->sigma_V&&a->max_dt_s==b->max_dt_s&&a->max_abs_current_A==b->max_abs_current_A;
}

static void public_belief(scm_hypothesis_component *s)
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

static int component_init(scm_hypothesis_component *s,const scm_hypothesis_config *c)
{
    scm_hypothesis_config configuration;
    if(!s||!scm_hypothesis_config_valid(c))return SCM_ONLINE_ERR_ARGUMENT;
    configuration=*c;memset(s,0,sizeof(*s));s->config=configuration;s->initialized=1;
    public_belief(s);return SCM_ONLINE_OK;
}

int scm_hypothesis_component_validate(const scm_hypothesis_component *s)
{
    int i,j;
    const unsigned allowed=SCM_ONLINE_FLAG_HISTORY_LOST|SCM_ONLINE_FLAG_RECOVERY_REQUIRED|
        SCM_ONLINE_FLAG_MODEL_UNAVAILABLE|SCM_ONLINE_FLAG_MISSING_VOLTAGE|
        SCM_ONLINE_FLAG_UPDATE_REJECTED|SCM_ONLINE_FLAG_GAIN_LIMITED;
    if(!s||s->initialized!=1||!scm_hypothesis_config_valid(&s->config)||s->flags&~allowed||s->excitation>3||
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
    for(i=0;i<D;i++)for(j=0;j<=i;j++)if(!isfinite(s->factor[AT(i,j)])||
        (i==j&&s->factor[AT(i,j)]<0))return SCM_ONLINE_ERR_STATE;
    return SCM_ONLINE_OK;
}

static int normalized_weights(const double logw[2])
{
    double m,total;
    if(!isfinite(logw[0])||!isfinite(logw[1])||logw[0]>0||logw[1]>0)return 0;
    m=fmax(logw[0],logw[1]);
    total=m+log(exp(logw[0]-m)+exp(logw[1]-m));
    /* Rounded normalization check only; no clipping or inference floor. */
    return isfinite(total)&&fabs(total)<=32.*DBL_EPSILON;
}

int scm_hypothesis_validate(const scm_hypothesis *s)
{
    const scm_hypothesis_component *a,*b;
    unsigned common_flags=SCM_ONLINE_FLAG_HISTORY_LOST|SCM_ONLINE_FLAG_RECOVERY_REQUIRED|
        SCM_ONLINE_FLAG_MODEL_UNAVAILABLE|SCM_ONLINE_FLAG_MISSING_VOLTAGE|SCM_ONLINE_FLAG_UPDATE_REJECTED;
    if(!s||s->header.active_components!=SCM_HYPOTHESIS_COMPONENTS||
       s->header.flags&~(SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT|SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE)||
       s->header.last_rejection_stage>SCM_HYPOTHESIS_REJECT_REGENERATION||
       (s->header.last_rejection_component!=SCM_HYPOTHESIS_NO_COMPONENT&&
        s->header.last_rejection_component>=SCM_HYPOTHESIS_COMPONENTS)||
       !normalized_weights(s->log_weight))return SCM_ONLINE_ERR_STATE;
    a=&s->component[0];b=&s->component[1];
    if(scm_hypothesis_component_validate(a)||scm_hypothesis_component_validate(b)||
       !scm_hypothesis_config_equal(&a->config,&b->config))return SCM_ONLINE_ERR_STATE;
#define SAME(field) if(a->field!=b->field)return SCM_ONLINE_ERR_STATE
    SAME(epoch_begin);SAME(next_index);SAME(prediction_count);SAME(voltage_count);
    SAME(missing_voltage_count);SAME(rejected_voltage_count);SAME(cold_resets);
    SAME(elapsed_s);SAME(epoch_elapsed_s);SAME(last_current_A);SAME(excitation);SAME(prediction_valid);
#undef SAME
    if((a->flags&common_flags)!=(b->flags&common_flags)||
       s->header.generation<a->next_index||
       s->header.bank_evidence_next_index<a->epoch_begin||
       s->header.bank_evidence_next_index>a->next_index||
       a->evidence_next_index>s->header.bank_evidence_next_index||
       b->evidence_next_index>s->header.bank_evidence_next_index)return SCM_ONLINE_ERR_STATE;
    if(s->header.flags&SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE) {
        if(s->header.bank_evidence_next_index==a->epoch_begin)return SCM_ONLINE_ERR_STATE;
    } else if(s->header.bank_evidence_next_index!=a->epoch_begin||a->has_voltage||b->has_voltage)
        return SCM_ONLINE_ERR_STATE;
    if(s->header.last_rejection_stage==SCM_HYPOTHESIS_REJECT_NONE) {
        if(s->header.last_rejection_component!=SCM_HYPOTHESIS_NO_COMPONENT||
           (a->flags&SCM_ONLINE_FLAG_UPDATE_REJECTED))return SCM_ONLINE_ERR_STATE;
    } else if(!(a->flags&(SCM_ONLINE_FLAG_UPDATE_REJECTED|SCM_ONLINE_FLAG_RECOVERY_REQUIRED)))
        return SCM_ONLINE_ERR_STATE;
    return SCM_ONLINE_OK;
}

static void split_component(scm_hypothesis_component *s,unsigned component)
{
    const double alpha=0.7978845608028654,beta=0.6028102749890869;
    double sigma=s->factor[AT(5,5)];
    s->mean[5]+=(component?1.:-1.)*alpha*sigma;
    s->factor[AT(5,5)]=sigma*beta;
}

int scm_hypothesis_init(scm_hypothesis *s,const scm_hypothesis_config *c,scm_hypothesis_mode mode)
{
    scm_hypothesis_config configuration;unsigned j;
    if(!s||!scm_hypothesis_config_valid(c)||
       (mode!=SCM_HYPOTHESIS_COINCIDENT&&mode!=SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT))return SCM_ONLINE_ERR_ARGUMENT;
    configuration=*c;memset(s,0,sizeof(*s));
    s->header.active_components=SCM_HYPOTHESIS_COMPONENTS;
    s->header.last_rejection_component=SCM_HYPOTHESIS_NO_COMPONENT;
    if(mode==SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT)s->header.flags|=SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        component_init(&s->component[j],&configuration);
        if(mode==SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT)split_component(&s->component[j],j);
        s->log_weight[j]=-0.69314718055994530942;
    }
    return scm_hypothesis_validate(s);
}

static double factor_at(const scm_hypothesis_component *s,int i,int j)
{return j<=i?s->factor[AT(i,j)]:0.;}

/* Copy first, then transform only physical rows. Implicit upper entries enter
 * the same sums as exact numeric zero. No diagonal approximation is made. */
static int predict(const scm_hypothesis_component *old,scm_hypothesis_component *next,double dt,double current)
{
    int i,j,k;double q,a,om,derivative,derivative_R,charge;
    charge=current*dt/(3600.*exp(old->mean[5]));
    next->mean[11]=old->mean[11]-charge;
    for(j=0;j<=11;j++)next->factor[AT(11,j)]=factor_at(old,11,j)+charge*factor_at(old,5,j);
    for(i=0;i<3;i++) {
        k=12+i;q=dt/exp(old->mean[i]);a=exp(-q);om=-expm1(-q);
        derivative=q*a*(old->mean[k]-old->mean[7+i]*current);derivative_R=om*current;
        next->mean[k]=a*old->mean[k]+om*old->mean[7+i]*current;
        for(j=0;j<=k;j++)next->factor[AT(k,j)]=a*factor_at(old,k,j)+
            derivative*factor_at(old,i,j)+derivative_R*factor_at(old,7+i,j);
    }
    if(current!=0&&dt!=0) {
        double sign=current>0?1.:-1.;k=current>0?3:4;
        q=exp(old->mean[k])*(fabs(current)/3600.)*dt;a=exp(-q);om=-expm1(-q);
        derivative=-q*a*(old->mean[15]-sign);
        next->mean[15]=a*old->mean[15]+om*sign;
        for(j=0;j<D;j++)next->factor[AT(15,j)]=a*factor_at(old,15,j)+derivative*factor_at(old,k,j);
    }
    for(i=0;i<D;i++)if(!isfinite(next->mean[i])||next->mean[i]<lower[i]||next->mean[i]>upper[i])return -1;
    for(i=0;i<(int)N;i++)if(!isfinite(next->factor[i]))return -1;
    return 0;
}

static int observation(const scm_hypothesis_component *s,double current,double *voltage,double gradient[D])
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

static int regenerate_numeric(const scm_hypothesis_component *old,scm_hypothesis_component *next,
    const scm_sample *input)
{
    /* Metadata survives this restoration; both numeric arrays must be copied
     * before re-predicting, because correction has rotated the factor. */
    memcpy(next->mean,old->mean,sizeof(next->mean));
    memcpy(next->factor,old->factor,sizeof(next->factor));
    return predict(old,next,input->dt,input->current);
}

/* Full Joseph identity: Lopt*Lopt^T+(g-t)*(g-t)^T. The selected normalized
 * gain t is shared by this covariance and the actual rounded mean update. */
static uint32_t correct(const scm_hypothesis_component *old,scm_hypothesis_component *s,
    const scm_sample *input,scm_hypothesis_workspace *w,unsigned component,int *used_gain)
{
    int i,j,active=0,any_gain=0;unsigned limited=0,blocked=0;
    double prediction,innovation,sd,standard,minimum=1.,maximum=0.,score;
    if(observation(s,s->last_current_A,&prediction,w->observation_gradient))return SCM_HYPOTHESIS_REJECT_OBSERVATION;
    innovation=input->voltage-prediction;if(!isfinite(innovation))return SCM_HYPOTHESIS_REJECT_OBSERVATION;
    for(j=0;j<D;j++) {
        double value=0;
        for(i=j;i<D;i++)value+=s->factor[AT(i,j)]*w->observation_gradient[i];
        if(!isfinite(value))return SCM_HYPOTHESIS_REJECT_PROJECTION;
        w->projected_gradient[j]=value;w->covariance_gradient[j]=0.;
    }
    sd=s->config.sigma_V;
    for(j=D-1;j>=0;j--) {
        double r=hypot(sd,w->projected_gradient[j]),c,rotation;
        if(!isfinite(r)||r<=0||r>sqrt(DBL_MAX))return SCM_HYPOTHESIS_REJECT_INNOVATION_SD;
        c=sd/r;rotation=w->projected_gradient[j]/r;sd=r;
        for(i=j;i<D;i++) {
            double x=w->covariance_gradient[i],y=s->factor[AT(i,j)];
            double gain=c*x+rotation*y,factor=-rotation*x+c*y;
            if(!isfinite(gain)||!isfinite(factor))return SCM_HYPOTHESIS_REJECT_COVARIANCE;
            w->covariance_gradient[i]=gain;s->factor[AT(i,j)]=factor;
        }
    }
    standard=innovation/sd;if(!isfinite(standard))return SCM_HYPOTHESIS_REJECT_LIKELIHOOD;
    score=-log(sd)-(0.5*standard)*standard;
    if(!isfinite(score))return SCM_HYPOTHESIS_REJECT_LIKELIHOOD;
    w->pre_correction_log_likelihood[component]=score;
    for(i=0;i<D;i++) {
        double gain=w->covariance_gradient[i],change=gain*standard,lambda=1.,limit,t,value;
        if(!isfinite(change))return SCM_HYPOTHESIS_REJECT_GAIN;
        if(change>0){limit=(upper[i]-s->mean[i])/change;if(limit<lambda)lambda=limit;}
        else if(change<0){limit=(lower[i]-s->mean[i])/change;if(limit<lambda)lambda=limit;}
        lambda=fmax(0.,fmin(1.,lambda));if(lambda<1.)lambda*=1.-1e-9;
        t=lambda*gain;value=s->mean[i]+t*standard;
        if(!isfinite(t)||!isfinite(value))return SCM_HYPOTHESIS_REJECT_MEAN;
        if(value<lower[i]||value>upper[i]){t=0.;lambda=0.;value=s->mean[i];}
        w->correction[i]=t;
        if(gain!=0) {
            active=1;minimum=fmin(minimum,lambda);maximum=fmax(maximum,lambda);
            if(lambda<1.)limited|=1u<<i;
            if(t==0)blocked|=1u<<i;
        }
        if(t!=0)any_gain=1;
        if(t!=0&&standard!=0)s->mean[i]=value;
    }
    if(!active)maximum=1.;
    if(!any_gain) {
        if(regenerate_numeric(old,s,input))return SCM_HYPOTHESIS_REJECT_REGENERATION;
    } else {
        for(i=0;i<D;i++)w->covariance_gradient[i]-=w->correction[i];
        for(j=0;j<D;j++) {
            double r,c,rotation;
            if(w->covariance_gradient[j]==0)continue;
            r=hypot(s->factor[AT(j,j)],w->covariance_gradient[j]);
            if(!isfinite(r)||r<=0)return SCM_HYPOTHESIS_REJECT_COVARIANCE;
            c=s->factor[AT(j,j)]/r;rotation=w->covariance_gradient[j]/r;
            s->factor[AT(j,j)]=r;w->covariance_gradient[j]=0.;
            for(i=j+1;i<D;i++) {
                double x=s->factor[AT(i,j)],y=w->covariance_gradient[i];
                double factor=c*x+rotation*y,remainder=-rotation*x+c*y;
                if(!isfinite(factor)||!isfinite(remainder))return SCM_HYPOTHESIS_REJECT_COVARIANCE;
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
    if(observation(s,s->last_current_A,&s->last_prediction_V,NULL))return SCM_HYPOTHESIS_REJECT_OBSERVATION;
    if(scm_hypothesis_component_validate(s))return SCM_HYPOTHESIS_REJECT_COMPONENT_VALIDATION;
    *used_gain=any_gain;return SCM_HYPOTHESIS_REJECT_NONE;
}

static void advance_ledger(const scm_hypothesis_component *old,scm_hypothesis_component *next,
    const scm_sample *input,int voltage_present,double elapsed,double epoch_elapsed)
{
    next->next_index=old->next_index+1;next->prediction_count=old->prediction_count+1;
    next->elapsed_s=elapsed;next->epoch_elapsed_s=epoch_elapsed;next->last_current_A=input->current;
    next->flags&=~(SCM_ONLINE_FLAG_MISSING_VOLTAGE|SCM_ONLINE_FLAG_UPDATE_REJECTED|SCM_ONLINE_FLAG_GAIN_LIMITED);
    if(voltage_present)next->voltage_count=old->voltage_count+1;
    else {next->missing_voltage_count=old->missing_voltage_count+1;next->flags|=SCM_ONLINE_FLAG_MISSING_VOLTAGE;}
    if(input->dt>0&&input->current>0)next->excitation|=1u;
    if(input->dt>0&&input->current<0)next->excitation|=2u;
}

static int enter_recovery(scm_hypothesis *s,scm_hypothesis *next,const scm_sample *input,
    int voltage_present,double elapsed,double epoch_elapsed,uint32_t stage,uint32_t component)
{
    unsigned j;
    *next=*s;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        scm_hypothesis_component *n=&next->component[j];
        advance_ledger(&s->component[j],n,input,voltage_present,elapsed,epoch_elapsed);
        n->flags|=SCM_ONLINE_FLAG_RECOVERY_REQUIRED|SCM_ONLINE_FLAG_MODEL_UNAVAILABLE;
        n->prediction_valid=0;
        if(voltage_present){n->rejected_voltage_count++;n->flags|=SCM_ONLINE_FLAG_UPDATE_REJECTED;}
    }
    next->header.generation=s->header.generation+1;
    next->header.last_rejection_stage=stage;next->header.last_rejection_component=component;
    *s=*next;return SCM_ONLINE_ACCEPTED_RECOVERY;
}

/* No score is recomputed during rollback. Predictions and ledgers always
 * derive from immutable old state, not from an already advanced stage. */
static int reject_voltage(scm_hypothesis *s,scm_hypothesis *next,const scm_sample *input,
    double elapsed,double epoch_elapsed,uint32_t stage,uint32_t component)
{
    unsigned j;
    *next=*s;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        scm_hypothesis_component *n=&next->component[j];
        if(predict(&s->component[j],n,input->dt,input->current)||
           observation(n,input->current,&n->last_prediction_V,NULL))
            return enter_recovery(s,next,input,1,elapsed,epoch_elapsed,SCM_HYPOTHESIS_REJECT_REGENERATION,j);
        advance_ledger(&s->component[j],n,input,1,elapsed,epoch_elapsed);
        n->prediction_valid=1;n->rejected_voltage_count++;n->flags|=SCM_ONLINE_FLAG_UPDATE_REJECTED;
    }
    next->header.generation=s->header.generation+1;
    next->header.last_rejection_stage=stage;next->header.last_rejection_component=component;
    if(scm_hypothesis_validate(next))
        return enter_recovery(s,next,input,1,elapsed,epoch_elapsed,SCM_HYPOTHESIS_REJECT_BANK_VALIDATION,SCM_HYPOTHESIS_NO_COMPONENT);
    *s=*next;return SCM_ONLINE_OK;
}

static int update_weights(const scm_hypothesis *old,scm_hypothesis *next,const double score[2])
{
    double a,b,m,u,v,den,score_max;
    /* The common likelihood offset carries no relative evidence. Remove it
     * before adding prior odds, or a huge finite common score can erase the
     * carried odds by rounding (or create an avoidable overflow). Equal
     * scores preserve the old normalized weights byte-for-byte. */
    if(score[0]==score[1]) {
        memcpy(next->log_weight,old->log_weight,sizeof(next->log_weight));
        return 0;
    }
    score_max=fmax(score[0],score[1]);
    u=score[0]-score_max;v=score[1]-score_max;
    if(!isfinite(u)||!isfinite(v))return -1;
    a=old->log_weight[0]+u;b=old->log_weight[1]+v;
    if(!isfinite(a)||!isfinite(b))return -1;
    m=fmax(a,b);u=a-m;v=b-m;
    if(!isfinite(u)||!isfinite(v))return -1;
    den=log1p(exp(fmin(u,v)));
    if(!isfinite(den))return -1;
    next->log_weight[0]=u-den;next->log_weight[1]=v-den;
    return normalized_weights(next->log_weight)?0:-1;
}

int scm_hypothesis_ingest(scm_hypothesis *s,const unsigned char id[SCM_ONLINE_SOURCE_BYTES],
    uint64_t index,const scm_sample *input,int voltage_present,scm_hypothesis_workspace *w)
{
    scm_hypothesis *next;const scm_hypothesis_component *first;
    double elapsed,epoch_elapsed;unsigned j;int any_gain=0;
    if(w)w->pre_correction_log_likelihood[0]=w->pre_correction_log_likelihood[1]=NAN;
    if(!s||!id||!input||!w||(voltage_present!=0&&voltage_present!=1))return SCM_ONLINE_ERR_ARGUMENT;
    if(scm_hypothesis_validate(s))return SCM_ONLINE_ERR_STATE;
    first=&s->component[0];
    if(memcmp(id,first->config.source_id,SCM_ONLINE_SOURCE_BYTES))return SCM_ONLINE_ERR_SOURCE;
    if(index!=first->next_index)return SCM_ONLINE_ERR_ORDER;
    if(first->flags&SCM_ONLINE_FLAG_RECOVERY_REQUIRED)return SCM_ONLINE_ERR_RECOVERY_REQUIRED;
    if(!isfinite(input->dt)||!isfinite(input->current)||(voltage_present&&!isfinite(input->voltage)))return SCM_ONLINE_ERR_NONFINITE;
    if(input->dt<0||input->dt>first->config.max_dt_s||fabs(input->current)>first->config.max_abs_current_A)return SCM_ONLINE_ERR_DOMAIN;
    if(index==UINT64_MAX||s->header.generation==UINT64_MAX)return SCM_ONLINE_ERR_OVERFLOW;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        const scm_hypothesis_component *c=&s->component[j];
        if(c->prediction_count==UINT64_MAX||
           (voltage_present&&(c->voltage_count==UINT64_MAX||c->rejected_voltage_count==UINT64_MAX||
            c->limited_gain_count==UINT64_MAX||c->zero_gain_count==UINT64_MAX))||
           (!voltage_present&&c->missing_voltage_count==UINT64_MAX))return SCM_ONLINE_ERR_OVERFLOW;
    }
    elapsed=first->elapsed_s+input->dt;epoch_elapsed=first->epoch_elapsed_s+input->dt;
    if(!isfinite(elapsed)||!isfinite(epoch_elapsed)||
       (input->dt>0&&(elapsed==first->elapsed_s||epoch_elapsed==first->epoch_elapsed_s)))return SCM_ONLINE_ERR_OVERFLOW;
    next=&w->staged;*next=*s;
    next->header.generation=s->header.generation+1;
    next->header.last_rejection_stage=SCM_HYPOTHESIS_REJECT_NONE;
    next->header.last_rejection_component=SCM_HYPOTHESIS_NO_COMPONENT;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        scm_hypothesis_component *n=&next->component[j];
        if(predict(&s->component[j],n,input->dt,input->current)||
           observation(n,input->current,&n->last_prediction_V,NULL))
            return enter_recovery(s,next,input,voltage_present,elapsed,epoch_elapsed,SCM_HYPOTHESIS_REJECT_PREDICTION,j);
        advance_ledger(&s->component[j],n,input,voltage_present,elapsed,epoch_elapsed);
        n->prediction_valid=1;
    }
    if(voltage_present) {
        for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
            int used=0;
            uint32_t stage=correct(&s->component[j],&next->component[j],input,w,j,&used);
            if(stage)return reject_voltage(s,next,input,elapsed,epoch_elapsed,stage,j);
            any_gain|=used;
        }
        if(update_weights(s,next,w->pre_correction_log_likelihood))
            return reject_voltage(s,next,input,elapsed,epoch_elapsed,SCM_HYPOTHESIS_REJECT_WEIGHTS,SCM_HYPOTHESIS_NO_COMPONENT);
        if(any_gain||
           (w->pre_correction_log_likelihood[0]!=w->pre_correction_log_likelihood[1]&&
            (next->log_weight[0]!=s->log_weight[0]||next->log_weight[1]!=s->log_weight[1]))) {
            next->header.bank_evidence_next_index=index+1;
            next->header.flags|=SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE;
        }
    }
    if(scm_hypothesis_validate(next)) {
        if(voltage_present)return reject_voltage(s,next,input,elapsed,epoch_elapsed,SCM_HYPOTHESIS_REJECT_BANK_VALIDATION,SCM_HYPOTHESIS_NO_COMPONENT);
        return enter_recovery(s,next,input,0,elapsed,epoch_elapsed,SCM_HYPOTHESIS_REJECT_BANK_VALIDATION,SCM_HYPOTHESIS_NO_COMPONENT);
    }
    *s=*next;return SCM_ONLINE_OK;
}

const char *scm_hypothesis_status_name(scm_online_status status)
{
    switch(status) {
        case SCM_ONLINE_UNEXCITED:return "unexcited";
        case SCM_ONLINE_UNRESOLVED:return "unresolved";
        case SCM_ONLINE_PROVISIONAL:return "provisional";
        default:return "unknown";
    }
}

const char *scm_hypothesis_rejection_stage_name(uint32_t stage)
{
    switch(stage) {
        case SCM_HYPOTHESIS_REJECT_NONE:return "none";
        case SCM_HYPOTHESIS_REJECT_PREDICTION:return "prediction";
        case SCM_HYPOTHESIS_REJECT_OBSERVATION:return "observation";
        case SCM_HYPOTHESIS_REJECT_PROJECTION:return "projection";
        case SCM_HYPOTHESIS_REJECT_INNOVATION_SD:return "innovation_sd";
        case SCM_HYPOTHESIS_REJECT_GAIN:return "gain";
        case SCM_HYPOTHESIS_REJECT_MEAN:return "mean";
        case SCM_HYPOTHESIS_REJECT_COVARIANCE:return "covariance";
        case SCM_HYPOTHESIS_REJECT_LIKELIHOOD:return "likelihood";
        case SCM_HYPOTHESIS_REJECT_WEIGHTS:return "weights";
        case SCM_HYPOTHESIS_REJECT_COMPONENT_VALIDATION:return "component_validation";
        case SCM_HYPOTHESIS_REJECT_BANK_VALIDATION:return "bank_validation";
        case SCM_HYPOTHESIS_REJECT_REGENERATION:return "regeneration";
        default:return "invalid";
    }
}

static double coordinate_sd(const scm_hypothesis_component *s,int coordinate)
{
    int j;double sd=0;
    for(j=0;j<=coordinate;j++)sd=hypot(sd,s->factor[AT(coordinate,j)]);
    return sd;
}

static void component_query(const scm_hypothesis_component *s,scm_online_query_result *out)
{
    int i;double q,sdz,sdq,relative;int ranges;
    memset(out,0,sizeof(*out));out->flags=s->flags;out->excitation=s->excitation;
#define COPY(field) out->field=s->field
    COPY(epoch_begin);COPY(next_index);COPY(evidence_next_index);COPY(prediction_count);COPY(voltage_count);
    COPY(missing_voltage_count);COPY(rejected_voltage_count);COPY(limited_gain_count);COPY(zero_gain_count);COPY(cold_resets);
    COPY(elapsed_s);COPY(epoch_elapsed_s);COPY(last_innovation_V);COPY(last_innovation_variance_V2);
    COPY(last_gain_scale);COPY(last_max_gain_scale);COPY(minimum_gain_scale);COPY(innovation_ewma);
    COPY(last_limited_mask);COPY(last_blocked_mask);
#undef COPY
    out->evidence_age_samples=s->next_index-s->evidence_next_index;
    out->state_bytes=sizeof(*s);out->workspace_bytes=sizeof(scm_hypothesis_workspace);
    memcpy(out->mean,s->mean,sizeof(out->mean));
    for(i=0;i<D;i++)out->coordinate_sd[i]=coordinate_sd(s,i);
    if(!s->has_voltage||(s->flags&SCM_ONLINE_FLAG_RECOVERY_REQUIRED))return;
    out->point_available=1;out->capacity_available=s->excitation!=0;
    out->prediction_available=s->prediction_valid;out->current_soc=s->mean[11];
    q=exp(s->mean[5]);out->capacity_Ah=q;out->predicted_voltage_V=s->last_prediction_V;
    sdz=out->coordinate_sd[11];sdq=out->coordinate_sd[5];
    out->soc_local_lower=s->mean[11]-2*sdz;out->soc_local_upper=s->mean[11]+2*sdz;
    out->capacity_local_lower_Ah=exp(s->mean[5]-2*sdq);out->capacity_local_upper_Ah=exp(s->mean[5]+2*sdq);
    ranges=isfinite(out->soc_local_lower)&&isfinite(out->soc_local_upper)&&
        isfinite(out->capacity_local_lower_Ah)&&isfinite(out->capacity_local_upper_Ah);
    if(!ranges)out->soc_local_lower=out->soc_local_upper=out->capacity_local_lower_Ah=out->capacity_local_upper_Ah=0;
    out->local_ranges_available=ranges;
    relative=ranges?fmax(q-out->capacity_local_lower_Ah,out->capacity_local_upper_Ah-q)/q:INFINITY;
    out->soc_local_precision_hard=ranges&&2*sdz<=.10;out->soc_local_precision_preferred=ranges&&2*sdz<=.005;
    out->capacity_local_precision_hard=ranges&&relative<=.05;out->capacity_local_precision_preferred=ranges&&relative<=.005;
    out->soc_status=ranges&&out->soc_local_precision_hard&&out->soc_local_lower>=0&&out->soc_local_upper<=1?
        SCM_ONLINE_PROVISIONAL:SCM_ONLINE_UNRESOLVED;
    out->capacity_status=!s->excitation?SCM_ONLINE_UNEXCITED:
        ranges&&out->capacity_local_precision_hard&&out->capacity_local_lower_Ah>=.03&&out->capacity_local_upper_Ah<=.10?
        SCM_ONLINE_PROVISIONAL:SCM_ONLINE_UNRESOLVED;
}

static void target_hull(const scm_hypothesis *s,double hull[4])
{
    unsigned j;double zl=INFINITY,zu=-INFINITY,ql=INFINITY,qu=-INFINITY;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        const scm_hypothesis_component *c=&s->component[j];
        double dz=2*coordinate_sd(c,11),dq=2*coordinate_sd(c,5);
        double lz=c->mean[11]-dz,uz=c->mean[11]+dz;
        double lq=exp(c->mean[5]-dq),uq=exp(c->mean[5]+dq);
        if(!isfinite(lz)||!isfinite(uz)){zl=-INFINITY;zu=INFINITY;}
        else {zl=fmin(zl,lz);zu=fmax(zu,uz);}
        if(!isfinite(lq)||!isfinite(uq)){ql=-INFINITY;qu=INFINITY;}
        else {ql=fmin(ql,lq);qu=fmax(qu,uq);}
    }
    hull[0]=isfinite(zl)?zl:NAN;hull[1]=isfinite(zu)?zu:NAN;
    hull[2]=isfinite(ql)?ql:NAN;hull[3]=isfinite(qu)?qu:NAN;
}

static double weighted_magnitude(double value,double root_weight,double log_root_weight)
{
    double magnitude=fabs(value);
    if(magnitude==0)return 0.;
    if(root_weight>=DBL_MIN)return root_weight*magnitude;
    /* A linear weight, or even its square root, can underflow although its
     * product with a large finite factor is representable. Combine exponents
     * before exponentiating on this rare query-only path. */
    return exp(log(magnitude)+log_root_weight);
}

static void aggregate_query(const scm_hypothesis *s,scm_hypothesis_aggregate_query *out)
{
    const scm_hypothesis_component *a=&s->component[0],*b=&s->component[1];
    double wa=exp(s->log_weight[0]),wb=exp(s->log_weight[1]),total=wa+wb;
    double ra,rb,logra,logrb,q,sdz,sdq,relative;int i,j,ranges;
    logra=.5*s->log_weight[0]-.5*log(total);
    logrb=.5*s->log_weight[1]-.5*log(total);
    wa/=total;wb/=total;ra=exp(logra);rb=exp(logrb);
    memset(out,0,sizeof(*out));out->flags=a->flags|b->flags;out->excitation=a->excitation;
#define COPY(field) out->field=a->field
    COPY(epoch_begin);COPY(next_index);COPY(prediction_count);COPY(voltage_count);
    COPY(missing_voltage_count);COPY(rejected_voltage_count);COPY(cold_resets);
    COPY(elapsed_s);COPY(epoch_elapsed_s);
#undef COPY
    out->evidence_next_index=s->header.bank_evidence_next_index;
    out->evidence_age_samples=out->next_index-out->evidence_next_index;
    for(i=0;i<D;i++) {
        double sd=0;
        out->mean[i]=wa*a->mean[i]+wb*b->mean[i];
        /* Square-root terms avoid an avoidable intermediate variance
         * overflow. Both within and between component contributions enter. */
        for(j=0;j<=i;j++)sd=hypot(sd,weighted_magnitude(a->factor[AT(i,j)],ra,logra));
        sd=hypot(sd,weighted_magnitude(a->mean[i]-out->mean[i],ra,logra));
        for(j=0;j<=i;j++)sd=hypot(sd,weighted_magnitude(b->factor[AT(i,j)],rb,logrb));
        sd=hypot(sd,weighted_magnitude(b->mean[i]-out->mean[i],rb,logrb));
        out->coordinate_sd[i]=sd;
    }
    out->prediction_available=a->prediction_valid&&b->prediction_valid&&
        !(out->flags&SCM_ONLINE_FLAG_RECOVERY_REQUIRED);
    if(out->prediction_available)out->predicted_voltage_V=wa*a->last_prediction_V+wb*b->last_prediction_V;
    if(!(s->header.flags&SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE)||
       (out->flags&SCM_ONLINE_FLAG_RECOVERY_REQUIRED))return;
    out->point_available=1;out->capacity_available=out->excitation!=0;
    out->current_soc=out->mean[11];q=exp(out->mean[5]);out->capacity_Ah=q;
    sdz=out->coordinate_sd[11];sdq=out->coordinate_sd[5];
    out->soc_local_lower=out->mean[11]-2*sdz;out->soc_local_upper=out->mean[11]+2*sdz;
    out->capacity_local_lower_Ah=exp(out->mean[5]-2*sdq);out->capacity_local_upper_Ah=exp(out->mean[5]+2*sdq);
    ranges=isfinite(out->soc_local_lower)&&isfinite(out->soc_local_upper)&&
        isfinite(out->capacity_local_lower_Ah)&&isfinite(out->capacity_local_upper_Ah);
    if(!ranges)out->soc_local_lower=out->soc_local_upper=out->capacity_local_lower_Ah=out->capacity_local_upper_Ah=0;
    out->local_ranges_available=ranges;
    relative=ranges?fmax(q-out->capacity_local_lower_Ah,out->capacity_local_upper_Ah-q)/q:INFINITY;
    out->soc_local_precision_hard=ranges&&2*sdz<=.10;out->soc_local_precision_preferred=ranges&&2*sdz<=.005;
    out->capacity_local_precision_hard=ranges&&relative<=.05;out->capacity_local_precision_preferred=ranges&&relative<=.005;
    out->soc_status=ranges&&out->soc_local_precision_hard&&out->soc_local_lower>=0&&out->soc_local_upper<=1?
        SCM_ONLINE_PROVISIONAL:SCM_ONLINE_UNRESOLVED;
    out->capacity_status=!out->excitation?SCM_ONLINE_UNEXCITED:
        ranges&&out->capacity_local_precision_hard&&out->capacity_local_lower_Ah>=.03&&out->capacity_local_upper_Ah<=.10?
        SCM_ONLINE_PROVISIONAL:SCM_ONLINE_UNRESOLVED;
}

int scm_hypothesis_query(const scm_hypothesis *s,int selector,scm_hypothesis_query_result *out)
{
    unsigned j;
    if(!out||selector<SCM_HYPOTHESIS_AGGREGATE||selector>=(int)SCM_HYPOTHESIS_COMPONENTS||
       scm_hypothesis_validate(s))return SCM_ONLINE_ERR_ARGUMENT;
    memset(out,0,sizeof(*out));
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        out->log_weight[j]=s->log_weight[j];out->component_flags[j]=s->component[j].flags;
    }
    target_hull(s,out->all_component_soc_capacity_hull);
    if(selector==SCM_HYPOTHESIS_AGGREGATE)aggregate_query(s,&out->view.aggregate);
    else component_query(&s->component[selector],&out->view.component);
    return SCM_ONLINE_OK;
}

int scm_hypothesis_mark_unknown_gap(scm_hypothesis *s)
{
    unsigned j;
    if(scm_hypothesis_validate(s))return SCM_ONLINE_ERR_STATE;
    if(s->header.generation==UINT64_MAX)return SCM_ONLINE_ERR_OVERFLOW;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++)s->component[j].flags|=SCM_ONLINE_FLAG_RECOVERY_REQUIRED;
    s->header.generation++;return SCM_ONLINE_ERR_RECOVERY_REQUIRED;
}

int scm_hypothesis_cold_reset(scm_hypothesis *s)
{
    unsigned j;
    if(scm_hypothesis_validate(s))return SCM_ONLINE_ERR_STATE;
    if(s->header.generation==UINT64_MAX||s->component[0].cold_resets==UINT64_MAX)return SCM_ONLINE_ERR_OVERFLOW;
    for(j=0;j<SCM_HYPOTHESIS_COMPONENTS;j++) {
        scm_hypothesis_component *c=&s->component[j];
        c->epoch_begin=c->next_index;c->evidence_next_index=c->next_index;c->epoch_elapsed_s=0;
        c->cold_resets++;c->flags=SCM_ONLINE_FLAG_HISTORY_LOST;public_belief(c);
        if(s->header.flags&SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT)split_component(c,j);
        s->log_weight[j]=-0.69314718055994530942;
    }
    s->header.generation++;
    s->header.bank_evidence_next_index=s->component[0].epoch_begin;
    s->header.flags&=SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT;
    s->header.last_rejection_stage=SCM_HYPOTHESIS_REJECT_NONE;
    s->header.last_rejection_component=SCM_HYPOTHESIS_NO_COMPONENT;
    return SCM_ONLINE_OK;
}

