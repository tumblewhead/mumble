#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/model_metadata_001/baseline001/tiny_cardinal/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/model_metadata_001/baseline001/tiny_cardinal/config.h"
#include <stdio.h>
static void emit_bytes(const void*p,size_t n){if(fwrite(p,1,n,stdout)!=n)__builtin_trap();}
int main(void){
 core c={0};history_store history[595]={0};double response[93]={0};
 model m={config_mean,config_scale,config_center,config_P,config_P,config_P,1.,response,response+15,response+54};
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
 for(unsigned j=0;j<7;j++){
  model bad=m;
  switch(j){case 0:bad.mean=0;break;case 1:bad.scale=0;break;case 2:bad.center=0;break;case 3:bad.projected_map=0;break;case 4:bad.legacy=0;break;case 5:bad.free_rc=0;break;default:bad.forced_rc=0;}
  rc=bind(&c,&bad);if(rc!=-1)return 8;emit_bytes(&rc,sizeof(rc));
 }
 return 0;
}
