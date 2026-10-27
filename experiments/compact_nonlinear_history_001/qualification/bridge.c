#include "compact_history.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Qualification-only field access. No implementation hook or allocation. */
size_t qa_size(unsigned what)
{
    switch(what) {
    case 0:return sizeof(ch_context); case 1:return sizeof(ch_bank);
    case 2:return sizeof(ch_jet); case 3:return sizeof(ch_workspace);
    case 4:return sizeof(ch_result); case 5:return sizeof(ch_operational_layout);
    case 6:return sizeof(scm_model_state); case 7:return sizeof(scm_sample);
    case 8:return offsetof(ch_context,workspace); case 9:return offsetof(ch_context,result);
    case 10:return offsetof(ch_context,sample); case 11:return offsetof(ch_bank,query_evaluations);
    case 12:return offsetof(ch_bank,prior_evaluations); default:return 0;
    }
}
void qa_sample(ch_context *c,double dt,double current,double voltage)
{c->sample.dt=dt;c->sample.current=current;c->sample.voltage=voltage;}
void qa_point(ch_context *c,const double *x)
{memcpy(c->workspace.query.point,x,16*sizeof(double));}
void qa_estimate(ch_context *c,const double *x)
{memcpy(c->bank.estimate,x,16*sizeof(double));}
void qa_factor(ch_context *c,const double *r)
{memcpy(c->bank.upper,r,703*sizeof(double));}
void qa_read(const ch_context *c,unsigned what,double *v)
{
    switch(what) {
    case 0:memcpy(v,c->workspace.ingest.row,37*sizeof(double));break;
    case 1:memcpy(v,c->workspace.query.gradient,16*sizeof(double));break;
    case 2:memcpy(v,c->workspace.query.packed,136*sizeof(double));break;
    case 3:memcpy(v,c->bank.upper,703*sizeof(double));break;
    case 4:memcpy(v,c->bank.origin,16*sizeof(double));break;
    case 5:memcpy(v,c->bank.estimate,16*sizeof(double));break;
    case 6:memcpy(v,c->workspace.query.point,16*sizeof(double));break;
    case 7:v[0]=c->bank.jet.model.charge_Ah;v[1]=c->bank.charge_min_Ah;
           v[2]=c->bank.charge_max_Ah;v[3]=c->bank.jet.model.elapsed;break;
    }
}
void qa_result(const ch_context *c,ch_result *r) {*r=c->result;}
uint64_t qa_count(const ch_context *c,unsigned what)
{
    switch(what) {
    case 0:return c->bank.model_steps;case 1:return c->bank.qr_rows;
    case 2:return c->bank.query_evaluations;case 3:return c->bank.prior_evaluations;
    case 4:return c->bank.proposal_rounds;case 5:return c->bank.accepted_steps;
    case 6:return c->bank.next_index;case 7:return c->bank.available;
    default:return 0;
    }
}
int qa_last_error(const ch_context *c){return c->bank.last_error;}
int qa_jet_equal(const ch_context *c)
{return memcmp(&c->bank.jet,&c->workspace.ingest.prospective,sizeof(ch_jet))==0;}
