/* Experimental bounded integer square-root QR. Common fixed scale outside API.
   |stored coefficients| and |row entries| <= 2^29. No silent saturation.
   Failure may partially mutate factor/row; caller must latch invalidity.
   CORDIC_KIND=0: digit sqrt/divide; =1: shared CORDIC direction schedule.
   No trig API yet. All shifts of negative values are implemented explicitly. */
#include <stdint.h>
#define IQ_LIMIT INT32_C(536870912)
#ifndef CORDIC_KIND
#define CORDIC_KIND 0
#endif
static uint64_t iq_sqrt(uint64_t x){
 uint64_t r=0,b=UINT64_C(1)<<62;
 while(b>x)b>>=2;
 while(b){if(x>=r+b){x-=r+b;r=(r>>1)+b;}else r>>=1;b>>=2;}
 /* x is remainder: nearest integer square root, ties cannot occur here. */
 return r+(x>r);
}
static uint64_t iq_div(uint64_t x,uint32_t d){
 uint64_t q=0,r=0;
 for(int k=63;k>=0;k--){r=(r<<1)|((x>>k)&1);if(r>=d){r-=d;q|=UINT64_C(1)<<k;}}
 return q+(2*r>=d);
}
static int64_t iq_shift(int64_t x,unsigned k){return x<0?-((-x)>>k):x>>k;}
static int64_t iq_round(int64_t x,unsigned k){return x<0?-(((-x)+(INT64_C(1)<<(k-1)))>>k):(x+(INT64_C(1)<<(k-1)))>>k;}
static int iq_bound(int64_t x){return x>=-IQ_LIMIT&&x<=IQ_LIMIT;}
/* Gain inverse for 30 micro-rotations, nearest Q30. Internal vector Q16 guards.
   Split multiply avoids needing a 128-bit product. */
static int64_t iq_gain(int64_t x){
 int sign=x<0?-1:1;uint64_t a=x<0?(uint64_t)-x:(uint64_t)x;
 uint64_t p=(a>>16)*UINT64_C(652032874)+(((a&65535)*UINT64_C(652032874))>>16);
 return sign*(int64_t)((p+(UINT64_C(1)<<29))>>30);
}
static uint32_t iq_vector(int32_t a,int32_t b,int64_t *h){
 int64_t x=(int64_t)a*65536,y=(int64_t)b*65536;uint32_t bits=0;
 for(unsigned k=0;k<30;k++){int d=y>=0?1:-1;int64_t ox=x;x+=d*iq_shift(y,k);y-=d*iq_shift(ox,k);if(d>0)bits|=UINT32_C(1)<<k;}
 *h=iq_gain(x);return bits;
}
static void iq_rotate(int32_t a,int32_t b,uint32_t bits,int64_t *r,int64_t *v){
 int64_t x=(int64_t)a*65536,y=(int64_t)b*65536;
 for(unsigned k=0;k<30;k++){int d=(bits>>k)&1?1:-1;int64_t ox=x;x+=d*iq_shift(y,k);y-=d*iq_shift(ox,k);}
 *r=iq_gain(x);*v=iq_gain(y);
}
static int iq_insert(int32_t *R,unsigned n,int32_t*x){
 if(!n||n>34)return -1;
 unsigned count=n*(n+1)/2;
 for(unsigned i=0;i<count;i++)if(!iq_bound(R[i]))return -1;
 for(unsigned i=0;i<n;i++)if(!iq_bound(x[i]))return -1;
 unsigned p=0;
 for(unsigned j=0;j<n;j++){
  int32_t a=R[p],b=x[j];if(a<0)return -1;
  if(!a&&!b){p+=n-j;continue;}
  int64_t h;uint32_t bits=0;int64_t c=0,s=0;
#if CORDIC_KIND
  bits=iq_vector(a,b,&h);
#else
  h=(int64_t)iq_sqrt((uint64_t)((int64_t)a*a)+(uint64_t)((int64_t)b*b));
  c=(int64_t)iq_div((uint64_t)a<<30,(uint32_t)h);
  s=(int64_t)iq_div((uint64_t)(b<0?-(int64_t)b:b)<<30,(uint32_t)h);if(b<0)s=-s;
#endif
  if(!iq_bound(h)||h<=0)return -1;R[p++]=(int32_t)h;
  for(unsigned k=j+1;k<n;k++){
   int64_t r,v;
#if CORDIC_KIND
   iq_rotate(R[p],x[k],bits,&r,&v);
#else
   r=iq_round(c*R[p]+s*x[k],30);v=iq_round(c*x[k]-s*R[p],30);
#endif
   if(!iq_bound(r)||!iq_bound(v))return -1;
   R[p++]=(int32_t)r;x[k]=(int32_t)v;
  }
 }
 return 0;
}
