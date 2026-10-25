/* Host comparison: original and compact bounded paths see the identical
 * existing stream once each. No optimizer, truth file or raw-history array.
 * Reference objects, CSV parser and candidate list are HOST AUDIT costs.
 */
#include "compact_compare.h"
#include "scm_compact_assess.h"
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#define MAX_CANDIDATES 32
typedef union {
    struct { scm_compact_evidence_workspace evidence; scm_compact_remainder_workspace remainder; } ingest;
    struct { scm_compact_assess_workspace workspace; scm_compact_assessment report; scm_assess_options options; } query;
} compact_phase_storage;
typedef struct {
    scm_evidence_config config;
    scm_compact_evidence evidence;
    scm_compact_remainder remainder;
    compact_phase_storage phase;
    scm_sample sample;
    scm_remainder_result remainder_result;
    double delta[SCM_EVIDENCE_DIM];
} compact_owned_objects;
static compact_owned_objects compact;
static scm_evidence reference_e;
static scm_remainder reference_r;
static scm_evidence_workspace reference_ew;
static scm_remainder_workspace reference_rw;
static scm_remainder_result reference_result;
static scm_evidence_factor reference_snapshot;
static scm_fit_result reference_fit;
static scm_assessment reference_assessment;
static scm_assess_workspace reference_aw;
static double reference_gradient[SCM_EVIDENCE_DIM];
static double candidates[MAX_CANDIDATES][SCM_EVIDENCE_DIM];
static unsigned candidate_count;
static char csv_line[4096],source_hex[65];
static compact_comparison comparison;
static uint64_t diagnostic_checks,diagnostic_failures;
static double max_eigen_absolute_difference,max_target_absolute_difference;

static void number(double x){if(isfinite(x))printf("%.17g",x);else fputs("null",stdout);}
static const char *space(const char *s){while(isspace((unsigned char)*s))s++;return s;}
static int parse_count(const char *s,uint64_t *out)
{
    char *end;unsigned long long v;s=space(s);if(!*s||*s=='-')return -1;
    errno=0;v=strtoull(s,&end,10);if(errno||end==s||*space(end)||v>UINT64_MAX)return -1;
    *out=(uint64_t)v;return 0;
}
static int hex_digit(char c)
{
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return c-'a'+10;
    if(c>='A'&&c<='F')return c-'A'+10;
    return -1;
}
static int read_anchor(const char *path,uint64_t cap)
{
    scm_evidence_config *c=&compact.config;FILE *f=fopen(path,"r");int i,nt,na,d,ch,rc=-1;
    if(!f)return -1;
    memset(c,0,sizeof(*c));
    if(fscanf(f,"%d%lf%64s",&c->modes,&c->sigma,source_hex)!=3)goto done;
    nt=scm_model_ntheta(c->modes);na=scm_model_nalpha(c->modes);d=nt+na;
    if(!nt||strlen(source_hex)!=64)goto done;
    for(i=0;i<32;i++){int a=hex_digit(source_hex[2*i]),b=hex_digit(source_hex[2*i+1]);if(a<0||b<0)goto done;c->source_id[i]=(unsigned char)(16*a+b);}
    for(i=0;i<nt;i++)if(fscanf(f,"%lf",&c->theta[i])!=1)goto done;
    for(i=0;i<na;i++)if(fscanf(f,"%lf",&c->alpha[i])!=1)goto done;
    for(i=0;i<d;i++)if(fscanf(f,"%lf",&c->scale[i])!=1)goto done;
    for(i=0;i<d;i++)if(fscanf(f,"%lf",&c->radius[i])!=1)goto done;
    if(fscanf(f,"%u",&candidate_count)!=1||candidate_count>MAX_CANDIDATES)goto done;
    for(i=0;i<(int)candidate_count*d;i++)if(fscanf(f,"%lf",&candidates[i/d][i%d])!=1||!isfinite(candidates[i/d][i%d]))goto done;
    do{ch=fgetc(f);}while(ch!=EOF&&isspace((unsigned char)ch));if(ch!=EOF||ferror(f))goto done;
    c->max_event_samples=cap;c->residual_rms_limit_sigma=4;
    rc=scm_evidence_init(&reference_e,c);if(!rc)rc=scm_remainder_init(&reference_r,c);
    if(!rc)rc=scm_compact_evidence_init(&compact.evidence,c);
    if(!rc)rc=scm_compact_remainder_init(&compact.remainder,c);
done:
    if(fclose(f)&&rc==0)rc=-1;
    return rc;
}
static FILE *open_data(const char *path)
{
    FILE *f=fopen(path,"r");size_t n;if(!f)return NULL;
    if(!fgets(csv_line,sizeof(csv_line),f)){fclose(f);return NULL;}
    n=strlen(csv_line);while(n&&(csv_line[n-1]=='\n'||csv_line[n-1]=='\r'))csv_line[--n]=0;
    if(strcmp(csv_line,"sample_index,dt_s,current_A,voltage_V")){fclose(f);return NULL;}return f;
}
static int read_sample(FILE *f,uint64_t expected,scm_sample *s)
{
    const char *p;char *end;unsigned long long index;double v[3];int i;
    if(!fgets(csv_line,sizeof(csv_line),f))return -1;
    if(!strchr(csv_line,'\n')&&!feof(f))return -1;
    p=space(csv_line);if(!*p||*p=='-')return -1;errno=0;index=strtoull(p,&end,10);
    if(errno||end==p||index>UINT64_MAX||(uint64_t)index!=expected)return -1;
    p=space(end);if(*p++!=',')return -1;
    for(i=0;i<3;i++){errno=0;v[i]=strtod(p,&end);if(errno||end==p||!isfinite(v[i]))return -1;p=space(end);if(i<2){if(*p++!=',')return -1;}else if(*p)return -1;}
    if(v[0]<0)return -1;
    s->dt=v[0];s->current=v[1];s->voltage=v[2];return 0;
}
static void check(int same){diagnostic_checks++;if(!same)diagnostic_failures++;}
static int near(double a,double b,double absolute,double relative,double *maximum)
{
    if(a==b || (isnan(a)&&isnan(b)))return 1;
    if(!isfinite(a)||!isfinite(b))return 0;
    *maximum=fmax(*maximum,fabs(a-b));return fabs(a-b)<=absolute+relative*fmax(fabs(a),fabs(b));
}
static void compare_target(const scm_assess_target *a,const scm_assess_target *b)
{
#define TARGET_SCALAR(field) check(a->field==b->field)
#define TARGET_DOUBLE(field) check(near(a->field,b->field,1e-11,1e-9,&max_target_absolute_difference))
    check(!strcmp(a->name,b->name));check(!strcmp(a->units,b->units));
    TARGET_SCALAR(status);TARGET_SCALAR(reasons);TARGET_SCALAR(point_available);TARGET_SCALAR(has_local_range);
    TARGET_SCALAR(has_relative_halfwidth);TARGET_SCALAR(passes_local_precision);TARGET_SCALAR(eligible_for_profile_check);
    TARGET_SCALAR(active_constraints_present);TARGET_SCALAR(conditioned_fit);
    TARGET_DOUBLE(point);TARGET_DOUBLE(lower);TARGET_DOUBLE(upper);TARGET_DOUBLE(support_lower);TARGET_DOUBLE(support_upper);
    TARGET_DOUBLE(null_projection);TARGET_DOUBLE(local_standard_deviation);TARGET_DOUBLE(local_halfwidth);TARGET_DOUBLE(relative_halfwidth);
#undef TARGET_SCALAR
#undef TARGET_DOUBLE
}
static void emit_target(const scm_assess_target *t)
{
    printf("{\"status\":\"%s\",\"reasons\":%u,\"point\":",scm_assess_status_name(t->status),t->reasons);number(t->point);
    printf(",\"has_local_range\":%s,\"null_projection\":",t->has_local_range?"true":"false");number(t->null_projection);
    fputs(",\"local_halfwidth\":",stdout);number(t->local_halfwidth);
    printf(",\"passes_local_precision\":%d}",t->passes_local_precision);
}
static void emit_curvature(void)
{
    const scm_evidence_config *c=&compact.config;
    const scm_compact_assessment *a=&compact.phase.query.report;
    const scm_compact_assess_workspace *w=&compact.phase.query.workspace;
    int t,i,j,d=a->joint_dimension,n=c->modes;
    double Q=exp(c->theta[n+3]);
    fputs(",\"local_curvature_diagnostic\":[",stdout);
    for(t=0;t<2;t++) {
        double old_variance=0,new_variance=0,old_null=0,new_null=0,norm=0;
        for(i=0;i<d;i++) {
            double g=i==n+3?(t?c->scale[n+3]:(reference_e.model.charge_Ah/Q)*c->scale[n+3]):(!t&&i==n+2?c->scale[n+2]:0.);
            norm+=g*g;
        }
        for(j=0;j<d;j++) {
            double old_projection=0,new_projection=w->row_projection.target_projection[t*d+j];
            for(i=0;i<d;i++) {
                double g=i==n+3?(t?c->scale[n+3]:(reference_e.model.charge_Ah/Q)*c->scale[n+3]):(!t&&i==n+2?c->scale[n+2]:0.);
                old_projection+=g*reference_aw.vectors[i*d+j];
            }
            check(near(old_projection,new_projection,1e-11,1e-9,&max_target_absolute_difference));
            if(reference_assessment.eigenvalues[j]>reference_assessment.eigen_cutoff)old_variance+=old_projection*old_projection/reference_assessment.eigenvalues[j];
            else old_null+=old_projection*old_projection;
            if(w->eigenvalues[j]>a->eigen_cutoff)new_variance+=new_projection*new_projection/w->eigenvalues[j];
            else new_null+=new_projection*new_projection;
        }
        old_null=norm>0?fmax(0.,fmin(1.,old_null/norm)):1.;
        new_null=norm>0?fmax(0.,fmin(1.,new_null/norm)):1.;
        check(near(old_variance,new_variance,1e-11,1e-9,&max_target_absolute_difference));
        check(near(old_null,new_null,1e-11,1e-9,&max_target_absolute_difference));
        check(near((t?Q:1.)*sqrt(fmax(0.,old_variance)),(t?Q:1.)*sqrt(fmax(0.,new_variance)),1e-11,1e-9,&max_target_absolute_difference));
        if(t)putchar(',');
        printf("{\"target\":\"%s\",\"semantics\":\"fixed_chart_curvature_only_no_optimizer_or_coverage_claim\",\"coordinate_variance\":",t?"log_Q":"current_soc");number(new_variance);
        fputs(",\"reference_coordinate_variance\":",stdout);number(old_variance);
        fputs(",\"null_projection\":",stdout);number(new_null);
        fputs(",\"physical_standard_deviation\":",stdout);number((t?Q:1.)*sqrt(fmax(0.,new_variance)));
        printf(",\"local_direction_resolved\":%s}",!a->matrix_invalid&&new_null<=compact.phase.query.options.null_projection_tol?"true":"false");
    }
    putchar(']');
}
static int checkpoint(void)
{
    scm_evidence_config *c=&compact.config;scm_compact_assessment *a=&compact.phase.query.report;
    scm_compact_assess_workspace *w=&compact.phase.query.workspace;
    scm_assess_options *o=&compact.phase.query.options;
    int i,nt=scm_model_ntheta(c->modes),na=scm_model_nalpha(c->modes),d=nt+na;double cost;
    if(scm_evidence_snapshot(&reference_e,&reference_snapshot,&reference_ew))return -1;
    if(scm_compact_evidence_snapshot_into(&compact.evidence,&w->factor_matrix.snapshot,w->row_projection.qrrow))return -1;
    compact_compare_factor(&comparison,&reference_snapshot,&w->factor_matrix.snapshot);
    memset(&reference_fit,0,sizeof(reference_fit));
    if(scm_evidence_factor_normal(&reference_snapshot,reference_fit.joint_normal,reference_gradient,&cost))return -1;
    memcpy(reference_fit.theta,c->theta,(size_t)nt*sizeof(double));
    memcpy(reference_fit.alpha,c->alpha,(size_t)na*sizeof(double));
    memcpy(reference_fit.coordinate_scales,c->scale,(size_t)d*sizeof(double));
    reference_fit.charge_Ah=reference_e.model.charge_Ah;reference_fit.elapsed_physical_s=reference_e.model.elapsed;
    reference_fit.status=1; /* No nonlinear fit performed by either path. */
    if(!(reference_e.excitation&1u))reference_fit.unexcited_theta_mask|=1u<<c->modes;
    if(!(reference_e.excitation&2u))reference_fit.unexcited_theta_mask|=1u<<(c->modes+1);
    scm_assess_options_default(o);
    if(scm_assess(&reference_fit,c->modes,o,&reference_assessment,&reference_aw))return -1;
    if(scm_compact_assess(&compact.evidence,1,0,o,a,w))return -1;
#define ASSESS_SCALAR(field) check(a->field==reference_assessment.field)
    ASSESS_SCALAR(modes);ASSESS_SCALAR(joint_dimension);ASSESS_SCALAR(numerical_rank);ASSESS_SCALAR(matrix_invalid);
    ASSESS_SCALAR(eigen_converged);ASSESS_SCALAR(coordinate_chart_supported);ASSESS_SCALAR(optimizer_status);ASSESS_SCALAR(active_constraints);
#undef ASSESS_SCALAR
    check(near(a->eigen_cutoff,reference_assessment.eigen_cutoff,1e-9,1e-12,&max_eigen_absolute_difference));
    for(i=0;i<d;i++)check(near(w->eigenvalues[i],reference_assessment.eigenvalues[i],1e-9,1e-12,&max_eigen_absolute_difference));
    compare_target(&reference_assessment.targets[d],&a->current_soc);
    compare_target(&reference_assessment.targets[c->modes+3],&a->capacity_Q_Ah);
    printf("{\"samples\":%" PRIu64 ",\"elapsed_s\":%.17g,\"numerical_rank\":%d,\"affine_anchor_nll\":%.17g,\"current_soc\":",compact.evidence.next_index,compact.evidence.model.elapsed,a->numerical_rank,cost);
    emit_target(&a->current_soc);fputs(",\"capacity_Q_Ah\":",stdout);emit_target(&a->capacity_Q_Ah);
    emit_curvature();
    fputs(",\"candidate_queries\":[",stdout);
    for(i=0;i<(int)candidate_count;i++) {
        int r1,r2;if(i)putchar(',');memcpy(compact.delta,candidates[i],(size_t)d*sizeof(double));
        r1=scm_remainder_query(&reference_r,&reference_e,compact.delta,.1,&reference_result);
        r2=scm_compact_remainder_query(&compact.remainder,&compact.evidence,compact.delta,.1,&compact.remainder_result);
        compact_compare_scalar(&comparison,r1==r2,"query_code");compact_compare_result(&comparison,&reference_result,&compact.remainder_result);
        printf("{\"index\":%d,\"code\":%d,\"status\":\"%s\",\"affine_nll\":",i,r2,scm_remainder_status_name(compact.remainder_result.status));number(compact.remainder_result.affine_nll);
        fputs(",\"nll_error_bound\":",stdout);number(compact.remainder_result.nll_error_bound);putchar('}');
    }
    fputs("]}",stdout);return 0;
}
static void sizes(void)
{
#define SIZE(name,type) printf("\"%s\":%zu,",name,sizeof(type))
    fputs("{\"schema\":\"mumble_compact_sizes_v1\",",stdout);
    SIZE("pointer",void*);SIZE("double",double);SIZE("config",scm_evidence_config);
    SIZE("reference_evidence",scm_evidence);SIZE("reference_evidence_workspace",scm_evidence_workspace);
    SIZE("reference_remainder",scm_remainder);SIZE("reference_remainder_workspace",scm_remainder_workspace);
    SIZE("factor",scm_evidence_factor);SIZE("compact_evidence",scm_compact_evidence);
    SIZE("compact_evidence_workspace",scm_compact_evidence_workspace);SIZE("compact_remainder",scm_compact_remainder);
    SIZE("compact_remainder_workspace",scm_compact_remainder_workspace);SIZE("compact_assess_workspace",scm_compact_assess_workspace);
    SIZE("compact_assessment",scm_compact_assessment);SIZE("assess_options",scm_assess_options);
    SIZE("sample",scm_sample);SIZE("remainder_result",scm_remainder_result);
    printf("\"caller_delta\":%zu,\"ingest_phase\":%zu,\"query_phase\":%zu,",sizeof(compact.delta),sizeof(compact.phase.ingest),sizeof(compact.phase.query));
    SIZE("serialized_phase_union",compact_phase_storage);
    printf("\"complete_owned_objects\":%zu}\n",sizeof(compact_owned_objects));
#undef SIZE
}
int main(int argc,char **argv)
{
    FILE *f;uint64_t end,split,cap,k;int r1,r2,ch,first=1;
    if(argc==2&&!strcmp(argv[1],"--sizes")){sizes();return 0;}
    if(argc!=6||parse_count(argv[3],&end)||parse_count(argv[4],&split)||parse_count(argv[5],&cap)||!end||!cap||split>=end) {
        fprintf(stderr,"usage: %s data.csv anchor.txt end_samples split_samples max_event_samples | --sizes\n",argv[0]);return 2;
    }
    if(read_anchor(argv[2],cap)){fprintf(stderr,"invalid anchor\n");return 2;}
    f=open_data(argv[1]);if(!f){fprintf(stderr,"invalid input header\n");return 2;}
    printf("{\"schema\":\"mumble_compact_probe_v1\",\"source_id\":\"%s\",\"end_samples\":%" PRIu64 ",\"checkpoints\":[",source_hex,end);
    for(k=0;k<end;k++) {
        if(read_sample(f,k,&compact.sample)){fprintf(stderr,"invalid or missing sample %" PRIu64 "\n",k);fclose(f);return 2;}
        r1=scm_remainder_evidence_push(&reference_e,&reference_r,compact.config.source_id,k,&compact.sample,&reference_ew,&reference_rw);
        r2=scm_compact_remainder_evidence_push(&compact.evidence,&compact.remainder,compact.config.source_id,k,&compact.sample,&compact.phase.ingest.evidence,&compact.phase.ingest.remainder);
        if(r1||r2){fprintf(stderr,"ingest failure at %" PRIu64 ": reference=%d compact=%d\n",k,r1,r2);fclose(f);return 2;}
        compact_compare_evidence(&comparison,&reference_e,&compact.evidence);
        compact_compare_remainder(&comparison,&reference_r,&compact.remainder,&reference_e,&compact.evidence);
        if(k+1==split||k+1==end){if(!first)putchar(',');first=0;if(checkpoint()){fprintf(stderr,"checkpoint failure\n");fclose(f);return 2;}}
    }
    /* This focused replay consumes the complete selected trace, not a silently
     * truncated prefix. Reject trailing non-whitespace or read errors. */
    do{ch=fgetc(f);}while(ch!=EOF&&isspace((unsigned char)ch));
    if(ch!=EOF||ferror(f)){fprintf(stderr,"unexpected trailing data\n");fclose(f);return 2;}
    if(fclose(f)){fprintf(stderr,"input close failed\n");return 2;}
    printf("],\"exact_comparison\":{\"scalar_checks\":%" PRIu64 ",\"double_checks\":%" PRIu64 ",\"mismatches\":%" PRIu64 ",\"bit_differences\":%" PRIu64 ",\"max_absolute_difference\":%.17g,\"first_mismatch\":\"%s\"},",comparison.scalar_checks,comparison.double_checks,comparison.mismatches,comparison.bit_differences,comparison.max_absolute_difference,comparison.first_mismatch?comparison.first_mismatch:"");
    printf("\"diagnostic_comparison\":{\"checks\":%" PRIu64 ",\"failures\":%" PRIu64 ",\"max_eigen_absolute_difference\":%.17g,\"max_target_absolute_difference\":%.17g},\"phase_storage_shared\":true,\"owned_objects_bytes\":%zu,\"no_new_fits\":true,\"truth_loaded\":false,\"all_checks_passed\":%s}\n",diagnostic_checks,diagnostic_failures,max_eigen_absolute_difference,max_target_absolute_difference,sizeof(compact_owned_objects),!comparison.mismatches&&!diagnostic_failures?"true":"false");
    return comparison.mismatches||diagnostic_failures?1:0;
}
