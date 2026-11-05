#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/coordinate_sharing_001/baseline/tiny_cardinal/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/coordinate_sharing_001/baseline/tiny_cardinal/config.h"
#include <stdio.h>
static void emit_number(double x){if(fwrite(&x,8,1,stdout)!=1)__builtin_trap();}
int main(void){
 core c={0};history_store history[595]={0};double response[93]={0};
 static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
 model m={&cfg,response};response[0]=1;for(unsigned i=15;i<54;i++)response[i]=1;
 if(bind(&c,&m)||initialize(&c,history,c.anchor))return 2;
 for(unsigned i=0;i<=256;i++)for(unsigned j=0;j<3;j++){
  double v,d;spline(&m,-1.+i/128.,j,1,&v,&d);emit_number(v);emit_number(d);
 }
 for(unsigned i=0;i<64;i++){
  double w[16];for(unsigned k=0;k<16;k++)w[k]=((int)((i*17+k*13)%41)-20)*.002;
  if(supported(&m,w))return 3;
  for(unsigned j=0;j<34;j++){double v,d[16];if(feature(&m,w,j,0,&v,d))return 4;emit_number(v);for(unsigned k=0;k<16;k++)emit_number(d[k]);}
 }
 for(unsigned i=0;i<4096;i++){
  double obs[5]={.02,((int)((i/40)%17)-8)*.005,25,3.7,.002};
  if(stream_ingest(&c,history,config_V,config_ocv,obs))return 5;
  if(i%128==127){
   if(fit(&c,history,c.anchor))return 6;emit_number(c.stop);
   if(initialize(&c,history,(c.stop==1||c.stop==2)?c.point:c.anchor))return 7;
   int r=estimate(&c);emit_number(r);
   for(unsigned j=0;j<16;j++){double value=123,variance=456;int rc=scalar(&c,j,&value,&variance);emit_number(rc);emit_number(value);emit_number(variance);}
   emit_number(c.cost);emit_number(c.grad_inf);emit_number(c.decrement);
  }
 }
 for(unsigned j=0;j<93;j++)emit_number(response[j]);return 0;
}
