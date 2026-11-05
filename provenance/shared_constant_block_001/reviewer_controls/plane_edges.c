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
 for(unsigned k=0;k<8;k++){bytes[k]=cb_byte(p,k*p[1]+i);}
 memcpy(&v,bytes,8);return v;
}

static inline double cb_get(const unsigned short *segment,unsigned i){return cb_at(*segment+i);}
#include <stdio.h>
const unsigned char cb_blob[]={24,126,2,0,0,2,3,2,2,4,4,255,3,5,5,4,2,7,6,5,5,14,7,6,6,28,8,0,1,2,9,255,2,3,10,7,7,56,11,127,255,2,12,8,2,4,13,12,8,6,14,9,0,4,15,14,240,5,16,15,240,6,17,16,248,7,18,9,128,4,19,18,11,6,20,13,255,7,21,17,17,14,22,19,127,7,23,20,20,14,24,22,22,14,25,10,10,112,23,23,23,23,23,23,23,23,20,13,25,25,25,25,25,10,6,21,21,21,21,21,21,21,21,21,24,24,24,24,24,24,24,24,22,19,11};
int main(void){for(unsigned i=0;i<126;i++){double x=cb_at(i);fwrite(&x,8,1,stdout);}return 0;}
