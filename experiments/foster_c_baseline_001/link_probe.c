/* Link/resource accounting only: placeholder inputs, no vector/startup/memory map.
 * Not a firmware image, and not an executed RTL timing benchmark. */
#include "baseline.h"
FBContext probe_context;
FBConfig probe_config;
FBMessage probe_prior;
double probe_observation[5];
volatile int probe_status;
void probe_entry(void) {
    probe_status=fb_init(&probe_context,&probe_config,&probe_prior,1);
    probe_status=fb_offer(&probe_context,0,probe_observation);
    probe_status=fb_flush(&probe_context);
    for(;;){}
}
