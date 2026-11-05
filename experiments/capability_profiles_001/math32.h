/* Experimental binary32 shared math. Not a correctly-rounded libm replacement.
   Finite stream inputs are checked by the core. IEEE binary32 required. */
#include <math.h>
#include <float.h>
#include <stdint.h>
#include <string.h>
_Static_assert(sizeof(float)==4 && FLT_MANT_DIG==24,"binary32 required");
static uint32_t cp32_fbits(float x){uint32_t u;memcpy(&u,&x,4);return u;}
static float cp32_fvalue(uint32_t u){float x;memcpy(&x,&u,4);return x;}
static float cp32_fscale(float x,int n){
 if(n>127)return (x*cp32_fvalue((uint32_t)(n+126)<<23))*2.f;
 if(n<-126)return (x*cp32_fvalue((uint32_t)(n+151)<<23))*0x1p-24f;
 return x*cp32_fvalue((uint32_t)(n+127)<<23);
}
static __attribute__((noinline,noclone)) float cp32_fexpm1_reduced(float x){
 float y=0;for(int k=8;k>=0;k--)y=(1.f+x*y)/(k+1);return x*y;
}
static float cp32_fexp(float x){
 if(isnan(x))return x;
 if(x>88.722839f)return INFINITY;
 if(x<-103.972084f)return 0;
 int n=(int)(x*1.4426950408889634f+(x<0?-.5f:.5f));
 float r=(x-n*0x1.62e4p-1f)-n*0x1.7f7d1cp-20f;
 return cp32_fscale(1.f+cp32_fexpm1_reduced(r),n);
}
static float cp32_fexpm1(float x){return fabsf(x)<.5f?cp32_fexpm1_reduced(x):cp32_fexp(x)-1.f;}
static float cp32_fsqrt(float x){
 if(x<0||isnan(x))return NAN;
 if(x==0||isinf(x))return x;
 float scale=1;
 if(x<0x1p-126f){x*=0x1p24f;scale=0x1p-12f;}
 float y=cp32_fvalue((cp32_fbits(x)>>1)+UINT32_C(0x1fc00000));
 for(unsigned k=0;k<4;k++)y=.5f*(y+x/y);
 return y*scale;
}
static float cp32_fhypot(float x,float y){
 x=fabsf(x);y=fabsf(y);
 if(isinf(x)||isinf(y))return INFINITY;
 if(isnan(x)||isnan(y))return NAN;
 if(x<y){float t=x;x=y;y=t;}
 if(x==0)return 0;
 float r=y/x;return x*cp32_fsqrt(1.f+r*r);
}
#define exp cp32_fexp
#define expm1 cp32_fexpm1
#define hypot cp32_fhypot
#define fabs fabsf
