/* Six-byte little-endian storage of IEEE binary64 bits63..16 (37 significant
   bits including the implicit1). Round-to-nearest-even on EVERY write.
   Computation remains binary64. This is a new accumulating approximation;
   no indefinite rounding or uncertainty certificate is claimed. */
#include <stdint.h>
#include <string.h>
#include <math.h>
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error history48 requires little endian
#endif
typedef struct {unsigned char b[6];} history_store;
static double history_get(const history_store*p,unsigned i){uint64_t u=0;double x;memcpy(&u,p[i].b,6);u<<=16;memcpy(&x,&u,8);return x;}
static void history_put(history_store*p,unsigned i,double x){uint64_t u;memcpy(&u,&x,8);u=(u+UINT64_C(0x7fff)+((u>>16)&1))>>16;memcpy(p[i].b,&u,6);}
static int history_insert(history_store*R,int n,double*x){
 unsigned p=0;
 for(int j=0;j<n;j++){
  double a=history_get(R,p),b=x[j],h=hypot(a,b);
  if(!isfinite(h))return -1;
  if(h==0){p+=n-j;continue;}
  double c=a/h,s=b/h;history_put(R,p++,h);
  if(!isfinite(history_get(R,p-1)))return -1;
  for(int k=j+1;k<n;k++){
   double r=history_get(R,p),v=x[k];history_put(R,p,c*r+s*v);x[k]=c*v-s*r;
   if(!isfinite(history_get(R,p))||!isfinite(x[k]))return -1;
   p++;
  }
 }
 return 0;
}
