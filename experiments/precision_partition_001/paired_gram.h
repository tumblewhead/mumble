/* Experimental normal-matrix history, NOT a square-root factor.
   Each coefficient is hi+lo. Individual feature products round to binary32.
   Pair summation reduces loss of small additions but does not certify PSD,
   conditioning, coverage or indefinite accumulation. No fast-math/contraction. */
#include <math.h>
#include <stdint.h>
#include <string.h>
typedef struct {float hi,lo;} history_store;
/* Host reconstruction only; removed by target section GC when unused. */
static double history_get(const history_store*p,unsigned i){return (double)p[i].hi+(double)p[i].lo;}
static int pair_add(history_store*p,float x){
 float a=p->hi,b=x,s=a+b,v=s-a,e=(a-(s-v))+(b-v);
 float q=p->lo+e,t=s+q,w=t-s,r=(s-(t-w))+(q-w);
 if(!isfinite(t)||!isfinite(r))return -1;
 p->hi=t;p->lo=r;return 0;
}
static int history_insert(history_store*G,int n,float*x){
 unsigned p=0;
 for(int j=0;j<n;j++)for(int k=j;k<n;k++){
  float product=x[j]*x[k];
  if(!isfinite(product)||pair_add(G+p,product))return -1;
  p++;
 }
 return 0;
}
