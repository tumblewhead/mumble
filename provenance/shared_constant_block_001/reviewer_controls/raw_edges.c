#include <string.h>
extern const unsigned char cb_blob[];
/* Trusted offline-generated acyclic grammar; no dynamic allocation or recursion. */
static unsigned cb_rule(const unsigned char *p,unsigned token){
 unsigned i;for(i=0;i<p[0];i++)if(p[2+4*i]==token)break;return i;
}
static unsigned cb_len(const unsigned char *p,unsigned token){
 unsigned i=cb_rule(p,token);return i==p[0]?1:p[5+4*i];
}
static unsigned cb_byte(const unsigned char *p,unsigned offset){
 const unsigned char *s=p+2+4*p[0];unsigned token;
 for(;;){token=*s++;unsigned n=cb_len(p,token);if(offset<n)break;offset-=n;}
 for(;;){unsigned i=cb_rule(p,token);if(i==p[0])return token;
  unsigned left=p[3+4*i],n=cb_len(p,left);
  if(offset<n)token=left;else{offset-=n;token=p[4+4*i];}
 }
}
static __attribute__((noinline,noclone)) double cb_at(unsigned i){
 const unsigned char *p=cb_blob;
 unsigned char bytes[8];double v;
 for(unsigned k=0;k<8;k++){bytes[k]=cb_byte(p,8*i+k);}
 memcpy(&v,bytes,8);return v;
}

static inline double cb_get(const unsigned short *segment,unsigned i){return cb_at(*segment+i);}
#include <stdio.h>
const unsigned char cb_blob[]={23,126,2,0,0,2,3,2,2,4,4,255,255,2,5,3,3,8,6,3,2,6,7,4,4,4,8,6,240,7,9,5,1,9,10,9,5,17,11,10,6,23,12,11,128,24,13,12,8,31,14,13,127,32,15,14,8,39,16,15,255,40,17,16,1,41,18,17,3,45,19,18,0,46,20,19,248,47,21,20,127,48,22,21,7,52,23,22,7,56,24,23,23,112,24,24,24,24,24,24,24,24,24};
int main(void){for(unsigned i=0;i<126;i++){double x=cb_at(i);fwrite(&x,8,1,stdout);}return 0;}
