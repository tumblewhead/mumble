/* Campaign adapter: indexed V/I/T blocks only. No plant or scoring inputs. */
#include "baseline.h"
int campaign_block(FBContext *s,uint64_t first,const double *rows,int n,uint64_t *failure_index) {
    *failure_index=first;
    if(first!=s->next_index)return FB_ORDER;
    if(n<1||n>FB_BLOCK)return FB_INPUT;
    if(s->pending)return FB_FULL;
    for(int i=0;i<n;i++) {
        *failure_index=first+(uint64_t)i;
        int r=fb_offer(s,first+(uint64_t)i,rows+5*i);if(r<0)return r;
    }
    return s->pending?fb_flush(s):FB_RETIRED;
}
void campaign_state(const FBContext *s,uint64_t state[5],double diagnostics[7]) {
    state[0]=s->next_index;state[1]=s->retired_index;state[2]=(uint64_t)s->pending;
    state[3]=s->generation;state[4]=s->retired_ticks;
    diagnostics[0]=s->stop;diagnostics[1]=s->rounds;diagnostics[2]=s->evaluations;
    diagnostics[3]=s->cost;diagnostics[4]=s->initial_rms;diagnostics[5]=s->fitted_rms;
    diagnostics[6]=s->token_bytes;
}
