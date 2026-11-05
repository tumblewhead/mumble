#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/coordinate_sharing_001/hys_scalar/tiny_cardinal/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/coordinate_sharing_001/hys_scalar/tiny_cardinal/config.h"
#include <stdio.h>
static void emit_bytes(const void*p,size_t n){if(fwrite(p,1,n,stdout)!=n)__builtin_trap();}
int main(void){
 core c={0};history_store history[595]={0};double response[93]={0};
 static const fixed_config configuration={config_mean,config_scale,config_center,config_P};
 model m={&configuration,response};
 response[0]=1;for(unsigned j=15;j<54;j++)response[j]=1;
 int rc=bind(&c,&m);if(rc)return 2;
 rc=initialize(&c,history,c.anchor);if(rc)return 3;
 unsigned successful=0;
 for(unsigned i=0;i<256;i++){
  double w[16]={0};for(unsigned j=0;j<16;j++)w[j]=((int)((i*17+j*13)%41)-20)*.002;
  int support=supported(&m,w);emit_bytes(&support,sizeof(support));
  if(support==0){successful++;
   for(unsigned j=0;j<94;j++){double v,deriv[16];rc=feature(&m,w,j,1,&v,deriv);emit_bytes(&rc,sizeof(rc));if(!rc){emit_bytes(&v,8);emit_bytes(deriv,sizeof(deriv));}}
  }
  double obs[5]={.02,((int)(i%17)-8)*.005,25,3.7,.002};
  rc=stream_ingest(&c,history,config_V,config_ocv,obs);emit_bytes(&rc,sizeof(rc));if(rc)return 4;
  if(i%32==31){rc=fit(&c,history,c.anchor);emit_bytes(&rc,sizeof(rc));if(rc)return 5;
   emit_bytes(&c.stop,sizeof(c.stop));rc=initialize(&c,history,(c.stop==1||c.stop==2)?c.point:c.anchor);emit_bytes(&rc,sizeof(rc));if(rc)return 6;
  }
  for(unsigned j=0;j<16;j++){double v=123,var=456;rc=scalar(&c,j,&v,&var);emit_bytes(&rc,sizeof(rc));emit_bytes(&v,8);emit_bytes(&var,8);}
 }
 if(successful<1)return 7;
 emit_bytes(history,sizeof(history));emit_bytes(response,sizeof(response));emit_bytes(c.qr.factor,sizeof(c.qr.factor));
 for(unsigned j=0;j<5;j++){
  model bad=m; fixed_config badcfg=configuration;bad.config=&badcfg;
  switch(j){case 0:badcfg.mean=0;break;case 1:badcfg.scale=0;break;case 2:badcfg.center=0;break;case 3:badcfg.projected_map=0;break;default:bad.response=0;}
  rc=bind(&c,&bad);if(rc!=-1)return 8;emit_bytes(&rc,sizeof(rc));
 }
 model bad=m;bad.config=0;if(bind(&c,&bad)!=-1)return 9;return 0;
}
