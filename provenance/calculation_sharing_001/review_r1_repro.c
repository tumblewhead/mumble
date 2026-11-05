/* Compile with CORE_PATH and CONFIG_PATH string macros for each preserved generated candidate. */
#include CORE_PATH
#include CONFIG_PATH
#include <stdio.h>
int main(void){
 core c={0};history_store history[595]={0};double response[93]={0};
 model m={config_mean,config_scale,config_center,config_P,config_P,config_P,1.,response,response+15,response+54};
 response[0]=1;
 int b=bind(&c,&m),init=initialize(&c,history,c.anchor);
 c.point[7]=(709.-config_mean[7])/config_scale[7];
 double val=123,var=456,d[16];int support=supported(&c.m,c.point);
 int tr=transported(&c,1,&val,d);int sc=scalar(&c,1,&val,&var);
 int finite=1;for(int k=0;k<16;k++)if(!isfinite(d[k]))finite=0;
 printf("bind=%d init=%d support=%d transport=%d finite=%d scalar=%d value=%.17g variance=%.17g\n",b,init,support,tr,finite,sc,val,var);
 return 0;
}
