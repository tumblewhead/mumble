#include "scm_compact_assess.h"
#include <float.h>
#include <math.h>
#include <string.h>

/* Same maximum-pivot rotations, scaling, ordering and convergence criterion as
 * scm_assess.c. Applying each rotation to two target gradients replaces the
 * full eigenvector matrix. Rounding differs from V^T*g formed after all the
 * rotations; the comparison tests quantify that finite arithmetic difference.
 */
static int jacobi_targets(double *a,double *g,int n,double *eigenvalues)
{
    int i,j,k,iteration,p=0,q=0;double scale=0;
    for(i=0;i<n*n;i++)scale=fmax(scale,fabs(a[i]));
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
            for(k=0;k<2;k++) {
                double gp=g[k*n+p],gq=g[k*n+q];
                g[k*n+p]=c*gp-s*gq;g[k*n+q]=s*gp+c*gq;
            }
        }
    }
    for(i=0;i<n;i++)eigenvalues[i]=a[i*n+i]*scale;
    for(i=0;i<n;i++) {
        int smallest=i;
        for(j=i+1;j<n;j++)if(eigenvalues[j]<eigenvalues[smallest])smallest=j;
        if(smallest!=i) {
            double x=eigenvalues[i];eigenvalues[i]=eigenvalues[smallest];eigenvalues[smallest]=x;
            for(k=0;k<2;k++){x=g[k*n+i];g[k*n+i]=g[k*n+smallest];g[k*n+smallest]=x;}
        }
    }
    return iteration<80*n*n;
}

/* Destroy the snapshot in the explicit union, keeping only its joint Gram.
 * Parameter dimensions below 16 still use the original 17-wide QR packing.
 *
 * 1. Check the same residual/gradient finite domain as factor_normal, without
 *    retaining those outputs. Descending Gram rows/columns leave every needed
 *    QR row k<i untouched, and overwrite R[i,i] last in its row.
 * 2. Copy forward into (d+1)-wide packed storage. Destination <= source for
 *    d<=16, so later unread source elements survive.
 * 3. Expand backward: dense upper index minus packed index is i*(i-1)/2>=0;
 *    the mirrored lower index is no smaller. Both writes preserve unread
 *    earlier packed entries. No extra factor or dense matrix is allocated.
 */
static int snapshot_to_gram(scm_compact_assess_workspace *w,int d)
{
    double *p=w->factor_matrix.snapshot.upper;
    double norm=0;
    int i,j,k;
    for(i=0;i<d;i++) {
        double gradient=0;
        for(k=0;k<=i;k++)gradient-=p[scm_evidence_packed_index((size_t)k,(size_t)i)]*
            p[scm_evidence_packed_index((size_t)k,(size_t)d)];
        if(!isfinite(gradient))return -1;
    }
    for(i=0;i<=d;i++)norm=hypot(norm,p[scm_evidence_packed_index((size_t)i,(size_t)d)]);
    if(!isfinite(.5*norm*norm))return -1;
    for(i=d-1;i>=0;i--)for(j=d-1;j>=i;j--) {
        double h=0;
        for(k=0;k<=i;k++)h+=p[scm_evidence_packed_index((size_t)k,(size_t)j)]*
            p[scm_evidence_packed_index((size_t)k,(size_t)i)];
        if(!isfinite(h))return -1;
        /* Original scm_assess symmetrizes even its already symmetric input.
         * Keep that operation, including its subnormal rounding behavior. */
        p[scm_evidence_packed_index((size_t)i,(size_t)j)]=.5*h+.5*h;
    }
    for(i=0;i<d;i++)for(j=i;j<d;j++) {
        size_t packed=(size_t)i*(2*(size_t)(d+1)-(size_t)i-1)/2+(size_t)j;
        p[packed]=p[scm_evidence_packed_index((size_t)i,(size_t)j)];
    }
    for(i=d-1;i>=0;i--)for(j=d-1;j>=i;j--) {
        size_t packed=(size_t)i*(2*(size_t)(d+1)-(size_t)i-1)/2+(size_t)j;
        double h=p[packed];
        w->factor_matrix.matrix[i*d+j]=w->factor_matrix.matrix[j*d+i]=h;
    }
    return 0;
}

static void support(scm_assess_target *t,const char *name,const char *units,
                    double point,double lo,double hi)
{
    memset(t,0,sizeof(*t));t->name=name;t->units=units;t->point=point;t->point_available=1;
    t->lower=t->support_lower=lo;t->upper=t->support_upper=hi;t->status=SCM_ASSESS_UNRESOLVED;
}

static void diagnose(const scm_assess_options *o,const scm_compact_assessment *a,
    const double *eigenvalues,const double *projection,double norm2,
    scm_assess_target *target,int threshold,int logarithmic)
{
    int i,np=a->joint_dimension;double null2=0,variance=0;
    double sd=0,half=0,ratio=0,lo=0,hi=0;int local=0,passes=-1,relative_available=0;
    int null_direction,unavailable;unsigned reason=0;
    for(i=0;i<np;i++) {
        if(eigenvalues[i]>a->eigen_cutoff)variance+=projection[i]*projection[i]/eigenvalues[i];
        else null2+=projection[i]*projection[i];
    }
    target->null_projection=norm2>0?fmax(0.,fmin(1.,null2/norm2)):1.;
    null_direction=target->null_projection>o->null_projection_tol;
    if(o->linked_current_soc_chart)reason|=SCM_ASSESS_REASON_LINKED_CHART;
    else if(a->matrix_invalid) {
        if(!a->eigen_converged)reason|=SCM_ASSESS_REASON_EIGEN_NONCONVERGENCE;
        for(i=0;i<np;i++)if(eigenvalues[i]<-fmax(a->eigen_cutoff,1e-12))reason|=SCM_ASSESS_REASON_INDEFINITE;
    } else if(null_direction)reason|=SCM_ASSESS_REASON_NULL_SPACE;
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
    if(a->optimizer_status!=0)reason|=SCM_ASSESS_REASON_OPTIMIZER;
    if(a->active_constraints)reason|=SCM_ASSESS_REASON_ACTIVE_CONSTRAINT;
    if(o->conditioned_fit||o->linked_current_soc_chart)reason|=SCM_ASSESS_REASON_CONDITIONED;
    unavailable=o->linked_current_soc_chart||a->matrix_invalid||null_direction||!local||a->optimizer_status!=0;
    target->reasons=reason;target->active_constraints_present=a->active_constraints!=0;
    target->conditioned_fit=o->conditioned_fit||o->linked_current_soc_chart;
    target->has_local_range=!unavailable;target->has_relative_halfwidth=!unavailable&&relative_available;
    target->passes_local_precision=unavailable?0:passes;
    target->eligible_for_profile_check=!unavailable&&passes==1;
    if(!unavailable) {
        target->lower=lo;target->upper=hi;target->local_standard_deviation=sd;
        target->local_halfwidth=half;target->relative_halfwidth=ratio;
    }
    target->status=unavailable||passes==0?SCM_ASSESS_UNRESOLVED:SCM_ASSESS_PROVISIONAL;
}

int scm_compact_assess(const scm_compact_evidence *e,int optimizer_status,
    int active_constraints,const scm_assess_options *input,
    scm_compact_assessment *a,scm_compact_assess_workspace *w)
{
    scm_assess_options defaults;
    const scm_assess_options *o=input;
    const scm_evidence_config *c;
    int n,nt,na,d,i,j;
    double q,Q,lo=INFINITY,hi=-INFINITY,largest,norm_soc=0,norm_Q=0;
    double *g;
    if(!e||!e->config||!a||!w)return -1;
    c=e->config;n=c->modes;nt=scm_model_ntheta(n);na=scm_model_nalpha(n);d=nt+na;
    if(!nt||e->history.dim!=d||e->event.dim!=d)return -1;
    if(!o){scm_assess_options_default(&defaults);o=&defaults;}
    if(!isfinite(o->relative_halfwidth)||o->relative_halfwidth<=0||!isfinite(o->soc_halfwidth)||o->soc_halfwidth<=0||
       !isfinite(o->eigen_rtol)||o->eigen_rtol<=0||o->eigen_rtol>=1||!isfinite(o->null_projection_tol)||o->null_projection_tol<=0||o->null_projection_tol>=1||
       !isfinite(o->sigma_multiplier)||o->sigma_multiplier<=0||!isfinite(o->hysteresis_amplitude_floor_V)||o->hysteresis_amplitude_floor_V<0)return -1;
    q=e->model.charge_Ah;
    if(!isfinite(q))return -1;
    for(i=0;i<nt;i++)if(!isfinite(c->theta[i]))return -1;
    for(i=0;i<na;i++)if(!isfinite(c->alpha[i]))return -1;
    for(i=0;i<d;i++)if(!isfinite(c->scale[i])||c->scale[i]<=0)return -1;
    for(i=0;i<nt;i++)if(i!=n+2&&(!isfinite(exp(c->theta[i]))||exp(c->theta[i])<=0))return -1;
    Q=exp(c->theta[n+3]);
    for(i=0;i<2;i++)for(j=0;j<2;j++) {
        double value=(i?.95:.2)-q/(j?.1:.03);lo=fmin(lo,value);hi=fmax(hi,value);
    }
    lo=fmax(0.,lo);hi=fmin(1.,hi);
    if(!isfinite(lo)||!isfinite(hi)||lo>hi)return -1;
    if(scm_compact_evidence_snapshot_into(e,&w->factor_matrix.snapshot,w->row_projection.qrrow))return -1;
    if(snapshot_to_gram(w,d))return -1;
    memset(a,0,sizeof(*a));a->modes=n;a->joint_dimension=d;
    a->optimizer_status=optimizer_status;a->active_constraints=active_constraints;
    a->coordinate_chart_supported=!o->linked_current_soc_chart;
    support(&a->current_soc,"current_soc","SOC fraction",c->theta[n+2]-q/Q,lo,hi);
    support(&a->capacity_Q_Ah,"Q_Ah","Ah",Q,.03,.1);
    g=w->row_projection.target_projection;
    memset(g,0,(size_t)2*d*sizeof(double));
    g[n+2]=c->scale[n+2];g[n+3]=(q/Q)*c->scale[n+3];
    g[d+n+3]=c->scale[n+3];
    for(i=0;i<d;i++){norm_soc+=g[i]*g[i];norm_Q+=g[d+i]*g[d+i];}
    if(!isfinite(norm_soc)||!isfinite(norm_Q))return -1;
    a->eigen_converged=jacobi_targets(w->factor_matrix.matrix,g,d,w->eigenvalues);
    largest=fmax(0.,w->eigenvalues[d-1]);a->eigen_cutoff=largest*o->eigen_rtol;
    a->matrix_invalid=!a->eigen_converged;
    for(i=0;i<d;i++) {
        if(!isfinite(w->eigenvalues[i]))a->matrix_invalid=1;
        if(w->eigenvalues[i]>a->eigen_cutoff)a->numerical_rank++;
        if(w->eigenvalues[i]<-fmax(a->eigen_cutoff,1e-12))a->matrix_invalid=1;
    }
    diagnose(o,a,w->eigenvalues,g,norm_soc,&a->current_soc,2,0);
    diagnose(o,a,w->eigenvalues,g+d,norm_Q,&a->capacity_Q_Ah,1,1);
    return 0;
}
