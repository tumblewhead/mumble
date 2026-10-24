/* Reconstructed host CLI. Source identity with the lost implementation is not
 * asserted. Input remains sample-indexed, with point observations at interval
 * end; a prefix reads only its own samples. No truth metadata is loaded. */
#include "scm_estimator.h"
#include "scm_assess.h"
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *space(const char *p){while(isspace((unsigned char)*p))p++;return p;}
static int integer(const char *p,size_t *v)
{
    char *end;unsigned long long x;p=space(p);if(!*p||*p=='-')return -1;
    errno=0;x=strtoull(p,&end,10);
    if(errno||end==p||*space(end)||x>SIZE_MAX)return -1;
    *v=(size_t)x;return 0;
}
static int real(const char *p,double *v)
{
    char *end;errno=0;*v=strtod(p,&end);
    return errno||end==p||*space(end)||!isfinite(*v)?-1:0;
}
static int field(const char **p,int last,double *v)
{
    char *end;const char *start=*p;errno=0;*v=strtod(start,&end);
    if(errno||end==start||!isfinite(*v))return -1;
    *p=space(end);
    if(last)return **p?-1:0;
    if(**p!=',')return -1;
    (*p)++;return 0;
}
static void help(FILE *f)
{
    fputs("Usage: scm_estimator --data FILE [options]\n"
          "  --method full|tangent|hybrid   Observation representation (default full)\n"
          "  --modes 1|2|3                 Foster branches (default 3)\n"
          "  --starts N                    Nonlinear starts\n"
          "  --max-iter N                  Iteration limit per start\n"
          "  --sigma VALUE                 Known iid voltage sigma in V\n"
          "  --case ID                     JSON identifier\n"
          "  --prefix N                    Read only the first N observations\n"
          "  --initial a,b,...             Exactly modes+4 transformed theta values\n"
          "  --fixed INDEX VALUE           Fix transformed theta; repeatable\n"
          "  --fixed-alpha INDEX VALUE     Fix physical linear coordinate; repeatable\n"
          "  --fixed-current-soc VALUE     Fix SOC at the end of the retained prefix\n"
          "  --ocv FILE                    Known PWL table with header z,voltage\n"
          "  --help                        This help\n"
          "Data header: sample_index,dt_s,current_A,voltage_V\n"
          "Indices start at0 and remain contiguous. Point voltage is at interval END.\n"
          "theta=log(tau_i),log(gamma_plus),log(gamma_minus),z0,log(Q_Ah).\n"
          "alpha=R0,R_i,H,v_i0,u0=H*h0. Fixed current SOC couples z0 to Q and charge.\n"
          "Joint-normal diagnostics describe likelihood linearization before damping, not a posterior.\n"
          "Default OCV is illustrative, not measured:3+1.15*z+.08*tanh(8*(z-.5)).\n"
          "Host reference replays retained data; no bounded-memory online claim.\n",f);
}
static int header(FILE *f,const char *expected,const char *path)
{
    char line[512];size_t n;
    if(!fgets(line,sizeof(line),f)){fprintf(stderr,"Cannot read CSV header:%s\n",path);return -1;}
    n=strlen(line);while(n&&(line[n-1]=='\n'||line[n-1]=='\r'))line[--n]=0;
    if(strcmp(line,expected)){fprintf(stderr,"Invalid header in %s; expected %s\n",path,expected);return -1;}
    return 0;
}
static int load_data(const char *path,size_t prefix,int limited,scm_sample **out,size_t *count)
{
    FILE *f=fopen(path,"r");scm_sample *a=NULL;size_t n=0,cap=0;char line[4096];int rc=-1;
    if(!f){fprintf(stderr,"Cannot open %s:%s\n",path,strerror(errno));return -1;}
    if(header(f,"sample_index,dt_s,current_A,voltage_V",path))goto done;
    while((!limited||n<prefix)&&fgets(line,sizeof(line),f)) {
        const char *p=space(line);char *end;unsigned long long idx;scm_sample s;
        if(!strchr(line,'\n')&&!feof(f)){fprintf(stderr,"Data row%zu too long\n",n+2);goto done;}
        if(!*p||*p=='-'){fprintf(stderr,"Invalid data index at row%zu\n",n+2);goto done;}
        errno=0;idx=strtoull(p,&end,10);p=space(end);
        if(errno||end==space(line)||idx>SIZE_MAX||(size_t)idx!=n||*p!=','){
            fprintf(stderr,"Data row%zu requires contiguous index%zu\n",n+2,n);goto done;
        }
        p++;
        if(field(&p,0,&s.dt)||s.dt<0||field(&p,0,&s.current)||field(&p,1,&s.voltage)){
            fprintf(stderr,"Invalid finite dt/current/voltage at data row%zu\n",n+2);goto done;
        }
        if(n==cap) {
            size_t next;scm_sample *b;
            if(cap>SIZE_MAX/2){fprintf(stderr,"Data size overflow\n");goto done;}
            next=cap?2*cap:1024;if(limited&&next>prefix)next=prefix;
            if(next>SIZE_MAX/sizeof(*a)){fprintf(stderr,"Data byte count overflow\n");goto done;}
            b=realloc(a,next*sizeof(*a));if(!b){fprintf(stderr,"Data allocation failed\n");goto done;}
            a=b;cap=next;
        }
        a[n++]=s;
    }
    if(ferror(f)||!n||(limited&&n!=prefix)){fprintf(stderr,"Data read failure or insufficient rows:%zu\n",n);goto done;}
    if(cap!=n){scm_sample *b=realloc(a,n*sizeof(*a));if(!b){fprintf(stderr,"Data resize failed\n");goto done;}a=b;}
    *out=a;*count=n;a=NULL;rc=0;
done:
    free(a);
    if(fclose(f)&&rc==0){free(*out);*out=NULL;fprintf(stderr,"Data close failed\n");rc=-1;}
    return rc;
}
static int load_ocv(const char *path,scm_ocv *c,double **zo,double **uo)
{
    FILE *f=fopen(path,"r");double *z=NULL,*u=NULL;size_t n=0,cap=0;char line[4096];int rc=-1;
    if(!f){fprintf(stderr,"Cannot open OCV:%s\n",path);return -1;}
    if(header(f,"z,voltage",path))goto done;
    while(fgets(line,sizeof(line),f)) {
        const char *p=line;double zv,uv;
        if((!strchr(line,'\n')&&!feof(f))||field(&p,0,&zv)||field(&p,1,&uv)){
            fprintf(stderr,"Invalid OCV row%zu\n",n+2);goto done;
        }
        if(n==cap) {
            size_t next;double *b;
            if(cap>SIZE_MAX/2){fprintf(stderr,"OCV size overflow\n");goto done;}
            next=cap?2*cap:64;if(next>SIZE_MAX/sizeof(double)){fprintf(stderr,"OCV bytes overflow\n");goto done;}
            b=realloc(z,next*sizeof(double));if(!b){fprintf(stderr,"OCV labels allocation failed\n");goto done;}z=b;
            b=realloc(u,next*sizeof(double));if(!b){fprintf(stderr,"OCV values allocation failed\n");goto done;}u=b;cap=next;
        }
        z[n]=zv;u[n++]=uv;
    }
    if(ferror(f)||n<2){fprintf(stderr,"OCV requires two readable rows\n");goto done;}
    if(cap!=n) {
        double *b=realloc(z,n*sizeof(double));if(!b){fprintf(stderr,"OCV resize failed\n");goto done;}z=b;
        b=realloc(u,n*sizeof(double));if(!b){fprintf(stderr,"OCV resize failed\n");goto done;}u=b;
    }
    c->n=n;c->z=z;c->u=u;
    if(scm_ocv_validate(c)){fprintf(stderr,"OCV labels must increase in[0,1]; values must not decrease\n");goto done;}
    *zo=z;*uo=u;z=NULL;u=NULL;rc=0;
done:
    free(z);free(u);
    if(fclose(f)&&rc==0){free(*zo);free(*uo);*zo=NULL;*uo=NULL;fprintf(stderr,"OCV close failed\n");rc=-1;}
    return rc;
}
static void string(const char *s)
{
    const unsigned char *p=(const unsigned char*)s;putchar('"');
    while(*p){switch(*p){
        case '"':fputs("\\\"",stdout);break;case '\\':fputs("\\\\",stdout);break;
        case '\n':fputs("\\n",stdout);break;case '\r':fputs("\\r",stdout);break;
        case '\t':fputs("\\t",stdout);break;case '\b':fputs("\\b",stdout);break;case '\f':fputs("\\f",stdout);break;
        default:if(*p<0x20)printf("\\u%04x",(unsigned)*p);else putchar(*p);
    }p++;}putchar('"');
}
static void number(double v){if(isfinite(v))printf("%.17g",v);else fputs("null",stdout);}
static void named(const char *key,double v){printf(",\"%s\":",key);number(v);}
static void assessment_reasons(const scm_assess_target *t)
{
    static const struct {unsigned flag;const char *text;} reasons[]={
        {SCM_ASSESS_REASON_HYSTERESIS,"Hysteresis amplitude is zero, near zero, or has a local range reaching zero; h0 is unresolved."},
        {SCM_ASSESS_REASON_INDEFINITE,"Likelihood matrix is materially indefinite; local inversion is not trusted."},
        {SCM_ASSESS_REASON_ASYMMETRIC,"Likelihood matrix is materially asymmetric; local inversion is not trusted."},
        {SCM_ASSESS_REASON_UNEXCITED,"The retained history supplies no excitation for this direction; physical support is retained."},
        {SCM_ASSESS_REASON_NULL_SPACE,"Target has a numerical likelihood null-space component; no pseudoinverse interval is reported."},
        {SCM_ASSESS_REASON_NUMERICAL_RANGE,"Local numeric range is not finite; full support is retained."},
        {SCM_ASSESS_REASON_PRECISION,"Finite local range exceeds the declared precision threshold."},
        {SCM_ASSESS_REASON_OPTIMIZER,"Optimizer did not report convergence; point remains visible but local uncertainty is untrusted."},
        {SCM_ASSESS_REASON_ACTIVE_CONSTRAINT,"Active constraints require a nonlinear profile check of the local approximation."},
        {SCM_ASSESS_REASON_CONDITIONED,"Coordinates were fixed during fitting; conditional optimization is not independent identification."},
        {SCM_ASSESS_REASON_SUPPORT_CROSSING,"Raw local range crosses supplied support and has not been clipped to improve precision."},
        {SCM_ASSESS_REASON_EIGEN_NONCONVERGENCE,"Symmetric eigenvalue iteration did not converge; local ranges are withheld."},
        {SCM_ASSESS_REASON_LINKED_CHART,"The linked current-SOC chart cannot be reinterpreted as unrestricted target uncertainty; ranges remain unresolved."}
    };
    size_t i;int emitted=0;putchar('[');
    if(t->has_local_range&&t->passes_local_precision==1){string("Local precision screen passed; nonlinear profile confirmation is still required.");emitted=1;}
    else if(t->has_local_range&&t->passes_local_precision<0){string("Finite local nuisance-coordinate diagnostic; no precision threshold is declared.");emitted=1;}
    for(i=0;i<sizeof(reasons)/sizeof(reasons[0]);i++)if(t->reasons&reasons[i].flag){if(emitted)putchar(',');string(reasons[i].text);emitted=1;}
    putchar(']');
}
static void assessment_json(const scm_fit_result *fit,int modes,const scm_fit_options *fit_options)
{
    scm_assessment a;scm_assess_workspace workspace;scm_assess_options options;int rc,i;
    scm_assess_options_default(&options);
    options.conditioned_fit=fit_options->fixed_mask||fit_options->fixed_alpha_mask||fit_options->has_current_soc;
    options.linked_current_soc_chart=fit_options->has_current_soc;
    rc=scm_assess(fit,modes,&options,&a,&workspace);
    fputs(",\"assessment\":{\"implementation\":\"C99\",\"diagnostic_only\":true,\"coverage_certificate\":false",stdout);
    if(rc){printf(",\"status\":\"unavailable\",\"error_code\":%d,\"reason\":",rc);string("Assessment rejected invalid inputs; no precision claim is available.");putchar('}');return;}
    printf(",\"coordinate_chart_supported\":%s,\"joint_dimension\":%d,\"numerical_rank\":%d,\"matrix_invalid\":%s,\"eigen_converged\":%s,\"workspace_bytes\":%zu,\"output_bytes\":%zu,\"options_bytes\":%zu",
           a.coordinate_chart_supported?"true":"false",a.joint_dimension,a.numerical_rank,a.matrix_invalid?"true":"false",a.eigen_converged?"true":"false",
           sizeof(workspace),sizeof(a),sizeof(options));
    named("eigen_cutoff",a.eigen_cutoff);named("matrix_relative_asymmetry",a.matrix_relative_asymmetry);
    fputs(",\"uncertainty_semantics\":",stdout);string("Undamped joint likelihood linearization. Null directions retain physical support. Finite two-sigma local ranges are provisional, not confidence-coverage certificates.");
    printf(",\"thresholds\":{\"relative_halfwidth\":%.17g,\"soc_halfwidth_fraction\":%.17g,\"eigen_rtol\":%.17g,\"null_projection_tolerance\":%.17g,\"sigma_multiplier\":%.17g},\"eigenvalues\":[",
           options.relative_halfwidth,options.soc_halfwidth,options.eigen_rtol,options.null_projection_tol,options.sigma_multiplier);
    for(i=0;i<a.joint_dimension;i++){if(i)putchar(',');number(a.eigenvalues[i]);}
    fputs("],\"parameters\":{",stdout);
    for(i=0;i<a.target_count;i++) {
        const scm_assess_target *t=&a.targets[i];if(i)putchar(',');string(t->name);fputs(":{\"point\":",stdout);
        if(t->point_available)number(t->point);else fputs("null",stdout);
        fputs(",\"units\":",stdout);string(t->units);fputs(",\"status\":",stdout);string(scm_assess_status_name(t->status));
        fputs(",\"local_range\":[",stdout);number(t->lower);putchar(',');number(t->upper);fputs("],\"range_kind\":",stdout);
        string(t->has_local_range?"untruncated_local_two_sigma":"prior_support");
        fputs(",\"prior_support\":[",stdout);number(t->support_lower);putchar(',');number(t->support_upper);putchar(']');
        named("null_projection",t->null_projection);
        fputs(",\"local_standard_deviation\":",stdout);if(t->has_local_range)number(t->local_standard_deviation);else fputs("null",stdout);
        fputs(",\"local_halfwidth\":",stdout);if(t->has_local_range)number(t->local_halfwidth);else fputs("null",stdout);
        fputs(",\"relative_halfwidth\":",stdout);if(t->has_relative_halfwidth)number(t->relative_halfwidth);else fputs("null",stdout);
        fputs(",\"passes_local_precision\":",stdout);if(t->passes_local_precision<0)fputs("null",stdout);else fputs(t->passes_local_precision?"true":"false",stdout);
        printf(",\"eligible_for_profile_check\":%s,\"active_constraints_present\":%s,\"conditioned_fit\":%s,\"reason_flags\":%u,\"reasons\":",
               t->eligible_for_profile_check?"true":"false",t->active_constraints_present?"true":"false",t->conditioned_fit?"true":"false",t->reasons);
        assessment_reasons(t);putchar('}');
    }
    fputs("}}",stdout);
}
static void output(const scm_fit_result *r,const char *id,scm_method method,int modes,double sigma,const scm_ocv *c,const scm_fit_options *o)
{
    int j,np=scm_model_ntheta(modes)+scm_model_nalpha(modes);
    fputs("{\"case_id\":",stdout);string(id);fputs(",\"method\":",stdout);string(scm_method_name(method));
    printf(",\"modes\":%d,\"sigma_V\":",modes);number(sigma);
    printf(",\"ocv_kind\":\"%s\",\"ocv_table_rows\":%zu,\"has_initial\":%s,\"fixed_mask\":%u,\"fixed_alpha_mask\":%u,\"has_current_soc\":%s,\"fixed_current_soc\":",
           c?"pwl_table":"illustrative_known_curve",c?c->n:(size_t)0,o->has_initial?"true":"false",o->fixed_mask,o->fixed_alpha_mask,o->has_current_soc?"true":"false");
    if(o->has_current_soc)number(o->current_soc);else fputs("null",stdout);
    fputs(",\"theta\":[",stdout);
    for(j=0;j<scm_model_ntheta(modes);j++){if(j)putchar(',');number(r->theta[j]);}
    fputs("],\"alpha\":[",stdout);for(j=0;j<scm_model_nalpha(modes);j++){if(j)putchar(',');number(r->alpha[j]);}putchar(']');
    named("objective",r->objective);named("objective_full",r->objective_full);named("voltage_rmse",r->voltage_rmse);
    named("elapsed_cpu_s",r->elapsed_cpu_s);named("projected_gradient",r->projected_gradient);named("max_inner_kkt",r->max_inner_kkt);
    printf(",\"status\":%d,\"termination_reason\":%d,\"iterations\":%d,\"evaluations\":%d,\"converged_starts\":%d,\"starts\":%d,\"active_linear_constraints\":%d,\"active_outer_bounds\":%d",
           r->status,r->termination_reason,r->iterations,r->evaluations,r->converged_starts,r->starts,r->active_linear_constraints,r->active_outer_bounds);
    printf(",\"samples\":%zu,\"features\":%zu,\"blocks\":%zu,\"data_bytes\":%zu,\"basis_bytes\":%zu,\"payload_bytes\":%zu,\"workspace_bytes\":%zu,\"retained_bytes\":%zu,\"setup_peak_bytes\":%zu",
           r->samples,r->features,r->blocks,r->data_bytes,r->basis_bytes,r->payload_bytes,r->workspace_bytes,r->retained_bytes,r->setup_peak_bytes);
    named("basis_seconds",r->basis_seconds);named("basis_max_orthogonality",r->basis_max_orthogonality);named("max_discarded_column_norm",r->max_discarded_column_norm);
    named("elapsed_physical_s",r->elapsed_physical_s);named("charge_Ah",r->charge_Ah);
    printf(",\"unexcited_theta_mask\":%u,\"joint_normal_dimension\":%d,\"joint_normal_semantics\":",r->unexcited_theta_mask,np);
    string("Scaled likelihood Jacobian Gram matrix before damping and Schur reduction; not a posterior");
    fputs(",\"joint_normal_coordinates\":",stdout);string("Scaled theta followed by scaled alpha; packed row-major");
    fputs(",\"coordinate_scales\":[",stdout);
    for(j=0;j<np;j++){if(j)putchar(',');number(r->coordinate_scales[j]);}
    fputs("],\"joint_normal\":[",stdout);
    for(j=0;j<np*np;j++){if(j)putchar(',');number(r->joint_normal[j]);}
    putchar(']');
    assessment_json(r,modes,o);
    fputs("}\n",stdout);
}
int main(int argc,char **argv)
{
    const char *data=NULL,*ocv=NULL,*initial=NULL,*id="unnamed";scm_method method=SCM_FULL;
    scm_fit_options options;scm_fit_result result;scm_problem *problem=NULL;scm_sample *samples=NULL;
    scm_ocv curve={0,NULL,NULL};double *z=NULL,*u=NULL,sigma=.001;size_t prefix=0,n=0;
    int modes=3,limited=0,j,rc=EXIT_FAILURE;
    scm_fit_options_default(&options);memset(&result,0,sizeof(result));
    for(j=1;j<argc;j++) {
        const char *o=argv[j];size_t v;
        if(!strcmp(o,"--help")){help(stdout);return EXIT_SUCCESS;}
        if(j+1>=argc){fprintf(stderr,"Missing argument:%s\n",o);goto done;}
        if(!strcmp(o,"--data"))data=argv[++j];
        else if(!strcmp(o,"--case"))id=argv[++j];
        else if(!strcmp(o,"--ocv"))ocv=argv[++j];
        else if(!strcmp(o,"--initial"))initial=argv[++j];
        else if(!strcmp(o,"--method")) {
            const char *m=argv[++j];
            if(!strcmp(m,"full"))method=SCM_FULL;else if(!strcmp(m,"tangent"))method=SCM_TANGENT;else if(!strcmp(m,"hybrid"))method=SCM_HYBRID;
            else{fprintf(stderr,"Unknown method:%s\n",m);goto done;}
        } else if(!strcmp(o,"--modes")) {
            if(integer(argv[++j],&v)||v<1||v>SCM_MAX_MODES){fprintf(stderr,"--modes must be1..%d\n",SCM_MAX_MODES);goto done;}modes=(int)v;
        } else if(!strcmp(o,"--starts")||!strcmp(o,"--max-iter")) {
            if(integer(argv[++j],&v)||!v||v>INT_MAX){fprintf(stderr,"%s requires a positive integer\n",o);goto done;}
            if(!strcmp(o,"--starts"))options.starts=(int)v;else options.max_iterations=(int)v;
        } else if(!strcmp(o,"--prefix")) {
            if(integer(argv[++j],&prefix)||!prefix){fprintf(stderr,"--prefix requires a positive count\n");goto done;}limited=1;
        } else if(!strcmp(o,"--sigma")) {
            if(real(argv[++j],&sigma)||sigma<=0){fprintf(stderr,"--sigma requires a finite positive value\n");goto done;}
        } else if(!strcmp(o,"--fixed")) {
            double value;
            if(j+2>=argc||integer(argv[++j],&v)||v>=SCM_MAX_THETA||real(argv[++j],&value)){
                fprintf(stderr,"--fixed requires INDEX VALUE in transformed theta coordinates\n");goto done;
            }
            if(options.fixed_mask&(1u<<v)){fprintf(stderr,"Repeated fixed index%zu\n",v);goto done;}
            options.fixed_mask|=1u<<v;options.fixed_theta[v]=value;
        } else if(!strcmp(o,"--fixed-alpha")) {
            double value;
            if(j+2>=argc||integer(argv[++j],&v)||v>=SCM_MAX_ALPHA||real(argv[++j],&value)){
                fprintf(stderr,"--fixed-alpha requires INDEX VALUE in physical alpha coordinates\n");goto done;
            }
            if(options.fixed_alpha_mask&(1u<<v)){fprintf(stderr,"Repeated fixed alpha index%zu\n",v);goto done;}
            options.fixed_alpha_mask|=1u<<v;options.fixed_alpha[v]=value;
        } else if(!strcmp(o,"--fixed-current-soc")) {
            if(options.has_current_soc||real(argv[++j],&options.current_soc)||options.current_soc<0||options.current_soc>1){
                fprintf(stderr,"--fixed-current-soc requires one finite SOC in[0,1]\n");goto done;
            }
            options.has_current_soc=1;
        } else{fprintf(stderr,"Unknown option:%s\n",o);goto done;}
    }
    if(!data){fprintf(stderr,"--data is required\n");help(stderr);goto done;}
    if(options.fixed_mask>>scm_model_ntheta(modes)){fprintf(stderr,"Fixed index exceeds model dimension\n");goto done;}
    if(options.fixed_alpha_mask>>scm_model_nalpha(modes)){fprintf(stderr,"Fixed alpha index exceeds model dimension\n");goto done;}
    if(options.has_current_soc&&(options.fixed_mask&(1u<<(modes+2)))){
        fprintf(stderr,"--fixed-current-soc cannot be combined with fixed z0\n");goto done;
    }
    if(initial) {
        const char *p=initial;int nt=scm_model_ntheta(modes);
        for(j=0;j<nt;j++)if(field(&p,j==nt-1,&options.initial_theta[j])){
            fprintf(stderr,"--initial requires exactly%d finite coordinates\n",nt);goto done;
        }
        options.has_initial=1;
    }
    if(ocv&&load_ocv(ocv,&curve,&z,&u))goto done;
    if(load_data(data,prefix,limited,&samples,&n))goto done;
    problem=scm_problem_create(samples,n,modes,sigma,ocv?&curve:NULL,method);
    if(!problem){fprintf(stderr,"Problem initialization failed; check model domain, supported method and memory\n");goto done;}
    {int fit_rc=scm_fit(problem,&options,&result);if(fit_rc){fprintf(stderr,"Estimator operational failure:%d\n",fit_rc);goto done;}}
    if(!isfinite(result.objective)||!isfinite(result.objective_full)||!isfinite(result.voltage_rmse)){
        fprintf(stderr,"Nonfinite essential fit result\n");goto done;
    }
    for(j=0;j<scm_model_ntheta(modes);j++)if(!isfinite(result.theta[j])){fprintf(stderr,"Nonfinite theta\n");goto done;}
    for(j=0;j<scm_model_nalpha(modes);j++)if(!isfinite(result.alpha[j])){fprintf(stderr,"Nonfinite alpha\n");goto done;}
    output(&result,id,method,modes,sigma,ocv?&curve:NULL,&options);
    if(ferror(stdout)){fprintf(stderr,"JSON output failed\n");goto done;}rc=EXIT_SUCCESS;
done:
    scm_problem_destroy(problem);free(samples);free(z);free(u);return rc;
}
