#ifndef MUMBLE_COMPACT_COMPARE_H
#define MUMBLE_COMPACT_COMPARE_H
/* Host validation only. Field comparisons exclude padding and pointer values
 * that necessarily differ between the original and compact representations.
 * Acceptance is exact numerical equality; signed-zero bit changes are counted
 * separately. NaNs are comparable only in intentionally unavailable outputs.
 */
#include "scm_compact_remainder.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    uint64_t scalar_checks, double_checks, mismatches, bit_differences;
    double max_absolute_difference;
    const char *first_mismatch;
} compact_comparison;

static void compact_compare_scalar(compact_comparison *r,int same,const char *name)
{
    r->scalar_checks++;
    if(!same) { if(!r->mismatches)r->first_mismatch=name;r->mismatches++; }
}
static void compact_compare_double(compact_comparison *r,double a,double b,const char *name)
{
    int same=a==b || (isnan(a)&&isnan(b));
    r->double_checks++;
    if(memcmp(&a,&b,sizeof(a)))r->bit_differences++;
    if(isfinite(a)&&isfinite(b))r->max_absolute_difference=fmax(r->max_absolute_difference,fabs(a-b));
    if(!same) { if(!r->mismatches)r->first_mismatch=name;r->mismatches++; }
}
static void compact_compare_array(compact_comparison *r,const double *a,const double *b,
                                  size_t count,const char *name)
{
    size_t k;for(k=0;k<count;k++)compact_compare_double(r,a[k],b[k],name);
}
#define CMP_SCALAR(field) compact_compare_scalar(r,a->field==b->field,#field)
#define CMP_DOUBLE(field) compact_compare_double(r,a->field,b->field,#field)
#define CMP_ARRAY(field) compact_compare_array(r,a->field,b->field,sizeof(a->field)/sizeof(double),#field)
static void compact_compare_factor(compact_comparison *r,const scm_evidence_factor *a,
                                    const scm_evidence_factor *b)
{
    CMP_SCALAR(samples);CMP_SCALAR(dim);CMP_ARRAY(upper);
}
static void compact_compare_model(compact_comparison *r,const scm_model_state *a,
                                   const scm_model_state *b)
{
    CMP_SCALAR(modes);CMP_ARRAY(theta);CMP_ARRAY(tau);CMP_ARRAY(gamma);
    CMP_DOUBLE(Q);CMP_DOUBLE(z0);CMP_DOUBLE(charge_Ah);CMP_DOUBLE(elapsed);
    CMP_ARRAY(f);CMP_ARRAY(a);CMP_ARRAY(df);CMP_ARRAY(da);
    CMP_DOUBLE(hb);CMP_DOUBLE(ha);CMP_ARRAY(dhb);CMP_ARRAY(dha);
}
static void compact_compare_evidence(compact_comparison *r,const scm_evidence *a,
                                      const scm_compact_evidence *b)
{
    compact_compare_model(r,&a->model,&b->model);
    compact_compare_factor(r,&a->history,&b->history);
    compact_compare_factor(r,&a->event,&b->event);
    CMP_SCALAR(first_index);CMP_SCALAR(next_index);CMP_SCALAR(active_begin);
    CMP_SCALAR(events_completed);CMP_SCALAR(excitation);CMP_SCALAR(has_last);
    CMP_DOUBLE(last_current);CMP_DOUBLE(last_dt);
    CMP_DOUBLE(charge_min_Ah);CMP_DOUBLE(charge_max_Ah);
    CMP_SCALAR(last_event_samples);CMP_SCALAR(residual_flagged_events);
    CMP_DOUBLE(last_event_anchor_rms_sigma);CMP_DOUBLE(max_event_anchor_rms_sigma);
    compact_compare_scalar(r,b->config!=NULL,"config_present");
    if(b->config)compact_compare_scalar(r,!memcmp(&a->config,b->config,sizeof(a->config)),"config_content");
}
static void compact_compare_remainder(compact_comparison *r,const scm_remainder *a,
    const scm_compact_remainder *b,const scm_evidence *ae,const scm_compact_evidence *be)
{
    CMP_SCALAR(paired_ancestry);CMP_SCALAR(next_index);CMP_SCALAR(dim);CMP_SCALAR(pair_count);
    compact_compare_scalar(r,(a->bound_evidence==ae)==(b->bound_evidence==be),"bound_identity");
    compact_compare_scalar(r,(a->bound_evidence==NULL)==(b->bound_evidence==NULL),"bound_null");
    compact_compare_scalar(r,!memcmp(a->pair_row,b->pair_row,sizeof(a->pair_row)),"pair_row");
    compact_compare_scalar(r,!memcmp(a->pair_column,b->pair_column,sizeof(a->pair_column)),"pair_column");
    CMP_ARRAY(coefficient);CMP_ARRAY(last_bound);CMP_ARRAY(tau_lo);CMP_ARRAY(tau_hi);
    CMP_ARRAY(gamma_lo);CMP_ARRAY(gamma_hi);CMP_DOUBLE(Q_lo);
    CMP_ARRAY(R_abs_max);CMP_ARRAY(v_abs_max);CMP_DOUBLE(H_abs_max);CMP_DOUBLE(u_abs_max);
    CMP_ARRAY(f_lo);CMP_ARRAY(f_hi);CMP_ARRAY(f_first);CMP_ARRAY(f_second);
    CMP_DOUBLE(hb_lo);CMP_DOUBLE(hb_hi);CMP_ARRAY(hb_first);CMP_ARRAY(hb_second);
    CMP_ARRAY(throughput_Ah);CMP_DOUBLE(elapsed);CMP_DOUBLE(charge_Ah);
    CMP_DOUBLE(charge_min_Ah);CMP_DOUBLE(charge_max_Ah);
    compact_compare_scalar(r,b->config!=NULL,"remainder_config_present");
    if(b->config)compact_compare_scalar(r,!memcmp(&a->config,b->config,sizeof(a->config)),"remainder_config_content");
}
static void compact_compare_result(compact_comparison *r,const scm_remainder_result *a,
                                    const scm_remainder_result *b)
{
    CMP_SCALAR(status);CMP_SCALAR(arithmetic_validated);CMP_SCALAR(domain_code);
    CMP_DOUBLE(affine_nll);CMP_DOUBLE(whitened_prediction_error_bound);
    CMP_DOUBLE(nll_error_bound);CMP_DOUBLE(budget);
}
#undef CMP_SCALAR
#undef CMP_DOUBLE
#undef CMP_ARRAY
#endif
