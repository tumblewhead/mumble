#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/config_reference_001/pointer_block002/tiny_cardinal/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/config_reference_001/pointer_block002/tiny_cardinal/config.h"
#include <string.h>
#include <stdio.h>
int main(void){
 core c={0},before; double response[93]={0};
 static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
 model m={&cfg,response,response+15,response+54};if(bind(&c,&m))return 1;memcpy(&before,&c,sizeof c);
 double values[]={0.,-1.,NAN,INFINITY,-INFINITY};unsigned checks=0;
 for(unsigned group=0;group<3;group++)for(unsigned i=0;i<(group==2?5:16);i++)for(unsigned v=0;v<5;v++){
  if(group==0&&v<2)continue;
  double data[16];memcpy(data,group==0?config_mean:group==1?config_scale:config_center,(group==2?5:16)*8);data[i]=values[v];
  fixed_config badcfg=cfg;if(group==0)badcfg.mean=data;else if(group==1)badcfg.scale=data;else badcfg.center=data;
  model bad=m;bad.config=&badcfg;
  if(bind(&c,&bad)!=-1||memcmp(&c,&before,sizeof c))return 2;checks++;
 }
 for(unsigned i=0;i<8;i++){fixed_config badcfg=cfg;model bad=m;bad.config=&badcfg;
  switch(i){case 0:badcfg.mean=0;break;case 1:badcfg.scale=0;break;case 2:badcfg.center=0;break;case 3:badcfg.projected_map=0;break;case 4:bad.legacy=0;break;case 5:bad.free_rc=0;break;case 6:bad.forced_rc=0;break;default:bad.config=0;}
  if(bind(&c,&bad)!=-1||memcmp(&c,&before,sizeof c))return 3;checks++;
 }
 if(c.m.config!=&cfg)return 4;
 printf("invalid_config_checks=%u failed_bind_unchanged=1 shared_config_identity=1\n",checks);return 0;
}
