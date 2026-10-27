#include "../rolling_engine.h"
#include <stddef.h>
#include <stdint.h>

/* Host-only qualification instrumentation, never linked into the candidate.
 * Linker --wrap forwards unchanged arguments to the exact numerical kernels.
 * It counts attempts independently of engine counters, including calls made
 * by retained-block preflight, query and merge phases. There is no reset API.
 */
static uint64_t query_steps,merge_steps,budget_rejections;
typedef struct {
    double point[16],cost,likelihood,prior;
    uint64_t cursor,rows;
    int status,derivatives,include_prior;
} iq_query_record;
static iq_query_record query_records[128];
static uint64_t query_calls;

int __real_rm_query_step(lab_query_state *,const double *,const adc12_reading *);
int __real_rm_merge_step(ch_jet *,const double *,const scm_sample *,double,double *);
int iq_real_engine_query(re_context *,int,int);

int __wrap_rm_query_step(lab_query_state *state,const double *point,
                         const adc12_reading *reading)
{
    if(query_steps+merge_steps>=4096u) {
        ++budget_rejections;
        return CH_ERR_OVERFLOW;
    }
    ++query_steps;
    return __real_rm_query_step(state,point,reading);
}

int __wrap_rm_merge_step(ch_jet *state,const double *origin,
                         const scm_sample *sample,double sigma,double *row)
{
    if(query_steps+merge_steps>=4096u || merge_steps>=256u) {
        ++budget_rejections;
        return CH_ERR_OVERFLOW;
    }
    ++merge_steps;
    return __real_rm_merge_step(state,origin,sample,sigma,row);
}

/* Direct kernel fixture calls also pass through the same finite counters. */
int iq_query_step(lab_query_state *state,const double *point,
                   const adc12_reading *reading)
{
    return __wrap_rm_query_step(state,point,reading);
}

int iq_merge_step(ch_jet *state,const double *origin,const scm_sample *sample,
                   double sigma,double *row)
{
    return __wrap_rm_merge_step(state,origin,sample,sigma,row);
}

int re_query(re_context *ctx,int derivatives,int include_prior)
{
    iq_query_record *record;unsigned i;
    if(query_calls>=128u) {
        ++budget_rejections;
        return CH_ERR_OVERFLOW;
    }
    record=&query_records[query_calls++];
    if(ctx)for(i=0;i<16;i++)record->point[i]=ctx->core.workspace.query.point[i];
    record->derivatives=derivatives;record->include_prior=include_prior;
    record->status=iq_real_engine_query(ctx,derivatives,include_prior);
    if(ctx) {
        record->cost=ctx->core.result.evidence.total_cost;
        record->likelihood=ctx->core.result.evidence.likelihood_cost;
        record->prior=ctx->core.result.evidence.prior_cost;
        record->cursor=ctx->core.bank.next_index;record->rows=ctx->core.bank.qr_rows;
    }
    return record->status;
}

int iq_query(re_context *ctx,int derivatives,int include_prior)
{
    return re_query(ctx,derivatives,include_prior);
}

int iq_read_query(unsigned index,double point[16],double costs[3],
                   uint64_t counts[2],int labels[3])
{
    const iq_query_record *record;unsigned i;
    if(index>=query_calls || !point || !costs || !counts || !labels)return -1;
    record=&query_records[index];
    for(i=0;i<16;i++)point[i]=record->point[i];
    costs[0]=record->cost;costs[1]=record->likelihood;costs[2]=record->prior;
    counts[0]=record->cursor;counts[1]=record->rows;
    labels[0]=record->status;labels[1]=record->derivatives;
    labels[2]=record->include_prior;return 0;
}

uint64_t iq_activity(unsigned index)
{
    if(index==0u)return query_steps;
    if(index==1u)return merge_steps;
    if(index==2u)return budget_rejections;
    if(index==3u)return query_calls;
    return UINT64_MAX;
}

size_t iq_size(unsigned index)
{
    switch(index) {
        case 0:return sizeof(scm_model_state);
        case 1:return sizeof(ch_jet);
        case 2:return sizeof(ch_bank);
        case 3:return sizeof(lab_query_state);
        case 4:return sizeof(lab_workspace);
        case 5:return sizeof(lab_result);
        case 6:return sizeof(lab_core);
        case 7:return sizeof(lab_input_store);
        case 8:return sizeof(adc12_calibration);
        case 9:return sizeof(re_context);
        case 10:return sizeof(adc12_raw_sample);
        case 11:return sizeof(adc12_reading);
        case 12:return sizeof(ch_result);
        case 13:return sizeof(ss_workspace);
        case 14:return sizeof(ss_input);
        case 15:return sizeof(ss_result);
        case 16:return sizeof(scm_sample);
        default:return 0;
    }
}

size_t iq_offset(unsigned index)
{
    switch(index) {
        case 0:return offsetof(re_context,core);
        case 1:return offsetof(re_context,inputs);
        case 2:return offsetof(re_context,calibration);
        case 3:return sizeof(re_context)-128u; /* typed phase-exclusive tail */
        case 4:return offsetof(lab_core,bank);
        case 5:return offsetof(lab_core,workspace);
        case 6:return offsetof(lab_core,result);
        case 7:return offsetof(lab_workspace,query.packed);
        case 8:return offsetof(lab_workspace,query.gradient);
        case 9:return offsetof(lab_workspace,query.point);
        case 10:return offsetof(lab_workspace,query.state);
        case 11:return offsetof(lab_workspace,query.decoded);
        default:return (size_t)-1;
    }
}
