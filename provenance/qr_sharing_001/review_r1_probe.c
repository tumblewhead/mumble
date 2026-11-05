/* Independent direct-kernel comparison. Run from repository root. */
#include <stdio.h>
#include <stdlib.h>
#include <float.h>
#define STORE_DOUBLE 1
#define insert baseline_insert
#include "../../experiments/bank_memory_001/qr.c"
#undef insert
#include "../../experiments/sram_size_001/history48.h"
#include "../../experiments/qr_sharing_001/shared_qr.h"

static uint64_t rng=UINT64_C(0xf6426cd981ba0d13);
static uint64_t next(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static double value(unsigned mode){
 uint64_t u=next();double v;
 if(mode==0)return (double)((int)(u%2001)-1000)/71.;
 if(mode==1){u=(u&UINT64_C(0x800fffffffffffff))|((next()%2047)<<52);memcpy(&v,&u,8);return v;}
 if(mode==2){memcpy(&v,&u,8);return v;}
 const double a[]={0.,-0.,DBL_MIN,-DBL_MIN,DBL_TRUE_MIN,-DBL_TRUE_MIN,DBL_MAX,-DBL_MAX,INFINITY,-INFINITY,NAN,1.,-1.};
 return a[u%(sizeof(a)/sizeof(a[0]))];
}
int main(void){
 const unsigned widths[]={1,2,3,17,34,94};unsigned cases=0,failures=0,nan_only=0,finite_input_nan_only=0;
 for(unsigned wi=0;wi<sizeof(widths)/sizeof(widths[0]);wi++){
  unsigned n=widths[wi],count=n*(n+1)/2;
  for(unsigned mode=0;mode<4;mode++)for(unsigned trial=0;trial<100;trial++)for(unsigned packed=0;packed<2;packed++){
   /* Exact allocation extents let ASan detect either end overrun. */
   double *x=malloc(n*8),*y=malloc(n*8);
   void *a=malloc(count*(packed?6:8)),*b=malloc(count*(packed?6:8));
   if(!x||!y||!a||!b)return 2;
   for(unsigned j=0;j<n;j++)x[j]=value(mode);
   for(unsigned j=0;j<count;j++){
    double v=value(mode);
    if(packed)history_put(a,j,v);else ((double*)a)[j]=v;
   }
   memcpy(y,x,n*8);memcpy(b,a,count*(packed?6:8));
   int ra=packed?history_insert(a,(int)n,x):baseline_insert(a,(int)n,x);
   int rb=shared_insert(b,(int)n,y,packed);
   unsigned differences=0,bad=ra!=rb;
   for(unsigned j=0;j<n;j++)if(memcmp(x+j,y+j,8)){differences++;if(!isnan(x[j])||!isnan(y[j]))bad=1;}
   for(unsigned j=0;j<count;j++)if(memcmp((char*)a+j*(packed?6:8),(char*)b+j*(packed?6:8),packed?6:8)){
    double av=packed?history_get(a,j):((double*)a)[j],bv=packed?history_get(b,j):((double*)b)[j];
    differences++;if(!isnan(av)||!isnan(bv))bad=1;
   }
   if(differences){nan_only++;finite_input_nan_only+=mode<2;if(ra==0)bad=1;}
   if(bad){
    fprintf(stderr,"mismatch n=%u mode=%u trial=%u packed=%u status=%d/%d\n",n,mode,trial,packed,ra,rb);
    for(unsigned j=0;j<n;j++)if(memcmp(x+j,y+j,8))fprintf(stderr,"x[%u]=%a/%a\n",j,x[j],y[j]);
    if(!packed)for(unsigned j=0;j<count;j++)if(memcmp((double*)a+j,(double*)b+j,8))fprintf(stderr,"R[%u]=%a/%a\n",j,((double*)a)[j],((double*)b)[j]);
    free(x);free(y);free(a);free(b);return 1;
   }
   failures+=ra!=0;cases++;free(x);free(y);free(a);free(b);
  }
 }
 printf("{\"cases\":%u,\"matched_rejections\":%u,\"nan_representation_only_differences\":%u,\"finite_input_nan_only_differences\":%u,\"all_non_nan_factor_and_scratch_bytes_match\":true}\n",cases,failures,nan_only,finite_input_nan_only);
 return 0;
}
