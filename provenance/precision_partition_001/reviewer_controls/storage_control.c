
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/precision_partition_001/storage003/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/precision_partition_001/storage003/config.h"
#include <stdio.h>
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
int main(void){
 collector c={0};float response[93]={0};history_store h[595]={0};c.m.config=&cfg;c.m.response=response;c.valid=1;
 response[0]=1;response[12]=0.1234567f;for(int j=15;j<54;j++)response[j]=.7654321f;
 float o[5]={0,0,25,3.712345f,.00234567f};
 if(stream_row(&c,config_V,config_ocv,o))return 1;
 if(c.phi[1]!=-(double)config_ocv[1]*(double)response[12]/(double)o[4])return 2;
 if(c.phi[33]!=((double)config_ocv[0]-(double)o[3])/(double)o[4])return 3;
 for(int b=0;b<3;b++)for(int k=0;k<3;k++){
 double expected=0;for(int j=0;j<13;j++)expected-=(double)response[15+13*b+j]*(double)config_V[3*j+k]/(double)o[4];
 if(c.phi[3+6*b+k]!=expected)return 4;
 }
 float saved[93];memcpy(saved,response,sizeof saved);o[0]=-1;
 if(collect(&c,h,config_V,config_ocv,o)!=-1||memcmp(saved,response,sizeof saved))return 5;
 o[0]=.02f;if(collect(&c,h,config_V,config_ocv,o)!=-1||memcmp(saved,response,sizeof saved))return 6;
 puts("storage double-intermediate row controls and reject latch pass");return 0;
}
