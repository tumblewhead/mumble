
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/precision_partition_001/collector/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/precision_partition_001/collector/config.h"
#include <stdio.h>
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
int main(void){
 collector a={0},b={0};float ar[93]={0},br[93]={0};history_store ah[595]={0},bh[595]={0};
 a.m.config=b.m.config=&cfg;a.m.response=ar;b.m.response=br;a.valid=b.valid=1;
 ar[0]=br[0]=1;for(int j=15;j<54;j++)ar[j]=br[j]=1;
 for(int i=0;i<4096;i++){
 float o[5]={i%31==0?0:1.0f/35.0f,((i%11)-5)*.04f,25,3.6f,.002f};
 if(stream_row(&b,config_V,config_ocv,o))return 1;
 double row[34];for(int j=0;j<34;j++)row[j]=b.row.f[j];
 if(history_insert(bh,34,row))return 2;
 if(collect(&a,ah,config_V,config_ocv,o))return 3;
 if(memcmp(ar,br,sizeof ar)||memcmp(ah,bh,sizeof ah))return 4;
 }
 float before[93];history_store prior[595];memcpy(before,ar,sizeof ar);memcpy(prior,ah,sizeof ah);
 float invalid[5]={-1,0,25,3.6f,.002f};if(collect(&a,ah,config_V,config_ocv,invalid)!=-1)return 5;
 if(memcmp(ar,before,sizeof ar)||memcmp(ah,prior,sizeof ah))return 6;
 invalid[0]=.1f;if(collect(&a,ah,config_V,config_ocv,invalid)!=-1)return 7;
 if(memcmp(ar,before,sizeof ar)||memcmp(ah,prior,sizeof ah))return 8;
 puts("4096 paired separate-buffer expansion updates and reject/latch controls pass");return 0;
}
