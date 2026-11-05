#include <string.h>
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/collector_structure_001/scratch/shared_history.h"
int scratch(int32_t*R,int n,const float*x){row_scratch w;memcpy(w.f,x,sizeof w.f);return history_insert(R,n,&w);}
