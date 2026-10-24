#include "scm_assess.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures,checks;
#define CHECK(c,m) do{checks++;if(!(c)){fprintf(stderr,"FAIL %s\n",m);failures++;}}while(0)

static void fixture(scm_fit_result *f,int n)
{
    const double tau[]={.05,.5,5};int nt=n+4,na=2*n+3,np=nt+na,i;
    memset(f,0,sizeof(*f));
    for(i=0;i<n;i++)f->theta[i]=log(tau[i]);
    f->theta[n]=log(150);f->theta[n+1]=log(300);f->theta[n+2]=.68;f->theta[n+3]=log(.06);
    for(i=0;i<=n;i++)f->alpha[i]=.2;
    f->alpha[1+n]=.025;f->alpha[2+2*n]=.005;
    for(i=0;i<nt;i++)f->coordinate_scales[i]=i==n+2?.1:1.;
    for(i=0;i<na;i++)f->coordinate_scales[nt+i]=i<=n?.2:.03;
    for(i=0;i<np;i++)f->joint_normal[i*np+i]=1e6;
}

static void unit_tests(void)
{
    scm_fit_result f;scm_assessment a;scm_assess_workspace w;scm_assess_options o;
    int n,i,np,nt,q,z;
    scm_assess_options_default(&o);
    for(n=1;n<=3;n++) {
        fixture(&f,n);np=3*n+7;
        CHECK(scm_assess(&f,n,&o,&a,&w)==0,"assess supported mode count");
        CHECK(a.numerical_rank==np&&a.target_count==np+2,"full rank and target dimensions");
        CHECK(a.eigen_converged&&!a.matrix_invalid,"diagonal eigensolver");
        for(i=0;i<a.target_count;i++)CHECK(a.targets[i].status==SCM_ASSESS_PROVISIONAL,"full-rank fixture provisional");
    }
    n=3;nt=n+4;np=3*n+7;q=n+3;z=n+2;
    fixture(&f,n);memset(f.joint_normal,0,sizeof(f.joint_normal));f.unexcited_theta_mask=(1u<<n)|(1u<<(n+1));
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0,"zero information assessed");
    CHECK(a.numerical_rank==0,"zero information rank");
    CHECK(a.targets[q].status==SCM_ASSESS_UNRESOLVED&&!a.targets[q].has_local_range,"capacity remains unresolved at rest");
    CHECK(a.targets[q].lower==.03&&a.targets[q].upper==.1,"capacity full support retained");
    CHECK(a.targets[np].status==SCM_ASSESS_UNRESOLVED,"SOC remains unresolved at rest");
    CHECK(a.targets[n+1].status==SCM_ASSESS_UNEXCITED,"unexcited rate tag");
    fixture(&f,n);f.charge_Ah=.006;
    f.joint_normal[z*np+q]=f.joint_normal[q*np+z]=1e6;
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0,"correlated rank-deficient fixture");
    CHECK(a.numerical_rank==np-1,"one numerical null direction");
    CHECK(a.targets[z].status==SCM_ASSESS_UNRESOLVED&&a.targets[q].status==SCM_ASSESS_UNRESOLVED,"individual SOC0 and Q unresolved");
    CHECK(a.targets[np].status==SCM_ASSESS_PROVISIONAL&&a.targets[np].has_local_range,"current SOC combination observable through cross covariance");
    CHECK(a.targets[np].null_projection<1e-12,"observable target orthogonal to null space");
    fixture(&f,n);f.joint_normal[0]=-1000;
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0&&a.matrix_invalid,"indefinite Gram marked invalid");
    CHECK(a.targets[q].status==SCM_ASSESS_UNRESOLVED&&!a.targets[q].has_local_range,"invalid Gram cannot generate interval");
    fixture(&f,n);f.joint_normal[1]=.1;
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0&&a.matrix_invalid,"material asymmetry rejected diagnostically");
    fixture(&f,n);f.status=1;
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0,"optimizer limit assessed");
    for(i=0;i<a.target_count;i++)CHECK(a.targets[i].status==SCM_ASSESS_UNRESOLVED&&!a.targets[i].has_local_range,"unconverged fit does not acquire finite trusted interval");
    fixture(&f,n);f.alpha[n+1]=0;f.alpha[2+2*n]=0;
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0,"zero hysteresis amplitude assessed");
    CHECK(!a.targets[np+1].point_available&&a.targets[np+1].status==SCM_ASSESS_UNRESOLVED,"h0 unavailable at zero amplitude");
    fixture(&f,n);f.alpha[n+1]=-1e-17;f.alpha[2+2*n]=6e-17;f.status=1;
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0,"tiny amplitude roundoff assessed without division");
    CHECK(!a.targets[np+1].point_available&&!a.targets[np+1].has_local_range&&a.targets[np+1].status==SCM_ASSESS_UNRESOLVED,"tiny negative amplitude cannot produce spurious h0 point");
    fixture(&f,n);f.joint_normal[(nt+n+1)*np+nt+n+1]=.01;
    CHECK(scm_assess(&f,n,NULL,&a,&w)==0,"broad local H interval assessed");
    CHECK(a.targets[nt+n+1].has_local_range&&a.targets[nt+n+1].lower<0,"local ranges never clipped to bounds");
    CHECK(!a.targets[np+1].has_local_range,"h0 withheld when H local interval reaches zero");
    fixture(&f,n);o.linked_current_soc_chart=1;
    CHECK(scm_assess(&f,n,&o,&a,&w)==0&&!a.coordinate_chart_supported,"linked chart disclosed");
    for(i=0;i<a.target_count;i++)CHECK(a.targets[i].status==SCM_ASSESS_UNRESOLVED&&!a.targets[i].has_local_range,"linked chart not reinterpreted as unrestricted covariance");
    o.linked_current_soc_chart=0;f.joint_normal[0]=NAN;
    CHECK(scm_assess(&f,n,&o,&a,&w)==-1,"nonfinite input rejected");
}

static void number_or_null(double x,int available)
{if(available&&isfinite(x))printf("%.17g",x);else fputs("null",stdout);}

/* Standalone comparison driver. Each whitespace-delimited record contains:
 * modes,status,active_linear,active_outer,unexcited_mask,conditioned,linked,q;
 * then theta[nt],alpha[na],scales[np],Gram[np*np]. No optimization is run.
 */
static int driver(void)
{
    int n,got,nt,na,np,i,rc;scm_fit_result f;scm_assessment a;scm_assess_workspace w;scm_assess_options o;
    while(1) {
        memset(&f,0,sizeof(f));scm_assess_options_default(&o);
        got=scanf("%d %d %d %d %u %d %d %lf",&n,&f.status,&f.active_linear_constraints,&f.active_outer_bounds,
                  &f.unexcited_theta_mask,&o.conditioned_fit,&o.linked_current_soc_chart,&f.charge_Ah);
        if(got==EOF)return 0;
        if(got!=8||n<1||n>3)return 2;
        nt=n+4;na=2*n+3;np=nt+na;
        for(i=0;i<nt;i++)if(scanf("%lf",&f.theta[i])!=1)return 2;
        for(i=0;i<na;i++)if(scanf("%lf",&f.alpha[i])!=1)return 2;
        for(i=0;i<np;i++)if(scanf("%lf",&f.coordinate_scales[i])!=1)return 2;
        for(i=0;i<np*np;i++)if(scanf("%lf",&f.joint_normal[i])!=1)return 2;
        rc=scm_assess(&f,n,&o,&a,&w);
        if(rc){printf("{\"error\":%d}\n",rc);continue;}
        printf("{\"rank\":%d,\"matrix_invalid\":%s,\"chart_supported\":%s,\"eigenvalues\":[",
               a.numerical_rank,a.matrix_invalid?"true":"false",a.coordinate_chart_supported?"true":"false");
        for(i=0;i<np;i++){if(i)putchar(',');printf("%.17g",a.eigenvalues[i]);}
        fputs("],\"targets\":{",stdout);
        for(i=0;i<a.target_count;i++) {
            const scm_assess_target *t=&a.targets[i];
            if(i)putchar(',');
            printf("\"%s\":{\"status\":\"%s\",\"point\":",t->name,scm_assess_status_name(t->status));
            number_or_null(t->point,t->point_available);
            printf(",\"local_range\":[%.17g,%.17g],\"has_local_range\":%s,\"null_projection\":%.17g,\"local_standard_deviation\":",
                   t->lower,t->upper,t->has_local_range?"true":"false",t->null_projection);
            number_or_null(t->local_standard_deviation,t->has_local_range);
            fputs(",\"local_halfwidth\":",stdout);number_or_null(t->local_halfwidth,t->has_local_range);
            fputs(",\"relative_halfwidth\":",stdout);number_or_null(t->relative_halfwidth,t->has_relative_halfwidth);
            fputs(",\"passes_local_precision\":",stdout);
            if(t->passes_local_precision<0)fputs("null",stdout);else fputs(t->passes_local_precision?"true":"false",stdout);
            printf(",\"eligible_for_profile_check\":%s,\"reasons\":%u}",t->eligible_for_profile_check?"true":"false",t->reasons);
        }
        fputs("}}\n",stdout);
    }
}
int main(int argc,char **argv)
{
    if(argc>1&&!strcmp(argv[1],"--driver"))return driver();
    unit_tests();
    printf("{\"test\":\"scm_assess_c\",\"checks\":%d,\"failures\":%d,\"workspace_bytes\":%zu,\"output_bytes\":%zu,\"options_bytes\":%zu}\n",
           checks,failures,sizeof(scm_assess_workspace),sizeof(scm_assessment),sizeof(scm_assess_options));
    return failures?1:0;
}
