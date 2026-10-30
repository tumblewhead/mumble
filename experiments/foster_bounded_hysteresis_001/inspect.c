/* Read-only diagnostic access to the frozen run's context. */
#include "baseline.h"
#include <string.h>
size_t review_context_size(void) { return sizeof(FBContext); }
void review_state(const FBContext *s,double *candidate,double *anchor,uint64_t *counts) {
    memcpy(candidate,s->candidate.mean,16*sizeof(double));
    memcpy(candidate+16,s->candidate.root,256*sizeof(double));
    candidate[272]=s->candidate.logZ;
    memcpy(anchor,s->anchor,16*sizeof(double));
    counts[0]=s->next_index;counts[1]=s->retired_index;
    counts[2]=(uint64_t)s->pending;counts[3]=s->generation;
}
