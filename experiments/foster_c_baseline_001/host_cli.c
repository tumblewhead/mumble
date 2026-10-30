/* Standalone sanitizer/profiling harness. Native-endian fixture doubles:
 * calibration14, initial message273, then observations Nx5.
 * Host file I/O belongs to the harness, not the portable core. */
#include "baseline.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
static FBContext state;
int main(int argc,char **argv) {
    FBConfig config={0};FBMessage prior;double row[5],saved[273],after[273];
    if(argc!=2){fprintf(stderr,"usage: host_cli fixture.bin\n");return 2;}
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    if(fread(config.cal,sizeof(double),14,f)!=14||fread(prior.mean,sizeof(double),16,f)!=16||
       fread(prior.root,sizeof(double),256,f)!=256||fread(&prior.logZ,sizeof(double),1,f)!=1)return 2;
    config.rounds=4;config.fractions=8;config.gradient_tol=1e-6;config.step_tol=1e-7;config.encoding=4;
    if(fb_init(&state,&config,&prior,123))return 3;
    fb_get_message(&state,saved);
    double invalid[5]={1./35,0,25,3.7,0};
    if(fb_offer(&state,0,invalid)!=FB_INPUT||fb_offer(&state,1,invalid)!=FB_ORDER)return 4;
    fb_get_message(&state,after);if(memcmp(saved,after,sizeof(saved)))return 4;
    double t=fb_now();size_t count;
    while((count=fread(row,sizeof(double),5,f))==5) {
        int r=fb_offer(&state,state.next_index,row);if(r<0){fprintf(stderr,"failure %d at %llu\n",r,(unsigned long long)state.next_index);return 5;}
    }
    if(count||ferror(f)||fb_flush(&state)<0)return 6;
    double elapsed=fb_now()-t;fclose(f);
    if(fb_flush(&state)!=FB_OK)return 7;
    printf("{\"status\":\"completed\",\"records\":%llu,\"tokens\":%llu,\"context_bytes\":%zu,\"wall_s\":%.9g}\n",
           (unsigned long long)state.retired_index,(unsigned long long)state.generation,sizeof(state),elapsed);
    return 0;
}
