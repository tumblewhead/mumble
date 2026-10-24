#include "scm_assess.h"
#include <float.h>
#include <math.h>
#include <string.h>

#define D SCM_MAX_PARAMETERS

void scm_assess_options_default(scm_assess_options *o)
{
    if(!o)return;
    memset(o,0,sizeof(*o));o->relative_halfwidth=.10;o->soc_halfwidth=.05;
    o->eigen_rtol=1e-10;o->null_projection_tol=1e-8;o->sigma_multiplier=2.;
    o->hysteresis_amplitude_floor_V=1e-8;
}
const char *scm_assess_status_name(scm_assess_status s)
{
    return s==SCM_ASSESS_UNEXCITED?"unexcited":s==SCM_ASSESS_PROVISIONAL?"provisional":"unresolved";
}

/* Maximum-pivot Jacobi rotations on a symmetrized, scaled matrix. Eigenvectors
 * are stored by columns. A supplied PSD matrix is not repaired or regularized.
 * Scaling prevents gratuitous overflow and leaves the relative cutoff intact.
 */
static int jacobi(double *a,double *v,int n,double *eigenvalues)
{
    int i,j,k,iteration,p=0,q=0;double scale=0;
    for(i=0;i<n*n;i++)scale=fmax(scale,fabs(a[i]));
    memset(v,0,(size_t)n*n*sizeof(double));
    for(i=0;i<n;i++)v[i*n+i]=1.;
    if(scale==0){for(i=0;i<n;i++)eigenvalues[i]=0;return 1;}
    for(i=0;i<n*n;i++)a[i]/=scale;
    for(iteration=0;iteration<80*n*n;iteration++) {
        double maximum=0,diag=0;
        for(i=0;i<n;i++) {
            diag=fmax(diag,fabs(a[i*n+i]));
            for(j=i+1;j<n;j++)if(fabs(a[i*n+j])>maximum){maximum=fabs(a[i*n+j]);p=i;q=j;}
        }
        if(maximum<=DBL_EPSILON*fmax(diag,1.))break;
        {
            double apq=a[p*n+q],app=a[p*n+p],aqq=a[q*n+q];
            double tau=(aqq-app)/(2*apq);
            double t=copysign(1.,tau)/(fabs(tau)+hypot(1.,tau));
            double c=1./sqrt(1+t*t),s=t*c;
            for(k=0;k<n;k++)if(k!=p&&k!=q) {
                double akp=a[k*n+p],akq=a[k*n+q];
                a[k*n+p]=a[p*n+k]=c*akp-s*akq;
                a[k*n+q]=a[q*n+k]=s*akp+c*akq;
            }
            a[p*n+p]=app-t*apq;a[q*n+q]=aqq+t*apq;
            a[p*n+q]=a[q*n+p]=0;
            for(k=0;k<n;k++) {
                double vkp=v[k*n+p],vkq=v[k*n+q];
                v[k*n+p]=c*vkp-s*vkq;v[k*n+q]=s*vkp+c*vkq;
            }
        }
    }
    for(i=0;i<n;i++)eigenvalues[i]=a[i*n+i]*scale;
    for(i=0;i<n;i++) {
        int smallest=i;
        for(j=i+1;j<n;j++)if(eigenvalues[j]<eigenvalues[smallest])smallest=j;
        if(smallest!=i) {
            double x=eigenvalues[i];eigenvalues[i]=eigenvalues[smallest];eigenvalues[smallest]=x;
            for(k=0;k<n;k++){x=v[k*n+i];v[k*n+i]=v[k*n+smallest];v[k*n+smallest]=x;}
        }
    }
    return iteration<80*n*n;
}

static void support(scm_assess_target *t,const char *name,const char *units,double point,double lo,double hi)
{
    memset(t,0,sizeof(*t));t->name=name;t->units=units;t->point=point;t->point_available=1;
    t->lower=t->support_lower=lo;t->upper=t->support_upper=hi;t->status=SCM_ASSESS_UNRESOLVED;
}

/* threshold:0 nuisance,1 relative halfwidth,2 absolute SOC halfwidth.
 * Log-coordinate gradients are gradients of the transformed log parameter;
 * the interval is exponentiated after evaluating its coordinate variance.
 */
static void diagnose(const scm_fit_result *fit,const scm_assess_options *o,
                     const scm_assessment *a,const scm_assess_workspace *w,
                     scm_assess_target *target,int threshold,int logarithmic,
                     int explicitly_unexcited,int forced)
{
    int i,j,np=a->joint_dimension;double norm2=0,null2=0,variance=0;
    double sd=0,half=0,ratio=0,lo=0,hi=0;int local=0,passes=-1,relative_available=0;
    int null_direction,unavailable;unsigned reason=0;
    for(i=0;i<np;i++)norm2+=w->gradient[i]*w->gradient[i];
    for(j=0;j<np;j++) {
        double projection=0;
        for(i=0;i<np;i++)projection+=w->vectors[i*np+j]*w->gradient[i];
        if(a->eigenvalues[j]>a->eigen_cutoff)variance+=projection*projection/a->eigenvalues[j];
        else null2+=projection*projection;
    }
    target->null_projection=norm2>0?fmax(0.,fmin(1.,null2/norm2)):1.;
    null_direction=target->null_projection>o->null_projection_tol;
    if(o->linked_current_soc_chart)reason|=SCM_ASSESS_REASON_LINKED_CHART;
    else if(forced)reason|=SCM_ASSESS_REASON_HYSTERESIS;
    else if(a->matrix_invalid) {
        if(a->matrix_relative_asymmetry>1e-8)reason|=SCM_ASSESS_REASON_ASYMMETRIC;
        if(!a->eigen_converged)reason|=SCM_ASSESS_REASON_EIGEN_NONCONVERGENCE;
        for(i=0;i<np;i++)if(a->eigenvalues[i]<-fmax(a->eigen_cutoff,1e-12))reason|=SCM_ASSESS_REASON_INDEFINITE;
    } else if(explicitly_unexcited)reason|=SCM_ASSESS_REASON_UNEXCITED;
    else if(null_direction)reason|=SCM_ASSESS_REASON_NULL_SPACE;
    else {
        double coordinate_sd=sqrt(fmax(0.,variance)),radius=o->sigma_multiplier*coordinate_sd;
        if(logarithmic){lo=target->point*exp(-radius);hi=target->point*exp(radius);sd=target->point*coordinate_sd;}
        else{lo=target->point-radius;hi=target->point+radius;sd=coordinate_sd;}
        if(!isfinite(lo)||!isfinite(hi)||!isfinite(sd))reason|=SCM_ASSESS_REASON_NUMERICAL_RANGE;
        else {
            local=1;half=fmax(target->point-lo,hi-target->point);
            relative_available=target->point!=0;
            if(relative_available)ratio=half/fabs(target->point);
            if(threshold==1)passes=relative_available&&ratio<=o->relative_halfwidth;
            else if(threshold==2)passes=half<=o->soc_halfwidth;
            if(passes==0)reason|=SCM_ASSESS_REASON_PRECISION;
            if(lo<target->support_lower||hi>target->support_upper)reason|=SCM_ASSESS_REASON_SUPPORT_CROSSING;
        }
    }
    if(fit->status!=0)reason|=SCM_ASSESS_REASON_OPTIMIZER;
    if(a->active_constraints)reason|=SCM_ASSESS_REASON_ACTIVE_CONSTRAINT;
    if(o->conditioned_fit||o->linked_current_soc_chart)reason|=SCM_ASSESS_REASON_CONDITIONED;
    unavailable=o->linked_current_soc_chart||forced||a->matrix_invalid||explicitly_unexcited||null_direction||!local||fit->status!=0;
    target->reasons=reason;target->active_constraints_present=a->active_constraints!=0;
    target->conditioned_fit=o->conditioned_fit||o->linked_current_soc_chart;
    target->has_local_range=!unavailable;target->has_relative_halfwidth=!unavailable&&relative_available;
    target->passes_local_precision=unavailable?0:passes;
    target->eligible_for_profile_check=!unavailable&&passes==1;
    if(!unavailable) {
        target->lower=lo;target->upper=hi;target->local_standard_deviation=sd;
        target->local_halfwidth=half;target->relative_halfwidth=ratio;
    }
    if(explicitly_unexcited&&!a->matrix_invalid&&!forced&&!o->linked_current_soc_chart)target->status=SCM_ASSESS_UNEXCITED;
    else target->status=unavailable||passes==0?SCM_ASSESS_UNRESOLVED:SCM_ASSESS_PROVISIONAL;
}

int scm_assess(const scm_fit_result *f,int n,const scm_assess_options *input,
               scm_assessment *a,scm_assess_workspace *w)
{
    static const char *tau_name[]={"tau1","tau2","tau3"};
    static const char *r_name[]={"R0","R1","R2","R3"};
    static const char *v_name[]={"v10","v20","v30"};
    scm_assess_options o;int nt,na,np,i,j;double largest,asym=0,q,Q;
    if(!f||!a||!w||n<1||n>SCM_MAX_MODES)return -1;
    scm_assess_options_default(&o);if(input)o=*input;
    if(!isfinite(o.relative_halfwidth)||o.relative_halfwidth<=0||!isfinite(o.soc_halfwidth)||o.soc_halfwidth<=0||
       !isfinite(o.eigen_rtol)||o.eigen_rtol<=0||o.eigen_rtol>=1||!isfinite(o.null_projection_tol)||o.null_projection_tol<=0||o.null_projection_tol>=1||
       !isfinite(o.sigma_multiplier)||o.sigma_multiplier<=0||!isfinite(o.hysteresis_amplitude_floor_V)||o.hysteresis_amplitude_floor_V<0)return -1;
    nt=n+4;na=2*n+3;np=nt+na;q=f->charge_Ah;
    if(!isfinite(q))return -1;
    for(i=0;i<nt;i++)if(!isfinite(f->theta[i]))return -1;
    for(i=0;i<na;i++)if(!isfinite(f->alpha[i]))return -1;
    for(i=0;i<np;i++)if(!isfinite(f->coordinate_scales[i])||f->coordinate_scales[i]<=0)return -1;
    for(i=0;i<np*np;i++)if(!isfinite(f->joint_normal[i]))return -1;
    for(i=0;i<nt;i++)if(i!=n+2&&(!isfinite(exp(f->theta[i]))||exp(f->theta[i])<=0))return -1;
    memset(a,0,sizeof(*a));a->modes=n;a->joint_dimension=np;a->target_count=np+2;
    a->optimizer_status=f->status;a->active_constraints=f->active_linear_constraints+f->active_outer_bounds;
    a->coordinate_chart_supported=!o.linked_current_soc_chart;
    for(i=0;i<np;i++)for(j=0;j<np;j++) {
        double x=f->joint_normal[i*np+j],y=f->joint_normal[j*np+i];
        w->matrix[i*np+j]=.5*x+.5*y;asym=fmax(asym,fabs(x-y));
    }
    a->eigen_converged=jacobi(w->matrix,w->vectors,np,a->eigenvalues);
    largest=fmax(0.,a->eigenvalues[np-1]);a->eigen_cutoff=largest*o.eigen_rtol;
    a->matrix_relative_asymmetry=asym/fmax(largest,1.);
    a->matrix_invalid=!a->eigen_converged||a->matrix_relative_asymmetry>1e-8;
    for(i=0;i<np;i++) {
        if(!isfinite(a->eigenvalues[i]))a->matrix_invalid=1;
        if(a->eigenvalues[i]>a->eigen_cutoff)a->numerical_rank++;
        if(a->eigenvalues[i]<-fmax(a->eigen_cutoff,1e-12))a->matrix_invalid=1;
    }
    for(i=0;i<nt;i++) {
        const char *name,*units;double point,lo,hi;int logarithmic=1,threshold=1;
        if(i<n) {
            static const double l3[]={.015,.15,1.5},h3[]={.15,1.5,30.};
            name=tau_name[i];units="s";lo=n==3?l3[i]:(i?.8:.015);hi=n==3?h3[i]:(i?180.:30.);
        } else if(i==n||i==n+1){name=i==n?"gamma_plus":"gamma_minus";units="1/Ah";lo=5;hi=1200;}
        else if(i==n+2){name="z0";units="SOC fraction";lo=.2;hi=.95;logarithmic=0;threshold=2;}
        else{name="Q_Ah";units="Ah";lo=.03;hi=.1;}
        point=logarithmic?exp(f->theta[i]):f->theta[i];support(&a->targets[i],name,units,point,lo,hi);
        memset(w->gradient,0,np*sizeof(double));w->gradient[i]=f->coordinate_scales[i];
        diagnose(f,&o,a,w,&a->targets[i],threshold,logarithmic,(f->unexcited_theta_mask&(1u<<i))!=0,0);
    }
    for(i=0;i<na;i++) {
        const char *name,*units="V";double lo,hi;int threshold=0,index=nt+i;
        if(i<=n){name=r_name[i];units="ohm";lo=0;hi=1;threshold=1;}
        else if(i==n+1){name="H";lo=0;hi=.1;threshold=1;}
        else if(i<na-1){name=v_name[i-(n+2)];lo=-.08;hi=.08;}
        else{name="u0";lo=-.1;hi=.1;}
        support(&a->targets[index],name,units,f->alpha[i],lo,hi);
        memset(w->gradient,0,np*sizeof(double));w->gradient[index]=f->coordinate_scales[index];
        diagnose(f,&o,a,w,&a->targets[index],threshold,0,f->joint_normal[index*np+index]==0,0);
    }
    Q=exp(f->theta[n+3]);
    {
        double lo=INFINITY,hi=-INFINITY,zs[2]={.2,.95},qs[2]={.03,.1};
        for(i=0;i<2;i++)for(j=0;j<2;j++){double value=zs[i]-q/qs[j];lo=fmin(lo,value);hi=fmax(hi,value);}
        lo=fmax(0.,lo);hi=fmin(1.,hi);
        if(!isfinite(lo)||!isfinite(hi)||lo>hi)return -1;
        support(&a->targets[np],"current_soc","SOC fraction",f->theta[n+2]-q/Q,lo,hi);
        memset(w->gradient,0,np*sizeof(double));w->gradient[n+2]=f->coordinate_scales[n+2];w->gradient[n+3]=(q/Q)*f->coordinate_scales[n+3];
        diagnose(f,&o,a,w,&a->targets[np],2,0,0,0);
    }
    {
        double H=f->alpha[1+n],u=f->alpha[2+2*n];
        int amplitude_unavailable=H<=o.hysteresis_amplitude_floor_V;
        double point=amplitude_unavailable?0.:u/H;
        scm_assess_target *ht=&a->targets[nt+1+n];int forced=amplitude_unavailable||(ht->has_local_range&&ht->lower<=0);
        if(!isfinite(point))return -1;
        support(&a->targets[np+1],"h0","dimensionless",point,-1,1);
        memset(w->gradient,0,np*sizeof(double));
        if(!forced){w->gradient[nt+1+n]=-u/(H*H)*f->coordinate_scales[nt+1+n];w->gradient[nt+2+2*n]=f->coordinate_scales[nt+2+2*n]/H;}
        diagnose(f,&o,a,w,&a->targets[np+1],0,0,0,forced);
        if(amplitude_unavailable)a->targets[np+1].point_available=0;
    }
    return 0;
}
