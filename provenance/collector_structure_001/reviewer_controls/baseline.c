#include <string.h>
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/collector_structure_001/baseline/shared_history.h"
int baseline(int32_t*R,int n,const float*x){float w[34];memcpy(w,x,sizeof w);return history_insert(R,n,w);}
