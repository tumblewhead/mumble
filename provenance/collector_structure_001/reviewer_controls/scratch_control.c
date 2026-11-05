#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
int baseline(int32_t*,int,const float*);
int scratch(int32_t*,int,const float*);
static uint32_t state=37487;
static uint32_t rng(void){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
int main(void){
 float x[34];int32_t a[595],b[595];unsigned cases=0,rejected=0;
 const float edge[]={0,-0.f,131072.f,-131072.f,131073.f,-131073.f,INFINITY,-INFINITY,NAN,0x1p-149f,-0x1p-149f,0x1p-13f,-0x1p-13f,0x1.fffffep-14f};
 for(unsigned t=0;t<10000;t++){
  int n=1+rng()%34;
  for(int i=0;i<595;i++)a[i]=(int32_t)(rng()%1000000)-500000;
  unsigned q=0;for(int j=0;j<n;j++){a[q]=rng()%1000000;q+=n-j;}
  memcpy(b,a,sizeof a);
  for(int i=0;i<34;i++)x[i]=((int32_t)(rng()%20000001)-10000000)/8192.f;
  if(t%3==0)x[rng()%n]=edge[rng()%(sizeof edge/sizeof *edge)];
  int ra=baseline(a,n,x),rb=scratch(b,n,x);
  if(ra!=rb||memcmp(a,b,sizeof a)){printf("mismatch t=%u n=%d status=%d,%d\n",t,n,ra,rb);return 1;}
  cases++;rejected+=ra!=0;
 }
 for(int n=-1;n<=35;n+=36){memset(a,0,sizeof a);memcpy(b,a,sizeof a);if(baseline(a,n,x)!=scratch(b,n,x)||memcmp(a,b,sizeof a))return 2;cases++;}
 printf("cases=%u rejected=%u status=factor_bit_parity\n",cases,rejected);return 0;
}
