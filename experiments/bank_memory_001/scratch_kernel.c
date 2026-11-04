/* Isolated inference kernel. Not yet the campaign solver or a firmware port.
   Caller owns immutable packed history, phi, anchor and derivative generator.
   Serialized calls only: leases are NOT interrupt/thread synchronization.
   Preconditions: context is double-aligned and initially all-zero; every
   pointer has its declared full extent; caller inputs/outputs do not alias
   context or one another. emit fills all 16 derivatives deterministically at
   the same fixed parameter point, without reentry or mutation of these inputs.
   Width/history/phi and callback-generated derivatives must describe the same
   represented likelihood. Prior is identity in whitened coordinates only.
   Caller arrays, callback workspace, stack/libm and synchronization are NOT
   included in inference_bytes(). No firmware or lifetime bound is claimed. */
#include <stdint.h>
#include <stddef.h>
#include <math.h>
#include <string.h>
#define STORE_DOUBLE 1
#define insert qr_insert
#include "qr.c"
#undef insert

typedef int (*derivative)(void *, unsigned, double *);
typedef struct { uint64_t generation; uint32_t owner, valid; } registry;
typedef struct {
 double factor[153];
 union { struct {double d[16], row[17];} fit; double y[16]; } scratch;
 registry lease;
} inference;
size_t inference_bytes(void){return sizeof(inference);}
size_t lease_bytes(void){return sizeof(registry);}
static size_t index_of(unsigned n,unsigned i,unsigned j){return i*n-i*(i-1)/2+j-i;}
uint64_t acquire(inference *s,unsigned owner){
 if(!owner || s->lease.owner || s->lease.generation==UINT64_MAX)return 0;
 s->lease.owner=owner;return ++s->lease.generation;
}
int release(inference *s,unsigned owner,uint64_t generation){
 if(!owner || s->lease.owner!=owner || s->lease.generation!=generation)return -1;
 s->lease.owner=0;return 0;
}
/* Rebuild GN square root, retaining all joint cross terms, with original
   whitened prior [I, anchor]. No dense history copy or W-by-16 Jacobian. */
int rebuild(inference *s,unsigned width,const double *history,const double *phi,
 const double *anchor,derivative emit,void *context){
 if(width<1 || width>94 || !history || !phi || !anchor || !emit)return -1;
 uint64_t g=acquire(s,1);if(!g)return -2;
 s->lease.valid=0;memset(s->factor,0,sizeof(s->factor));
 double *r=s->scratch.fit.row,*d=s->scratch.fit.d;
 for(unsigned i=0;i<16;i++){
  memset(r,0,17*sizeof(double));r[i]=1;r[16]=anchor[i];
  if(!isfinite(anchor[i]) || qr_insert(s->factor,17,r))goto failed;
 }
 for(unsigned i=0;i<width;i++){
  memset(r,0,17*sizeof(double));
  for(unsigned j=i;j<width;j++){
   double a=history[index_of(width,i,j)];
   if(!isfinite(a)||!isfinite(phi[j])||emit(context,j,d))goto failed;
   for(unsigned k=0;k<16;k++){if(!isfinite(d[k]))goto failed;r[k]+=a*d[k];}
   r[16]+=a*phi[j];
  }
  if(qr_insert(s->factor,17,r))goto failed;
 }
 for(unsigned i=0;i<16;i++)if(!(s->factor[index_of(17,i,i)]>0))goto failed;
 s->lease.valid=1;return release(s,1,g);
failed:
 release(s,1,g);return -1;
}
/* Writes only a fully computed finite step; invalid inference refuses queries. */
int step(inference *s,double *out){
 uint64_t g=acquire(s,2);if(!g)return -2;
 if(!s->lease.valid || !out)goto failed;
 double *y=s->scratch.y;
 for(int i=15;i>=0;i--){
  double x=-s->factor[index_of(17,i,16)];
  for(unsigned j=i+1;j<16;j++)x-=s->factor[index_of(17,i,j)]*y[j];
  y[i]=x/s->factor[index_of(17,i,i)];if(!isfinite(y[i]))goto failed;
 }
 memcpy(out,y,16*sizeof(double));return release(s,2,g);
failed:
 release(s,2,g);return -1;
}
int variance(inference *s,const double *gradient,double *out){
 uint64_t g=acquire(s,2);if(!g)return -2;
 if(!s->lease.valid || !gradient || !out)goto failed;
 double *y=s->scratch.y,total=0;
 for(unsigned i=0;i<16;i++){
  double x=gradient[i];
  for(unsigned j=0;j<i;j++)x-=s->factor[index_of(17,j,i)]*y[j];
  y[i]=x/s->factor[index_of(17,i,i)];total+=y[i]*y[i];
 }
 if(!isfinite(total))goto failed;
 *out=total;return release(s,2,g);
failed:
 release(s,2,g);return -1;
}
