#include "provider.h"
#include "../live_anchor_integration_001/rolling_engine.h"
#include "../live_anchor_integration_001/host_input.h"
#include <string.h>

int desktop_eval(const double *,size_t,const double *,int,double *,double *,double *,double *);

size_t hp_context_bytes(void) { return sizeof(re_context); }
int hp_context_init(void *p,const unsigned char id[32])
{
    return re_init((re_context *)p,id,&hp_fixture_calibration);
}
static int raw_sample(uint64_t ticks,unsigned v,unsigned i,unsigned t,adc12_raw_sample *raw)
{
    if(v>4095 || i>4095 || t>4095)return CH_ERR_DOMAIN;
    memset(raw,0,sizeof(*raw));raw->interval_ticks=ticks;
    raw->codes.voltage=(uint16_t)v;raw->codes.current=(uint16_t)i;
    raw->codes.temperature=(uint16_t)t;return 0;
}
int hp_decode(uint64_t ticks,unsigned v,unsigned i,unsigned t,double out[3])
{
    adc12_raw_sample raw;adc12_reading d;int status;
    if(!out)return CH_ERR_ARGUMENT;
    status=raw_sample(ticks,v,i,t,&raw);if(status)return status;
    status=adc12_convert(&raw,&hp_fixture_calibration,&d);if(status)return status;
    out[0]=d.dt_s;out[1]=d.current_A;out[2]=d.voltage_V;return 0;
}
int hp_append(void *p,const unsigned char id[32],uint64_t index,
              uint64_t ticks,unsigned v,unsigned i,unsigned t)
{
    re_context *c=(re_context *)p;adc12_raw_sample raw;int status;
    if(!c || !id)return CH_ERR_ARGUMENT;
    if(c->inputs.block_count==LAB_BLOCK_DEPTH)return HP_ERR_BLOCK_FULL;
    status=raw_sample(ticks,v,i,t,&raw);if(status)return status;
    status=re_offer(c,id,index,&raw);if(status)return status;
    return re_admit(c);
}
int hp_commit_at(void *p,const double x[16])
{
    re_context work;int status;
    if(!p || !x)return CH_ERR_ARGUMENT;
    /* Extra host scratch makes this wrapper atomic, not an M23 implementation. */
    memcpy(&work,p,sizeof(work));
    memcpy(work.core.bank.estimate,x,sizeof(work.core.bank.estimate));
    status=re_commit(&work);
    if(!status)memcpy(p,&work,sizeof(work));
    return status;
}
int hp_compact_query(const void *p,const double x[16],hp_query_result *out)
{
    re_context work;int status;unsigned j;
    if(!p || !x || !out)return CH_ERR_ARGUMENT;
    memset(out,0,sizeof(*out));out->provider_kind=HP_LEGACY_COMPACT;
    memcpy(&work,p,sizeof(work));
    out->represented_rows=work.core.bank.next_index;
    out->retained_rows=work.inputs.block_count;
    memcpy(work.core.workspace.query.point,x,16*sizeof(double));
    status=re_query(&work,1,0);out->status=status;if(status)return status;
    out->likelihood=work.core.result.evidence.likelihood_cost;
    memcpy(out->gradient,work.core.workspace.query.gradient,sizeof(out->gradient));
    memcpy(out->gn_packed,work.core.workspace.query.packed,sizeof(out->gn_packed));
    out->endpoint[0]=work.core.result.evidence.detail.endpoint.SOC;
    for(j=0;j<3;j++)out->endpoint[j+1]=work.core.result.evidence.detail.endpoint.v[j];
    out->endpoint[4]=work.core.result.evidence.detail.endpoint.h;
    out->legacy_flags=work.core.result.evidence.flags;return 0;
}
int hp_exact_query(const double *samples,size_t n,const double x[16],hp_query_result *out)
{
    double matrix[256];unsigned i,j;int status;
    if((n && !samples) || !x || !out)return CH_ERR_ARGUMENT;
    memset(out,0,sizeof(*out));out->provider_kind=HP_REPLAY;out->retained_rows=n;
    status=desktop_eval(samples,n,x,1,&out->likelihood,out->gradient,matrix,out->endpoint);
    out->status=status;if(status)return status;
    for(i=0;i<16;i++)for(j=0;j<=i;j++)out->gn_packed[i*(i+1)/2+j]=matrix[16*i+j];
    return 0;
}
