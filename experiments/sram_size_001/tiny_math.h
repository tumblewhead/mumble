/* Small binary64 math candidate. Error is qualified by tests, not claimed
   correctly rounded. IEEE754 binary64 required; no errno/global libc state. */
#ifndef SRAM_TINY_MATH
#define SRAM_TINY_MATH
#include <math.h>
#include <float.h>
_Static_assert(sizeof(double)==8 && DBL_MANT_DIG==53,"binary64 required");
#include <stdint.h>
#include <string.h>
static inline uint64_t tm_bits(double x){uint64_t u;memcpy(&u,&x,8);return u;}
static inline double tm_value(uint64_t u){double x;memcpy(&x,&u,8);return x;}
static inline double tm_scale(double x,int n){
 if(n>1023)return (x*tm_value((uint64_t)(n+1022)<<52))*2;
 if(n<-1022)return (x*tm_value((uint64_t)(n+1077)<<52))*0x1p-54;
 return x*tm_value((uint64_t)(n+1023)<<52);
}
/* Shared degree13 expm1 polynomial for the reduced exp and tanh domains. */
static inline double tm_expm1_reduced(double r){
 static const double c[]={1.,.5,1./6.,1./24.,1./120.,1./720.,1./5040.,1./40320.,1./362880.,1./3628800.,1./39916800.,1./479001600.,1./6227020800.};
 double y=c[12];for(int j=11;j>=0;j--)y=c[j]+r*y;return r*y;
}
static inline double tm_exp(double x){
 if(isnan(x))return x;
 if(x>709.782712893384)return INFINITY;
 if(x<-745.1332191019411)return 0;
 int n=(int)(x*1.4426950408889634074+(x<0?-.5:.5));
 double r=(x-n*0x1.62e42fee00000p-1)-n*0x1.a39ef35793c76p-33;
 double y=1+tm_expm1_reduced(r);
 return tm_scale(y,n);
}
static inline double tm_expm1(double x){return fabs(x)<.5?tm_expm1_reduced(x):tm_exp(x)-1;}
static inline double tm_log(double x){
 if(isnan(x)||x<0)return NAN;
 if(x==0)return -INFINITY;
 if(isinf(x))return x;
 int n=0;
 if(x<0x1p-1022){x*=0x1p54;n=-54;}
 uint64_t u=tm_bits(x);n+=(int)(u>>52)-1023;
 double m=tm_value((u&UINT64_C(0xfffffffffffff))|UINT64_C(0x3ff0000000000000));
 if(m>1.4142135623730951){m*=.5;n++;}
 double t=(m-1)/(m+1),z=t*t,y=1./21.;
 for(int k=19;k>=3;k-=2)y=1./k+z*y;
 return n*0x1.62e42fee00000p-1+(2*t*(1+z*y)+n*0x1.a39ef35793c76p-33);
}
static inline double tm_sqrt(double x){
 if(x<0||isnan(x))return NAN;
 if(x==0||isinf(x))return x;
 double scale=1;
 if(x<0x1p-1022){x*=0x1p54;scale=0x1p-27;}
 double y=tm_value((tm_bits(x)>>1)+UINT64_C(0x1ff8000000000000));
 for(unsigned k=0;k<6;k++)y=.5*(y+x/y);
 return y*scale;
}
static inline double tm_hypot(double x,double y){
 x=fabs(x);y=fabs(y);
 if(isinf(x)||isinf(y))return INFINITY;
 if(isnan(x)||isnan(y))return NAN;
 if(x<y){double t=x;x=y;y=t;}
 if(x==0)return 0;
 double r=y/x;return x*tm_sqrt(1+r*r);
}
static inline double tm_tanh(double x){
 if(isnan(x))return x;
 if(fabs(x)>20)return x<0?-1:1;
 double a=fabs(x),v;
 if(a<.25){
  double e=tm_expm1_reduced(2*a);v=e/(2+e);
 }else{double e=tm_exp(-2*a);v=(1-e)/(1+e);}
 return tm_value(tm_bits(v)|(tm_bits(x)&UINT64_C(0x8000000000000000)));
}
static inline double tm_atanh(double x){
 if(fabs(x)>1||isnan(x))return NAN;
 if(fabs(x)==1)return x<0?-INFINITY:INFINITY;
 if(fabs(x)<.25){double z=x*x,y=1./25.;for(int k=23;k>=3;k-=2)y=1./k+z*y;return x*(1+z*y);}
 return .5*tm_log((1+x)/(1-x));
}
static inline double tm_nextup(double x,double direction){
 (void)direction;/* Caller uses nonnegative finite cost and +infinity only. */
 return tm_value(tm_bits(x)+1);
}
#define exp tm_exp
#define expm1 tm_expm1
#define log tm_log
#define sqrt tm_sqrt
#define hypot tm_hypot
#define tanh tm_tanh
#define atanh tm_atanh
#define nextafter tm_nextup
#define ldexp tm_scale
#define fmax(x,y) ((x)>(y)?(x):(y))
#endif
