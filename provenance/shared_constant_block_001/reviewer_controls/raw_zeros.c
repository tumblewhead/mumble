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
const unsigned char cb_blob[]={7,132,1,0,0,2,2,1,1,4,3,2,2,8,4,3,3,16,5,4,4,32,6,5,5,64,7,6,6,128,7,7,7,7,7,7,7,7,5};
int main(void){for(unsigned i=0;i<132;i++){double x=cb_at(i);fwrite(&x,8,1,stdout);}return 0;}
