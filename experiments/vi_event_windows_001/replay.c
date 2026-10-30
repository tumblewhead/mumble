#include "baseline.h"
#include <math.h>
double experiment_noise(double,double *,double *);
/* schedules are exclusive endpoints. Validate all before accepting any input. */
int experiment_replay(FBContext *s,const double *obs,size_t n,const uint64_t *ends,size_t blocks,
                      double *out,size_t capacity,size_t *written,double stats[4]) {
    *written=0;
    if(capacity<blocks)return FB_FULL;
    uint64_t previous=0;
    for(size_t j=0;j<blocks;j++) {
        if(ends[j]<=previous||ends[j]>n||ends[j]-previous>16)return FB_INPUT;
        previous=ends[j];
    }
    if(previous!=n||s->next_index||s->pending)return FB_INPUT;
    for(int k=0;k<4;k++)stats[k]=0.;
    size_t first=0;
    for(size_t j=0;j<blocks;j++) {
        int count=(int)(ends[j]-first);
        for(size_t i=first;i<ends[j];i++) {int r=fb_offer(s,i,obs+5*i);if(r<0)return r;}
        if(s->pending){int r=fb_flush(s);if(r<0)return r;}
        double *row=out+36*j;
        for(int i=0;i<16;i++) {
            double var=0.;row[i]=s->message.mean[i];
            for(int k=0;k<16;k++)var+=s->message.root[i*16+k]*s->message.root[i*16+k];
            row[16+i]=sqrt(var);
        }
        row[32]=s->message.logZ;row[33]=(double)s->retired_index;row[34]=s->stop;row[35]=s->evaluations;
        for(int i=0;i<count;i++) {
            double w,p;experiment_noise(s->residual[i],&w,&p);
            stats[0]+=1.-p;stats[1]+=w;stats[2]+=(p<.5);
        }
        stats[3]=(double)s->retired_ticks;*written=j+1;first=ends[j];
    }
    return FB_OK;
}
