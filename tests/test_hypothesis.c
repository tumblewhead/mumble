/* Independent finite numerical/transaction fixtures for the two-component
 * candidate. Dense matrices and extra banks below belong to this host oracle,
 * not the fixed-memory learner. No cell trace, truth file or optimizer is used. */
#include "scm_hypothesis.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define D SCM_HYPOTHESIS_DIM
#define AT(i,j) ((i)*D+(j))
#define PK(i,j) SCM_HYPOTHESIS_FACTOR_INDEX(i,j)
static int checks,failures;
static double max_prediction_error,max_factor_derivative_error,max_joseph_error,max_weight_error;
#define CHECK(c,m) do { checks++; if(!(c)){failures++;fprintf(stderr,"FAIL line %d: %s\n",__LINE__,m);} } while(0)

static scm_hypothesis_config configuration(void)
{
    scm_hypothesis_config c;unsigned i;
    scm_hypothesis_config_default(&c);
    for(i=0;i<SCM_ONLINE_SOURCE_BYTES;i++)c.source_id[i]=(unsigned char)(19+3*i);
    return c;
}

static void prior(scm_hypothesis *s,scm_hypothesis_mode mode)
{
    scm_hypothesis_config c=configuration();
    CHECK(scm_hypothesis_init(s,&c,mode)==0,"public initialization succeeds");
}

static double entry(const double *l,int i,int j)
{return j<=i?l[PK(i,j)]:0.;}

static void covariance(const double *l,double *p)
{
    int i,j,k;
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        p[AT(i,j)]=0.;
        for(k=0;k<D;k++)p[AT(i,j)]+=entry(l,i,k)*entry(l,j,k);
    }
}

static double observation(const double *x,double current)
{
    double v=0.,slope;
    CHECK(scm_ocv_eval(NULL,x[11],&v,&slope)==0,"independent OCV evaluates");
    return v-x[6]*current-x[12]-x[13]-x[14]-x[10]*x[15];
}

/* Preserved physical-model transition, independent of the new analytic
 * Jacobian and packed propagation implementation. */
static int physical(const double x[D],double dt,double current,double result[D],double *voltage)
{
    scm_physical p={0};scm_physical_state st={0};int i,rc;
    p.modes=3;p.gamma_plus=exp(x[3]);p.gamma_minus=exp(x[4]);p.Q=exp(x[5]);
    p.R0=x[6];p.H=x[10];st.z=x[11];st.h=x[15];
    for(i=0;i<3;i++){p.tau[i]=exp(x[i]);p.R[i]=x[7+i];st.v[i]=x[12+i];}
    rc=scm_physical_step(&p,&st,NULL,dt,current,voltage);if(rc)return rc;
    memcpy(result,x,D*sizeof(double));result[11]=st.z;result[15]=st.h;
    for(i=0;i<3;i++)result[12+i]=st.v[i];
    return 0;
}

static void prediction_and_derivatives(void)
{
    const double currents[]={.073,-.041,0};const double intervals[]={.0341,.123,0};
    scm_hypothesis before,after;scm_hypothesis_workspace w;
    double expected[D],plus[D],minus[D],x[D],jac[D*D];int n,i,j,k,c;
    for(n=0;n<3;n++) {
        double voltage,dt=intervals[n],current=currents[n];scm_sample input={dt,current,NAN};
        prior(&before,SCM_HYPOTHESIS_COINCIDENT);
        before.component[0].mean[12]=.011;before.component[0].mean[13]=-.007;
        before.component[0].mean[14]=.004;before.component[0].mean[15]=.31;
        for(i=0;i<D;i++)for(j=0;j<i;j++)before.component[0].factor[PK(i,j)]=
            .017*before.component[0].factor[PK(i,i)]*sin((double)((i+1)*(j+3)));
        before.component[1]=before.component[0];
        CHECK(physical(before.component[0].mean,dt,current,expected,&voltage)==0,"independent physical transition");
        after=before;
        CHECK(scm_hypothesis_ingest(&after,before.component[0].config.source_id,0,&input,0,&w)==0,"prediction-only input");
        for(c=0;c<2;c++)for(i=0;i<D;i++) {
            double e=fabs(after.component[c].mean[i]-expected[i]);max_prediction_error=fmax(max_prediction_error,e);
            CHECK(e<3e-15,"packed mean matches original physical dynamics");
        }
        CHECK(fabs(after.component[0].last_prediction_V-voltage)<3e-15,"physical voltage prediction");
        for(k=0;k<D;k++) {
            const double step=1e-6;
            memcpy(x,before.component[0].mean,sizeof(x));x[k]+=step;
            CHECK(physical(x,dt,current,plus,&voltage)==0,"positive finite difference");
            x[k]-=2*step;CHECK(physical(x,dt,current,minus,&voltage)==0,"negative finite difference");
            for(i=0;i<D;i++)jac[AT(i,k)]=(plus[i]-minus[i])/(2*step);
        }
        for(i=0;i<D;i++)for(j=0;j<D;j++) {
            double value=0.,e;
            for(k=0;k<D;k++)value+=jac[AT(i,k)]*entry(before.component[0].factor,k,j);
            e=fabs(value-entry(after.component[0].factor,i,j));max_factor_derivative_error=fmax(max_factor_derivative_error,e);
            CHECK(e<2e-8,"packed factor transport matches independent derivative");
        }
        CHECK(!memcmp(after.component[0].mean,after.component[1].mean,sizeof(after.component[0].mean))&&
              !memcmp(after.component[0].factor,after.component[1].factor,sizeof(after.component[0].factor)),
              "coincident prediction components remain identical");
        CHECK(!memcmp(before.log_weight,after.log_weight,sizeof(before.log_weight)),"missing voltage retains weights");
        CHECK(after.component[0].next_index==1&&after.component[1].next_index==1&&
              after.component[0].missing_voltage_count==1&&after.component[1].missing_voltage_count==1,
              "one physical input per component with one common chronology");
        CHECK(scm_hypothesis_validate(&after)==0,"prediction bank validates");
    }
}

/* Dense Joseph oracle forms (I-KH)P(I-KH)^T + K sigma^2 K^T independently
 * from a full covariance. It never uses either square-root rotation pass or
 * a diagnostic gain reported by the candidate. */
static void joseph_case(int kind)
{
    scm_hypothesis before,after;scm_hypothesis_workspace w;
    double p[D*D],a[D*D],ap[D*D],want[D*D],actual[D*D];
    double h[D]={0},gain[D]={0},selected[D],lo[D],hi[D];
    double predicted,u,slope,var,residual,minimum=1.,maximum=0.;
    scm_sample input={0.,.04,0.};int i,j,k,c,active=0,any=0;unsigned limited=0,blocked=0;
    scm_hypothesis_component *b;
    prior(&before,SCM_HYPOTHESIS_COINCIDENT);b=&before.component[0];
    for(i=0;i<D;i++)for(j=0;j<i;j++)b->factor[PK(i,j)]=.013*b->factor[PK(i,i)]*cos((double)((i+3)*(j+1)));
    if(kind==2) {
        for(i=0;i<D;i++)for(j=0;j<i;j++)b->factor[PK(i,j)]=0.;
        b->factor[PK(11,5)]=.04;b->mean[6]=0.;
    }
    if(kind==3||kind==9)for(i=0;i<D;i++)for(j=0;j<=i;j++)if(j%2==0)b->factor[PK(i,j)]=0.;
    if(kind==4) {
        memset(b->factor,0,sizeof(b->factor));b->factor[PK(0,0)]=.5;b->factor[PK(1,1)]=.4;
        b->factor[PK(1,0)]=-0.;b->mean[10]=-0.;
    }
    if(kind==5) {
        for(i=0;i<D;i++)for(j=0;j<i;j++)b->factor[PK(i,j)]=0.;
        b->mean[6]=0.;b->mean[10]=.1;b->mean[11]=1.;b->mean[15]=-1.;
        for(i=12;i<=14;i++)b->mean[i]=-.25;
    }
    if(kind==7)b->factor[PK(0,0)]=0.;
    if(kind==8) {
        memset(b->factor,0,sizeof(b->factor));b->factor[PK(6,6)]=.2;b->factor[PK(11,6)]=.1;b->mean[6]=1.;
    }
    before.component[1]=*b;
    CHECK(scm_hypothesis_validate(&before)==0,"independent Joseph fixture valid");
    predicted=observation(b->mean,input.current);
    CHECK(scm_ocv_eval(NULL,b->mean[11],&u,&slope)==0,"independent voltage slope");
    h[6]=-input.current;h[10]=-b->mean[15];h[11]=slope;h[12]=h[13]=h[14]=-1.;h[15]=-b->mean[10];
    residual=(kind==1||kind==9)?10.:kind==6?0.:(kind==2||kind==5||kind==8)?.001:1e-5;
    input.voltage=predicted+residual;residual=input.voltage-predicted;
    covariance(b->factor,p);var=b->config.sigma_V*b->config.sigma_V;
    for(i=0;i<D;i++){for(j=0;j<D;j++)gain[i]+=p[AT(i,j)]*h[j];var+=h[i]*gain[i];}
    for(i=0;i<D;i++)gain[i]/=var;
    scm_hypothesis_bounds(lo,hi);
    for(i=0;i<D;i++) {
        double delta=gain[i]*residual,scale=1.;
        if(delta>hi[i]-b->mean[i])scale=(hi[i]-b->mean[i])/delta;
        else if(delta<lo[i]-b->mean[i])scale=(lo[i]-b->mean[i])/delta;
        if(scale<1.)scale*=1.-1e-9;
        selected[i]=scale*gain[i];
        if(gain[i]!=0.){active=1;minimum=fmin(minimum,scale);maximum=fmax(maximum,scale);
            if(scale<1.)limited|=1u<<i;
            if(selected[i]==0.)blocked|=1u<<i;
        }
        if(selected[i]!=0.)any=1;
    }
    if(!active)maximum=1.;
    for(i=0;i<D;i++)for(j=0;j<D;j++)a[AT(i,j)]=(i==j?1.:0.)-selected[i]*h[j];
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        ap[AT(i,j)]=0.;for(k=0;k<D;k++)ap[AT(i,j)]+=a[AT(i,k)]*p[AT(k,j)];
    }
    for(i=0;i<D;i++)for(j=0;j<D;j++) {
        want[AT(i,j)]=selected[i]*selected[j]*b->config.sigma_V*b->config.sigma_V;
        for(k=0;k<D;k++)want[AT(i,j)]+=ap[AT(i,k)]*a[AT(j,k)];
    }
    after=before;
    CHECK(scm_hypothesis_ingest(&after,b->config.source_id,0,&input,1,&w)==0,"Joseph input accepted");
    CHECK(after.component[0].rejected_voltage_count==0&&after.component[1].rejected_voltage_count==0,"finite Joseph fixture not rejected");
    for(c=0;c<2;c++) {
        scm_hypothesis_component *s=&after.component[c];
        covariance(s->factor,actual);
        CHECK(fabs(s->last_gain_scale-minimum)<2e-13&&fabs(s->last_max_gain_scale-maximum)<2e-13,"gain extrema match dense oracle");
        CHECK(s->last_limited_mask==limited&&s->last_blocked_mask==blocked,"gain masks match dense oracle");
        CHECK(s->zero_gain_count==(uint64_t)!any&&s->limited_gain_count==(uint64_t)(limited!=0),"component gain counters");
        CHECK(s->has_voltage==any&&s->evidence_next_index==(uint64_t)any,"conditional evidence follows actual gain");
        for(i=0;i<D;i++) {
            CHECK(fabs(s->mean[i]-(b->mean[i]+selected[i]*residual))<2e-13,"same selected gain for mean");
            CHECK(s->factor[PK(i,i)]>=0.,"packed diagonal nonnegative");
            for(j=0;j<D;j++) {
                double e=fabs(actual[AT(i,j)]-want[AT(i,j)]);max_joseph_error=fmax(max_joseph_error,e);
                CHECK(e<3e-13*fmax(1.,fabs(want[AT(i,j)])),"full covariance matches independent dense Joseph");
            }
        }
        if(kind==4||kind==5) {
            CHECK(!memcmp(b->mean,s->mean,sizeof(b->mean)),"all-zero gain preserves signed mean bytes");
            CHECK(!memcmp(b->factor,s->factor,sizeof(b->factor)),"all-zero gain preserves signed factor bytes");
        }
        if(kind==6) {
            CHECK(!memcmp(b->mean,s->mean,sizeof(b->mean)),"zero residual preserves mean bytes");
            CHECK(actual[AT(11,11)]<p[AT(11,11)]&&s->has_voltage,"zero residual still learns covariance");
        }
        if(kind==8)CHECK(s->factor[PK(11,11)]>0.&&actual[AT(6,6)]*actual[AT(11,11)]-actual[AT(6,11)]*actual[AT(11,6)]>1e-10,
                         "constrained Joseph can increase rank through zero pivot");
    }
    CHECK(!memcmp(after.component[0].mean,after.component[1].mean,sizeof(b->mean))&&
          !memcmp(after.component[0].factor,after.component[1].factor,sizeof(b->factor)),"coincident conditionals stay equal without precision pooling");
    CHECK(after.log_weight[0]==after.log_weight[1],"identical predictive scores retain equal weights");
    CHECK(after.header.bank_evidence_next_index==(uint64_t)any,"coincident bank evidence matches conditional update");
    CHECK(scm_hypothesis_validate(&after)==0,"Joseph bank validates");
}

static void public_split_and_mixture(void)
{
    scm_hypothesis single,split,saved;scm_hypothesis_query_result q;int i,j;
    double p0[D*D],p1[D*D],pold[D*D];
    prior(&single,SCM_HYPOTHESIS_COINCIDENT);prior(&split,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);
    covariance(single.component[0].factor,pold);covariance(split.component[0].factor,p0);covariance(split.component[1].factor,p1);
    for(i=0;i<D;i++) {
        double mean=.5*(split.component[0].mean[i]+split.component[1].mean[i]);
        CHECK(fabs(mean-single.component[0].mean[i])<5e-16,"split preserves full public coordinate mean");
        for(j=0;j<D;j++) {
            double value=.5*(p0[AT(i,j)]+p1[AT(i,j)]);
            int c;for(c=0;c<2;c++)value+=.5*(split.component[c].mean[i]-mean)*
                (split.component[c].mean[j]-.5*(split.component[0].mean[j]+split.component[1].mean[j]));
            CHECK(fabs(value-pold[AT(i,j)])<5e-16,"split within plus between recovers full public covariance");
        }
    }
    saved=split;CHECK(scm_hypothesis_query(&split,SCM_HYPOTHESIS_AGGREGATE,&q)==0,"initial aggregate query");
    CHECK(!q.view.aggregate.point_available&&!q.view.aggregate.capacity_available,"public prior is not learned availability");
    CHECK(!memcmp(&saved,&split,sizeof(split)),"query cannot feed mixture moments into inference");
    for(i=0;i<D;i++)CHECK(fabs(q.view.aggregate.coordinate_sd[i]-sqrt(pold[AT(i,i)]))<5e-15,"aggregate SD includes between-component variance");
    CHECK(q.all_component_soc_capacity_hull[2]<exp(split.component[0].mean[5])&&
          q.all_component_soc_capacity_hull[3]>exp(split.component[1].mean[5]),"unlearned component hull uses retained factors");
    CHECK(sizeof(scm_hypothesis_component)==1464&&sizeof(scm_hypothesis_header)==32&&sizeof(scm_hypothesis)==2976,
          "component and complete bank layout matches budget");
    CHECK(sizeof(scm_hypothesis_workspace)==3504&&sizeof(scm_hypothesis_query_result)==592,"stage/scratch and one query arena match budget");
    CHECK(sizeof(scm_hypothesis)+sizeof(scm_hypothesis_workspace)+sizeof(scm_hypothesis_query_result)+
          sizeof(scm_hypothesis_config)+sizeof(scm_sample)==7152,"all named owned objects total 7152 bytes");
}

static double predictive_score(const scm_hypothesis_component *c,double current,double voltage)
{
    double p[D*D],h[D]={0},u,slope,v,s=c->config.sigma_V*c->config.sigma_V;int i,j;
    covariance(c->factor,p);CHECK(scm_ocv_eval(NULL,c->mean[11],&u,&slope)==0,"predictive score OCV slope");
    h[6]=-current;h[10]=-c->mean[15];h[11]=slope;h[12]=h[13]=h[14]=-1.;h[15]=-c->mean[10];
    for(i=0;i<D;i++)for(j=0;j<D;j++)s+=h[i]*p[AT(i,j)]*h[j];
    v=voltage-observation(c->mean,current);
    return -.5*(log(s)+v*v/s);
}

static void underflowed_weight_moment(void)
{
    scm_hypothesis b;scm_hypothesis_query_result q;int c,kind;
    for(kind=0;kind<2;kind++) {
        double expected;
        prior(&b,SCM_HYPOTHESIS_COINCIDENT);
        for(c=0;c<2;c++)memset(b.component[c].factor,0,sizeof(b.component[c].factor));
        b.component[0].factor[PK(5,5)]=kind?1e308:1e150;
        b.component[1].factor[PK(5,5)]=kind?1e-140:1e-80;
        b.log_weight[0]=kind?-2000.:-1000.;b.log_weight[1]=0.;
        CHECK(scm_hypothesis_validate(&b)==0&&exp(b.log_weight[0])==0.,"moment fixture has finite stored weight but underflowed display weight");
        expected=hypot(exp(.5*b.log_weight[0]+log(b.component[0].factor[PK(5,5)])),b.component[1].factor[PK(5,5)]);
        CHECK(scm_hypothesis_query(&b,SCM_HYPOTHESIS_AGGREGATE,&q)==0,"underflowed-weight moment query");
        CHECK(isfinite(expected)&&expected>1e-130&&fabs(q.view.aggregate.coordinate_sd[5]/expected-1.)<2e-13,
              "representable weighted covariance survives linear and square-root weight underflow");
    }
}

static void weights_and_evidence_cursors(void)
{
    scm_hypothesis b,saved,predicted;scm_hypothesis_workspace w;scm_hypothesis_query_result q;
    scm_sample input={0.,.04,3.8};double ell[2],raw[2],normal,w0,w1;int c;
    prior(&b,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);
    b.component[1].mean[11]+=.02;input.voltage=observation(b.component[0].mean,input.current)+.002;
    for(c=0;c<2;c++){ell[c]=predictive_score(&b.component[c],input.current,input.voltage);raw[c]=b.log_weight[c]+ell[c];}
    normal=fmax(raw[0],raw[1])+log(exp(raw[0]-fmax(raw[0],raw[1]))+exp(raw[1]-fmax(raw[0],raw[1])));
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"weighted conditional update");
    for(c=0;c<2;c++) {
        double e=fabs(w.pre_correction_log_likelihood[c]-ell[c]);max_weight_error=fmax(max_weight_error,e);
        CHECK(e<2e-12,"weight likelihood uses pre-correction full predictive covariance");
        CHECK(fabs(b.log_weight[c]-(raw[c]-normal))<2e-12,"causal log weights match independent normalization");
    }
    CHECK(scm_hypothesis_query(&b,SCM_HYPOTHESIS_AGGREGATE,&q)==0,"weighted aggregate query");
    w0=exp(b.log_weight[0]);w1=exp(b.log_weight[1]);
    CHECK(fabs(q.view.aggregate.capacity_Ah-exp(w0*b.component[0].mean[5]+w1*b.component[1].mean[5]))<1e-15,
          "aggregate capacity uses frozen geometric point convention");
    CHECK(fabs(q.view.aggregate.predicted_voltage_V-(w0*b.component[0].last_prediction_V+w1*b.component[1].last_prediction_V))<2e-15,
          "aggregate voltage is mixture of component physical predictions");

    prior(&b,SCM_HYPOTHESIS_COINCIDENT);memset(b.component[0].factor,0,sizeof(b.component[0].factor));
    input=(scm_sample){.01,.02,3.8};
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"one zero-gain component is allowed");
    CHECK(!b.component[0].has_voltage&&b.component[0].evidence_next_index==0&&b.component[1].has_voltage&&
          b.component[1].evidence_next_index==1&&b.header.bank_evidence_next_index==1,
          "conditional evidence cursors may differ from each other and bank");
    CHECK(scm_hypothesis_validate(&b)==0,"distinct conditional cursors validate");

    prior(&b,SCM_HYPOTHESIS_COINCIDENT);
    for(c=0;c<2;c++)memset(b.component[c].factor,0,sizeof(b.component[c].factor));
    b.component[1].mean[11]+=.02;predicted=b;input=(scm_sample){.01,.02,3.8};
    CHECK(scm_hypothesis_ingest(&predicted,predicted.component[0].config.source_id,0,&input,0,&w)==0,"weight-only independent physical reference");
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"two all-zero gains can learn relative weights");
    CHECK(!b.component[0].has_voltage&&!b.component[1].has_voltage&&b.component[0].evidence_next_index==0&&
          b.component[1].evidence_next_index==0&&b.header.bank_evidence_next_index==1&&
          (b.header.flags&SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE),"weight-only joint freshness differs from conditional evidence");
    CHECK(scm_hypothesis_query(&b,SCM_HYPOTHESIS_AGGREGATE,&q)==0&&q.view.aggregate.point_available&&
          q.view.aggregate.capacity_available&&q.view.aggregate.prediction_available,"weight-only aggregate availability uses joint evidence");
    CHECK(q.all_component_soc_capacity_hull[0]==fmin(b.component[0].mean[11],b.component[1].mean[11])&&
          q.all_component_soc_capacity_hull[1]==fmax(b.component[0].mean[11],b.component[1].mean[11]),
          "zero-variance local hull includes unavailable conditional points");
    for(c=0;c<2;c++) {
        CHECK(!memcmp(b.component[c].mean,predicted.component[c].mean,sizeof(b.component[c].mean))&&
              !memcmp(b.component[c].factor,predicted.component[c].factor,sizeof(b.component[c].factor)),
              "weight-only transaction preserves predicted conditional bytes");
        CHECK(scm_hypothesis_query(&b,c,&q)==0&&!q.view.component.point_available,"weight-only conditional availability remains false");
    }
    prior(&b,SCM_HYPOTHESIS_COINCIDENT);
    for(c=0;c<2;c++)memset(b.component[c].factor,0,sizeof(b.component[c].factor));
    b.log_weight[0]=log(.2);b.log_weight[1]=log(.8);input=(scm_sample){.01,.02,3.8};
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"all-zero equal-score observation accepted");
    CHECK(b.header.bank_evidence_next_index==0&&!(b.header.flags&SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE),
          "equal scores cannot manufacture fresh evidence via normalization rounding");
    CHECK(scm_hypothesis_query(&b,SCM_HYPOTHESIS_AGGREGATE,&q)==0&&!q.view.aggregate.point_available&&q.view.aggregate.prediction_available,
          "physical prediction availability is distinct from learned-point availability");

    prior(&b,SCM_HYPOTHESIS_COINCIDENT);
    for(c=0;c<2;c++)memset(b.component[c].factor,0,sizeof(b.component[c].factor));
    b.component[1].mean[11]+=.02;b.log_weight[0]=-1e300;b.log_weight[1]=0.;saved=b;
    input=(scm_sample){0.,0.,0.};input.voltage=observation(b.component[1].mean,input.current);
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"finite unequal-score weight update below odds resolution");
    CHECK(w.pre_correction_log_likelihood[0]!=w.pre_correction_log_likelihood[1]&&
          !memcmp(b.log_weight,saved.log_weight,sizeof(b.log_weight)),"unequal scores can leave finite stored log odds unchanged");
    CHECK(b.header.bank_evidence_next_index==0&&!(b.header.flags&SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE),
          "unrepresented relative-weight change cannot manufacture joint freshness");

    prior(&b,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);b.log_weight[0]=-1000.;b.log_weight[1]=0.;saved=b;
    CHECK(scm_hypothesis_validate(&b)==0&&exp(b.log_weight[0])==0.,"finite log weight survives display underflow");
    input=(scm_sample){.01,.02,3.8};
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"underflowed component still advances");
    CHECK(b.header.active_components==2&&isfinite(b.log_weight[0])&&b.component[0].has_voltage&&
          memcmp(saved.component[0].mean,b.component[0].mean,sizeof(b.component[0].mean))!=0,"underflow does not prune or suppress component correction");
    CHECK(scm_hypothesis_query(&b,SCM_HYPOTHESIS_AGGREGATE,&q)==0,"underflowed weight query remains available");
    {
        double lo0=b.component[0].mean[11],lo1=b.component[1].mean[11],sd0=0.,sd1=0.;int i;
        for(i=0;i<=11;i++){sd0=hypot(sd0,b.component[0].factor[PK(11,i)]);sd1=hypot(sd1,b.component[1].factor[PK(11,i)]);}
        CHECK(q.all_component_soc_capacity_hull[0]==fmin(lo0-2*sd0,lo1-2*sd1),"all-component hull ignores display weight underflow");
    }
}

static void rejection_and_prediction_recovery(void)
{
    scm_hypothesis b,before,predicted;scm_hypothesis_workspace w;scm_hypothesis_query_result q;
    scm_sample input={.031,.04,3.8};int c;
    prior(&b,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);b.component[1].factor[PK(11,0)]=1e200;before=b;predicted=b;
    CHECK(scm_hypothesis_validate(&b)==0,"large finite conditional covariance accepted as an input state");
    CHECK(scm_hypothesis_ingest(&predicted,predicted.component[0].config.source_id,0,&input,0,&w)==0,"rejection reference physical prediction");
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"second-component correction failure consumes known interval");
    CHECK(b.header.last_rejection_component==1&&b.header.last_rejection_stage==SCM_HYPOTHESIS_REJECT_INNOVATION_SD,
          "failure stage/component captured after first component trial");
    for(c=0;c<2;c++) {
        CHECK(!memcmp(b.component[c].mean,predicted.component[c].mean,sizeof(b.component[c].mean))&&
              !memcmp(b.component[c].factor,predicted.component[c].factor,sizeof(b.component[c].factor)),
              "whole-bank rejection retains both physical predictions exactly");
        CHECK(b.component[c].next_index==1&&b.component[c].prediction_count==1&&b.component[c].voltage_count==1&&
              b.component[c].rejected_voltage_count==1&&!b.component[c].has_voltage&&b.component[c].evidence_next_index==0,
              "whole-bank rejection accounts input once with no conditional evidence");
    }
    CHECK(!memcmp(b.log_weight,before.log_weight,sizeof(b.log_weight))&&b.header.bank_evidence_next_index==0,
          "failed component cannot change weights or joint evidence");
    CHECK(scm_hypothesis_validate(&b)==0,"rejected voltage bank remains valid");

    prior(&b,SCM_HYPOTHESIS_COINCIDENT);
    for(c=0;c<2;c++)memset(b.component[c].factor,0,sizeof(b.component[c].factor));
    b.component[1].factor[PK(12,12)]=1.;
    b.log_weight[0]=-1.7e308;b.log_weight[1]=0.;before=b;input=(scm_sample){0.,0.,1e151};
    CHECK(scm_hypothesis_validate(&b)==0,"finite extreme log odds are not pruned");
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,"nonfinite weight arithmetic rejects voltage transaction");
    CHECK(w.pre_correction_log_likelihood[0]!=w.pre_correction_log_likelihood[1]&&
          isfinite(w.pre_correction_log_likelihood[0])&&isfinite(w.pre_correction_log_likelihood[1]),
          "differential overflow fixture has unequal finite predictive scores");
    CHECK(b.header.last_rejection_stage==SCM_HYPOTHESIS_REJECT_WEIGHTS&&b.component[0].rejected_voltage_count==1&&
          b.component[1].rejected_voltage_count==1,"genuine relative-log-odds overflow is explicit whole-bank rejection");
    CHECK(!memcmp(b.log_weight,before.log_weight,sizeof(b.log_weight))&&b.header.bank_evidence_next_index==0,
          "weight failure preserves finite old log weights without floor");
    for(c=0;c<2;c++)CHECK(!memcmp(b.component[c].mean,before.component[c].mean,sizeof(b.component[c].mean))&&
        !memcmp(b.component[c].factor,before.component[c].factor,sizeof(b.component[c].factor))&&b.component[c].zero_gain_count==0,
        "later weight failure rolls back all-zero correction metadata and arrays");

    prior(&b,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);b.component[1].mean[11]=0.;before=b;input=(scm_sample){1.,.25,3.8};
    CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==SCM_ONLINE_ACCEPTED_RECOVERY,
          "one prediction failure consumes known interval and enters whole-bank recovery");
    for(c=0;c<2;c++)CHECK(b.component[c].next_index==1&&b.component[c].prediction_count==1&&b.component[c].elapsed_s==1.&&
        b.component[c].rejected_voltage_count==1&&(b.component[c].flags&SCM_ONLINE_FLAG_MODEL_UNAVAILABLE)&&
        !b.component[c].prediction_valid&&!memcmp(b.component[c].mean,before.component[c].mean,sizeof(b.component[c].mean))&&
        !memcmp(b.component[c].factor,before.component[c].factor,sizeof(b.component[c].factor)),
        "prediction failure retains both last valid beliefs without current-state claim");
    CHECK(!memcmp(b.log_weight,before.log_weight,sizeof(b.log_weight)),"prediction failure never excludes a component");
    CHECK(scm_hypothesis_query(&b,SCM_HYPOTHESIS_AGGREGATE,&q)==0&&!q.view.aggregate.point_available&&
          !q.view.aggregate.capacity_available&&!q.view.aggregate.prediction_available,"recovery withholds current aggregate");
    CHECK(scm_hypothesis_validate(&b)==0,"recovery bank remains checkpoint-valid");
}

/* An arbitrarily unlikely observation common to both alternatives supplies
 * no relative evidence. Removing its common log score must precede addition
 * to carried log odds, or finite precision can erase the old preference. */
static void common_score_cancellation(void)
{
    scm_hypothesis b,before;scm_hypothesis_workspace w;
    scm_sample input={0.,0.,1e151};int c,kind;
    for(kind=0;kind<2;kind++) {
        prior(&b,SCM_HYPOTHESIS_COINCIDENT);
        for(c=0;c<2;c++)memset(b.component[c].factor,0,sizeof(b.component[c].factor));
        if(kind==0){b.log_weight[0]=log(.2);b.log_weight[1]=log(.8);}
        else {b.log_weight[0]=-1.7e308;b.log_weight[1]=0.;}
        before=b;
        CHECK(scm_hypothesis_validate(&b)==0,"common-score cancellation input bank valid");
        CHECK(scm_hypothesis_ingest(&b,b.component[0].config.source_id,0,&input,1,&w)==0,
              "huge finite common likelihood does not cause avoidable rejection");
        CHECK(isfinite(w.pre_correction_log_likelihood[0])&&
              w.pre_correction_log_likelihood[0]==w.pre_correction_log_likelihood[1]&&
              w.pre_correction_log_likelihood[0]<-1e307,"fixture has identical huge finite negative scores");
        CHECK(!memcmp(b.log_weight,before.log_weight,sizeof(b.log_weight)),
              "equal predictive evidence preserves carried log odds byte-exact");
        CHECK(!b.component[0].rejected_voltage_count&&!b.component[1].rejected_voltage_count&&
              b.header.bank_evidence_next_index==0&&!(b.header.flags&SCM_HYPOTHESIS_FLAG_JOINT_EVIDENCE),
              "common score alone cannot create rejection or evidence freshness");
        CHECK(scm_hypothesis_validate(&b)==0,"common-score output remains valid");
    }
}

static void reject_atomic(scm_hypothesis *s,const unsigned char *id,uint64_t index,
                          scm_sample input,int present,int wanted,const char *message)
{
    scm_hypothesis before=*s;scm_hypothesis_workspace w;
    CHECK(scm_hypothesis_ingest(s,id,index,&input,present,&w)==wanted,message);
    CHECK(!memcmp(&before,s,sizeof(before)),"negative ingest return leaves live bank byte-identical");
}

static void lifecycle_and_validation(void)
{
    scm_hypothesis s,before,initial;scm_hypothesis_workspace w;scm_hypothesis_query_result q;
    scm_hypothesis_config cfg=configuration(),bad=cfg;scm_sample input={.027,.04,3.8};unsigned char wrong[32]={0};int c;
    prior(&s,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);initial=s;before=s;bad.sigma_V=0.;
    CHECK(scm_hypothesis_init(&s,&bad,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT)==SCM_ONLINE_ERR_ARGUMENT&&
          !memcmp(&s,&before,sizeof(s)),"invalid initialization is atomic");
    reject_atomic(&s,wrong,0,input,1,SCM_ONLINE_ERR_SOURCE,"wrong source rejected");
    reject_atomic(&s,cfg.source_id,1,input,1,SCM_ONLINE_ERR_ORDER,"out-of-order input rejected");
    input.dt=-1.;reject_atomic(&s,cfg.source_id,0,input,1,SCM_ONLINE_ERR_DOMAIN,"negative interval rejected");
    input.dt=1.01;reject_atomic(&s,cfg.source_id,0,input,1,SCM_ONLINE_ERR_DOMAIN,"oversize interval rejected");
    input.dt=.027;input.current=.251;reject_atomic(&s,cfg.source_id,0,input,1,SCM_ONLINE_ERR_DOMAIN,"oversize current rejected");
    input.current=NAN;reject_atomic(&s,cfg.source_id,0,input,1,SCM_ONLINE_ERR_NONFINITE,"nonfinite current rejected");
    input.current=.04;input.voltage=NAN;reject_atomic(&s,cfg.source_id,0,input,1,SCM_ONLINE_ERR_NONFINITE,"present NaN voltage rejected");
    CHECK(scm_hypothesis_ingest(&s,cfg.source_id,0,&input,0,&w)==0,"missing voltage payload ignored");
    input.voltage=3.8;CHECK(scm_hypothesis_ingest(&s,cfg.source_id,1,&input,1,&w)==0,"next physical interval accepted");
    reject_atomic(&s,cfg.source_id,1,input,1,SCM_ONLINE_ERR_ORDER,"duplicate input rejected");
    CHECK(scm_hypothesis_mark_unknown_gap(&s)==SCM_ONLINE_ERR_RECOVERY_REQUIRED,"unknown gap latches recovery");
    reject_atomic(&s,cfg.source_id,2,input,1,SCM_ONLINE_ERR_RECOVERY_REQUIRED,"unrecovered gap blocks input");
    before=s;CHECK(scm_hypothesis_cold_reset(&s)==0,"explicit cold reset");
    for(c=0;c<2;c++)CHECK(s.component[c].next_index==before.component[c].next_index&&
        s.component[c].epoch_begin==s.component[c].next_index&&s.component[c].evidence_next_index==s.component[c].epoch_begin&&
        s.component[c].elapsed_s==before.component[c].elapsed_s&&s.component[c].epoch_elapsed_s==0.&&
        s.component[c].voltage_count==before.component[c].voltage_count&&s.component[c].cold_resets==1&&
        s.component[c].flags==SCM_ONLINE_FLAG_HISTORY_LOST&&!s.component[c].has_voltage&&
        !memcmp(s.component[c].mean,initial.component[c].mean,sizeof(s.component[c].mean))&&
        !memcmp(s.component[c].factor,initial.component[c].factor,sizeof(s.component[c].factor)),
        "cold reset preserves input ledger and reconstructs only the declared public component");
    CHECK(s.header.flags==SCM_HYPOTHESIS_FLAG_LOGQ_SPLIT&&s.header.bank_evidence_next_index==s.component[0].epoch_begin&&
          !memcmp(s.log_weight,initial.log_weight,sizeof(s.log_weight)),"cold reset clears joint evidence and restores public weights/mode");
    CHECK(scm_hypothesis_query(&s,SCM_HYPOTHESIS_AGGREGATE,&q)==0&&!q.view.aggregate.point_available&&
          scm_hypothesis_validate(&s)==0,"cold prior explicitly unavailable and valid");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.header.generation=UINT64_MAX;
    reject_atomic(&s,cfg.source_id,0,input,1,SCM_ONLINE_ERR_OVERFLOW,"bank generation cannot wrap");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);
    for(c=0;c<2;c++)s.component[c].elapsed_s=s.component[c].epoch_elapsed_s=1e300;
    reject_atomic(&s,cfg.source_id,0,input,1,SCM_ONLINE_ERR_OVERFLOW,"known physical clock cannot silently stop advancing");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.component[1].factor[PK(0,0)]=-.1;
    CHECK(scm_hypothesis_validate(&s)==SCM_ONLINE_ERR_STATE,"negative diagonal rejected");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.component[1].factor[PK(12,4)]=INFINITY;
    CHECK(scm_hypothesis_validate(&s)==SCM_ONLINE_ERR_STATE,"nonfinite packed factor rejected");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.component[1].next_index=1;
    CHECK(scm_hypothesis_validate(&s)==SCM_ONLINE_ERR_STATE,"inconsistent physical ledger rejected");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.log_weight[0]=s.log_weight[1]=0.;
    CHECK(scm_hypothesis_validate(&s)==SCM_ONLINE_ERR_STATE,"unnormalized weights rejected");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.header.bank_evidence_next_index=1;
    CHECK(scm_hypothesis_validate(&s)==SCM_ONLINE_ERR_STATE,"future bank evidence rejected");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.header.active_components=1;
    CHECK(scm_hypothesis_validate(&s)==SCM_ONLINE_ERR_STATE,"implicit component pruning rejected");
    prior(&s,SCM_HYPOTHESIS_COINCIDENT);s.component[0].last_blocked_mask=1;
    CHECK(scm_hypothesis_validate(&s)==SCM_ONLINE_ERR_STATE,"blocked diagnostic without limiting rejected");
}

static void subnormal_boundary_witness(void)
{
    scm_hypothesis before,after,predicted;scm_hypothesis_workspace w;
    scm_sample input={0.,0.,0.};double unit=nextafter(0.,1.),sd;int c;
    prior(&before,SCM_HYPOTHESIS_COINCIDENT);
    for(c=0;c<2;c++) {
        memset(before.component[c].factor,0,sizeof(before.component[c].factor));
        before.component[c].mean[9]=7.*unit;
        before.component[c].factor[PK(9,9)]=.25;before.component[c].factor[PK(12,9)]=-1.;
    }
    predicted=before;CHECK(scm_hypothesis_ingest(&predicted,before.component[0].config.source_id,0,&input,0,&w)==0,"boundary physical reference");
    sd=hypot(before.component[0].config.sigma_V,1.);input.voltage=predicted.component[0].last_prediction_V-8.*sd;
    after=before;CHECK(scm_hypothesis_ingest(&after,before.component[0].config.source_id,0,&input,1,&w)==0,"minimal production-order boundary input");
    for(c=0;c<2;c++) {
        double p0[D*D],p1[D*D];covariance(before.component[c].factor,p0);covariance(after.component[c].factor,p1);
        CHECK(after.component[c].rejected_voltage_count==0&&after.component[c].mean[9]==7.*unit,
              "finite rounded out-of-domain R3 proposal selects zero without rejection");
        CHECK(after.component[c].last_blocked_mask==(1u<<9)&&after.component[c].last_gain_scale==0.&&
              after.component[c].last_max_gain_scale>0.&&after.component[c].mean[12]!=predicted.component[c].mean[12],
              "boundary fallback does not create a global learning stall");
        CHECK(fabs(p0[AT(9,9)]-p1[AT(9,9)])<3e-15,"zero actual gain retains R3 marginal variance");
        CHECK(after.component[c].has_voltage&&after.component[c].evidence_next_index==1&&after.component[c].zero_gain_count==0,
              "other feasible coordinates retain observation evidence");
    }
    CHECK(after.header.bank_evidence_next_index==1&&scm_hypothesis_validate(&after)==0,"boundary output has valid joint evidence");
}

int main(void)
{
    int kind;
    public_split_and_mixture();prediction_and_derivatives();
    for(kind=0;kind<10;kind++)joseph_case(kind);
    weights_and_evidence_cursors();underflowed_weight_moment();common_score_cancellation();rejection_and_prediction_recovery();
    lifecycle_and_validation();subnormal_boundary_witness();
    printf("{\"test\":\"nonlinear_hypothesis_core\",\"checks\":%d,\"failures\":%d,"
           "\"max_prediction_error\":%.17g,\"max_factor_derivative_error\":%.17g,"
           "\"max_dense_Joseph_error\":%.17g,\"max_predictive_score_error\":%.17g,"
           "\"state_bytes\":%zu,\"workspace_bytes\":%zu,\"query_bytes\":%zu,"
           "\"primary_streams\":0,\"optimizer_calls\":0}\n",checks,failures,
           max_prediction_error,max_factor_derivative_error,max_joseph_error,max_weight_error,
           sizeof(scm_hypothesis),sizeof(scm_hypothesis_workspace),sizeof(scm_hypothesis_query_result));
    return failures?1:0;
}
