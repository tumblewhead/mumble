/* Independent reviewer differential probe. Compile twice with CORE_PATH and
 * CONFIG_PATH. Binary stdout serializes each result separately, without padding.
 * No truth, input source mutation, or production implementation edits. */
#include CORE_PATH
#include CONFIG_PATH
#include <stdio.h>
static uint64_t rng=0x77112233445566ULL;
static double draw(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return (double)(rng>>11)*0x1p-53;}
static void record(int code,double value,const double*d){
 fwrite(&code,sizeof(code),1,stdout);fwrite(&value,sizeof(value),1,stdout);
 fwrite(d,sizeof(double),16,stdout);
}
int main(void){
 core c={0};history_store history[595]={0};double response[93]={0};
 model m={config_mean,config_scale,config_center,config_P,config_P,config_P,1.,response,response+15,response+54};
 response[0]=1;if(bind(&c,&m)||initialize(&c,history,c.anchor))return 2;
 const double edge[]={-1.000000000001,-1.,-0.999999999999,0.,0.999999999999,1.,1.000000000001};
 unsigned supported_count=0,features=0,endpoints=0,scalars=0;
 for(unsigned test=0;test<2000;test++){
  memset(c.point,0,sizeof(c.point));
  double prev=0;
  for(unsigned b=0;b<3;b++){
   double u=test<343?edge[(test/(b==0?1:b==1?7:49))%7]:2.4*draw()-1.2;
   double tau=config_center[b]*exp(u),x=log(tau-prev);prev=tau;
   c.point[8+2*b]=(x-config_mean[8+2*b])/config_scale[8+2*b];
   c.point[1+b]=(draw()-.5)*8;
  }
  if(test>=343&&test%4==0){
   unsigned j=test%16;const double exceptional[]={NAN,INFINITY,-INFINITY,709.,710.,-745.,-746.,0.};
   double x=exceptional[(test/16)%8];c.point[j]=(x-config_mean[j])/config_scale[j];
  }
  for(unsigned j=15;j<93;j++)response[j]=(draw()-.5)*.2;
  if(test%9==0)memset(response+15,0,78*sizeof(double));
  if(test%9==1)for(unsigned j=15;j<93;j++)response[j]*=1e-300;
  if(test%9==2)for(unsigned j=15;j<93;j++)response[j]*=1e300;
  if(test%9==3)response[15+test%78]=NAN;
  if(test%9==4)response[15+test%78]=INFINITY;
  int support=supported(&c.m,c.point);fwrite(&support,sizeof(support),1,stdout);
  if(support)continue;supported_count++;
  for(unsigned full=0;full<2;full++)for(unsigned row=0;row<(full?94:34);row++){
   double value=123,d[16];for(unsigned j=0;j<16;j++)d[j]=456;
   int code=feature(&c.m,c.point,row,full,&value,d);record(code,value,d);features++;
  }
  for(unsigned k=0;k<18;k++){
   double value=123,d[16];for(unsigned j=0;j<16;j++)d[j]=456;
   int code=transported(&c,k,&value,d);record(code,value,d);endpoints++;
   for(unsigned valid=0;valid<2;valid++){
    c.qr.lease.valid=valid;value=123;double var=456;
    code=scalar(&c,k,&value,&var);record(code,value,c.trial);fwrite(&var,sizeof(var),1,stdout);scalars++;
   }
  }
 }
 fprintf(stderr,"support_probes=2000 supported=%u feature_probes=%u endpoint_probes=%u scalar_probes=%u\n",supported_count,features,endpoints,scalars);
 return ferror(stdout)?3:0;
}
