
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/coordinate_sharing_001/hys_pair/tiny_cardinal/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/coordinate_sharing_001/hys_pair/tiny_cardinal/config.h"
#include <stdio.h>
static void wr(const void*p,size_t n){if(fwrite(p,1,n,stdout)!=n)__builtin_trap();}
int main(void){
 static const fixed_config cfg={config_mean,config_scale,config_center,config_P};double response[93]={0};core c={0};model m={&cfg,response};c.m=m;
 double candidates[]={-INFINITY,-1000,-2,-1.000000000002,-1.000000000001,-1,-0.0,0.0,1,1.000000000001,1.000000000002,2,1000,INFINITY,NAN};
 for(unsigned j=0;j<16;j++)for(unsigned k=0;k<sizeof(candidates)/sizeof(*candidates);k++){
  memset(c.point,0,sizeof(c.point));c.point[j]=candidates[k];int s=supported(&m,c.point);wr(&s,sizeof(s));
  if(!s)for(unsigned coord=0;coord<16;coord++){
   for(unsigned z=0;z<93;z++)response[z]=(z%7-3.0)*.001;response[0]=.1;
   double v=123,d[16];int rc=transported(&c,coord,&v,d);wr(&rc,sizeof(rc));if(!rc){wr(&v,8);wr(d,sizeof(d));}
  }
 }
 for(unsigned j=14;j<16;j++)for(unsigned k=0;k<15;k++){
  memset(c.point,0,sizeof(c.point));c.point[j]=(candidates[k]+chart(&m,c.point,5)+log(cfg.center[j-11])-cfg.mean[j])/cfg.scale[j];int s=supported(&m,c.point);wr(&s,sizeof(s));
 }
 return 0;
}
