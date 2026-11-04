#include <math.h>
#if STORE_DOUBLE
typedef double store;
#else
typedef float store;
#endif
/* One double row of caller-owned scratch; no dense factor or allocation.
   Exact-arithmetic orthogonal insertion, f64 rotations with rounded storage. */
int insert(store *R,int n,double *x){
 int p=0;
 for(int j=0;j<n;j++){
  double a=R[p],b=x[j],h=hypot(a,b);
  if(!isfinite(h))return -1;
  if(h==0){p+=n-j;continue;}
  double c=a/h,s=b/h;
  R[p++]=(store)h;
  if(!isfinite(R[p-1]))return -1;
  for(int k=j+1;k<n;k++){
   double r=R[p],v=x[k];R[p]=(store)(c*r+s*v);x[k]=c*v-s*r;
   if(!isfinite(R[p])||!isfinite(x[k]))return -1;
   p++;
  }
 }
 return 0;
}
