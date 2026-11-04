/* Stationary rank3/f64 rowwise bank inference. Serialized owner, no heap.
   External arrays have fixed documented lengths and do not alias context.
   All pointers must remain valid through the call. Configuration is immutable.
   Input evidence transport/ownership remains the campaign's responsibility. */
#include <float.h>
#define step br_step
#define variance br_variance
#define rebuild br_rebuild
#define acquire br_acquire
#define release br_release

#include "../bank_memory_001/scratch_kernel.c"
#define WIDTH 34

typedef struct {
 const double *mean,*scale,*center,*map,*knots,*projected_map;
 double hu;
 const double *legacy,*free_rc,*forced_rc;
} model;
typedef struct {
 inference qr;
 double anchor[16],point[16],trial[16],delta[16],phi[WIDTH];
 model m;
 double cost,grad_inf,decrement;
 unsigned rounds,rejections,stop;
} core;
size_t core_bytes(void){return sizeof(core);}
static double chart(const model *m,const double *w,unsigned i){return m->mean[i]+m->scale[i]*w[i];}
static double cheb(double t,unsigned n){return n==0?1:n==1?t:2*t*t-1;}
static double dcheb(double t,unsigned n){return n==0?0:n==1?1:4*t;}
static void spline(const model *m,double u,unsigned pole,int projected,double *v,double *d){
 *v=0;*d=0;
 for(unsigned j=0;j<27;j++){
  double x=(u-m->knots[j])/m->hu,t=fabs(x),b=0,db=0;
  if(t<=1){b=(4-6*t*t+3*t*t*t)/6;db=(-2*t+1.5*t*t);}
  else if(t<2){b=(2-t)*(2-t)*(2-t)/6;db=-.5*(2-t)*(2-t);}
  db*=x<0?-1:x>0?1:0;db/=m->hu;
  double a=(projected?m->projected_map:m->map)[27*pole+j];*v+=a*b;*d+=a*db;
 }
}
/* Domain matches the original full bank, not a narrowed reduced-basis domain. */
static int supported(const model *m,const double *w){
 for(unsigned j=0;j<16;j++)if(!isfinite(w[j])||!isfinite(chart(m,w,j)))return -1;
 double q=exp(-chart(m,w,5)),s=0;
 if(!(q>0)||!isfinite(q))return -1;
 double z=chart(m,w,0);
 if(z-q*m->legacy[38]<0||z-q*m->legacy[37]>1)return -1;
 for(unsigned j=0;j<3;j++){
  s+=exp(chart(m,w,8+2*j));double u=log(s/m->center[j]);
  if(!isfinite(u)||fabs(u)>1)return -1;
 }
 for(unsigned j=6;j<16;j++)if(!isfinite(exp(chart(m,w,j)))||!(exp(chart(m,w,j))>0))return -1;
 for(unsigned j=0;j<2;j++){
  double u=chart(m,w,14+j)-chart(m,w,5)-log(m->center[3+j]);
  if(!isfinite(u)||fabs(u)>1+1e-12)return -1;
 }
 return 0;
}
/* One feature and one derivative row, physical chart coordinates. */
static int feature(const model *m,const double *w,unsigned row,int full,double *value,double *d){
 unsigned n=full?13:3,hstart=3+6*n;
 memset(d,0,16*sizeof(double));*value=0;
 if(row==0){*value=chart(m,w,0);d[0]=1;}
 else if(row==1){*value=exp(-chart(m,w,5));d[5]=-*value;}
 else if(row==2){*value=exp(chart(m,w,6));d[6]=*value;}
 else if(row<hstart){
  unsigned block=(row-3)/n,j=(row-3)%n,b=block/2,forced=block%2;
  double tau=0;
  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));
  double v,dv;spline(m,log(tau/m->center[b]),j,!full,&v,&dv);
  unsigned ai=forced?7+2*b:1+b;double a=forced?exp(chart(m,w,ai)):chart(m,w,ai);
  *value=a*v;d[ai]=forced?*value:v;
  for(unsigned k=0;k<=b;k++)d[8+2*k]=a*dv*exp(chart(m,w,8+2*k))/tau;
 }else if(row<hstart+12){
  static const unsigned ip[6]={0,0,0,1,1,2},jp[6]={0,1,2,0,1,0};
  unsigned k=(row-hstart)%6,free=(row-hstart)/6;
  double tp=chart(m,w,14)-chart(m,w,5)-log(m->center[3]);
  double tm=chart(m,w,15)-chart(m,w,5)-log(m->center[4]);
  double H=exp(chart(m,w,13)),eta=chart(m,w,4),h=tanh(eta),a=H*(free?h:1);
  double v=cheb(tp,ip[k])*cheb(tm,jp[k]);
  double dp=dcheb(tp,ip[k])*cheb(tm,jp[k]),dm=cheb(tp,ip[k])*dcheb(tm,jp[k]);
  *value=a*v;d[13]=*value;d[14]=a*dp;d[15]=a*dm;d[5]=-a*(dp+dm);
  double e=exp(-2*fabs(eta));if(free)d[4]=H*4*e/((1+e)*(1+e))*v;
 }else if(row==hstart+12)*value=1;
 else return -1;
 if(!isfinite(*value))return -1;
 for(unsigned k=0;k<16;k++)if(!isfinite(d[k]))return -1;
 return 0;
}
static int emit(void *ctx,unsigned row,double *out){
 core *c=ctx;double value;
 if(feature(&c->m,c->point,row,0,&value,out))return -1;
 for(unsigned k=0;k<16;k++)out[k]*=c->m.scale[k];
 return 0;
}
int bind(core *c,const model *m){
 if(!c||!m||!m->mean||!m->scale||!m->center||!m->map||!m->knots||!m->projected_map||!m->legacy||!m->free_rc||!m->forced_rc||!(m->hu>0))return -1;
 for(unsigned k=0;k<16;k++)if(!isfinite(m->mean[k])||!isfinite(m->scale[k])||!(m->scale[k]>0))return -1;
 for(unsigned k=0;k<5;k++)if(!isfinite(m->center[k])||!(m->center[k]>0))return -1;
 c->m=*m;return 0;
}
int row_query(core *c,const double *w,unsigned row,double *value,double *derivative_out){
 if(supported(&c->m,w))return -1;
 return feature(&c->m,w,row,0,value,derivative_out);
}
static double cost_at(core *c,const double *history,const double *w){
 if(supported(&c->m,w))return NAN;
 /* The derivative scratch is dead here; no nested acquisition. */
 for(unsigned j=0;j<WIDTH;j++)if(feature(&c->m,w,j,0,c->phi+j,c->qr.scratch.fit.d))return NAN;
 double cost=0;
 for(unsigned j=0;j<16;j++)cost+=.5*w[j]*w[j];
 for(unsigned i=0;i<WIDTH;i++){
  double r=0;for(unsigned j=i;j<WIDTH;j++)r+=history[index_of(WIDTH,i,j)]*c->phi[j];
  cost+=.5*r*r;
 }
 return cost;
}
static int evaluate(core *c,const double *history,const double *w){
 c->cost=cost_at(c,history,w);if(!isfinite(c->cost))return -1;
 memmove(c->point,w,16*sizeof(double));
 if(rebuild(&c->qr,WIDTH,history,c->phi,c->point,emit,c))return -1;
 c->grad_inf=0;c->decrement=0;
 for(unsigned i=0;i<16;i++){
  double g=0;for(unsigned j=0;j<=i;j++)g+=c->qr.factor[index_of(17,j,i)]*c->qr.factor[index_of(17,j,16)];
  if(fabs(g)>c->grad_inf)c->grad_inf=fabs(g);
  double t=c->qr.factor[index_of(17,i,16)];c->decrement+=t*t;
 }
 return isfinite(c->grad_inf)&&isfinite(c->decrement)?0:-1;
}
/* Fresh original-prior linearization. Does not add a posterior as evidence. */
int initialize(core *c,const double *history,const double *w){
 c->qr.lease.valid=0;
 if(evaluate(c,history,w))return -1;
 memcpy(c->anchor,w,16*sizeof(double));return 0;
}
/* Same60-round/18halving line search and stopping rule as desktop reference.
   Cost probes need phi only. Rebuild current tangent on rejected refresh outside.
   No covariance/inverse/normal-matrix assembly occurs here. */
int fit(core *c,const double *history,const double *start){
 c->stop=3;c->rounds=0;c->rejections=0;c->qr.lease.valid=0;
 if(evaluate(c,history,start))return -1;
 for(unsigned iteration=0;iteration<60;iteration++){
  c->rounds=iteration+1;
  double mag=fmax(fabs(c->cost),1),ulp=nextafter(mag,INFINITY)-mag;
  if(c->decrement<=32*ulp){c->stop=1;break;}
  if(c->grad_inf<1e-6){c->stop=2;break;}
  if(step(&c->qr,c->delta))return -1;
  int accepted=0;
  for(unsigned power=0;power<18;power++){
   double a=ldexp(1.,-(int)power);
   for(unsigned j=0;j<16;j++)c->trial[j]=c->point[j]+a*c->delta[j];
   double cost=cost_at(c,history,c->trial);
   if(!isfinite(cost)){c->rejections++;continue;}
   if(cost<c->cost){if(evaluate(c,history,c->trial))return -1;accepted=1;break;}
  }
  if(!accepted){c->stop=4;break;}
 }
 /* Recompute phi at accepted point after any rejected probe. */
 if(evaluate(c,history,c->point))return -1;
 return 0;
}
int append(core *c,const double *rows,unsigned count){
 if(!c->qr.lease.valid)return -1;
 /* Fixed-anchor tangent; incoming rows already own disjoint new observations. */
 memcpy(c->point,c->anchor,sizeof(c->point));
 for(unsigned i=0;i<count;i++){
  double *out=c->qr.scratch.fit.row,*d=c->qr.scratch.fit.d;
  memset(out,0,17*sizeof(double));
  for(unsigned j=0;j<WIDTH;j++){
   double v;if(feature(&c->m,c->anchor,j,0,&v,d))goto fail;
   double a=rows[i*WIDTH+j];if(!isfinite(a))goto fail;
   for(unsigned k=0;k<16;k++)out[k]+=a*d[k]*c->m.scale[k];
   out[16]+=a*v;
  }
  if(qr_insert(c->qr.factor,17,out))goto fail;
 }
 return 0;
fail:c->qr.lease.valid=0;return -1;
}
static int transported(core *c,unsigned coordinate,double *value,double *d);
int estimate(core *c){
 if(step(&c->qr,c->delta))return -1;
 for(unsigned k=0;k<16;k++)c->point[k]=c->anchor[k]+c->delta[k];
 if(supported(&c->m,c->point))return -1;
 double value;
 if(transported(c,0,&value,c->trial)||value<0||value>1)return -1;
 return transported(c,4,&value,c->trial);
}
/* Full-bank endpoint transport row, deliberately not projected. Returns chart
   coordinate and its gradient in original whitened coordinates. */
static int transported(core *c,unsigned coordinate,double *value,double *d){
 const model *m=&c->m;double *w=c->point;memset(d,0,16*sizeof(double));
 if(coordinate>=16)return -1;
 if(coordinate>=5){*value=chart(m,w,coordinate);d[coordinate]=m->scale[coordinate];return 0;}
 if(coordinate==0){double q=exp(-chart(m,w,5));*value=chart(m,w,0)-q*m->legacy[36];d[0]=1;d[5]=q*m->legacy[36];}
 else if(coordinate<4){
  unsigned b=coordinate-1;double tau=0,vf=0,ff=0,dvf=0,dff=0;
  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));
  double u=log(tau/m->center[b]);
  for(unsigned j=0;j<13;j++){
   double v,dv;spline(m,u,j,0,&v,&dv);
   vf+=v*m->free_rc[13*b+j];ff+=v*m->forced_rc[13*b+j];dvf+=dv*m->free_rc[13*b+j];dff+=dv*m->forced_rc[13*b+j];
  }
  double bv=chart(m,w,1+b),R=exp(chart(m,w,7+2*b));*value=bv*vf+R*ff;d[1+b]=vf;d[7+2*b]=R*ff;
  for(unsigned k=0;k<=b;k++)d[8+2*k]=(bv*dvf+R*dff)*exp(chart(m,w,8+2*k))/tau;
 }else{
  /* TaylorH2 raw jets order00,10,01,20,11,02; same p2 projection. */
  double tp=chart(m,w,14)-chart(m,w,5)-log(m->center[3]),tm=chart(m,w,15)-chart(m,w,5)-log(m->center[4]);
  double vals[2],dp[2],dm[2];
  for(unsigned k=0;k<2;k++){
   const double *s=m->legacy+18+9*k;
   vals[k]=s[0]+s[1]*tp+s[2]*tm+.5*s[3]*tp*tp+s[4]*tp*tm+.5*s[5]*tm*tm;
   dp[k]=s[1]+s[3]*tp+s[4]*tm;dm[k]=s[2]+s[4]*tp+s[5]*tm;
  }
  double eta=chart(m,w,4),h0=tanh(eta),h=vals[1]+vals[0]*h0,e=exp(-2*fabs(eta));
  if(!(fabs(h)<1))return -1;
  *value=atanh(h);d[4]=vals[0]*4*e/((1+e)*(1+e))/(1-h*h);
  d[14]=(dp[1]+dp[0]*h0)/(1-h*h);d[15]=(dm[1]+dm[0]*h0)/(1-h*h);d[5]=-d[14]-d[15];
 }
 for(unsigned k=0;k<16;k++)d[k]*=m->scale[k];
 return isfinite(*value)?0:-1;
}
/* Scalar API: after successful estimate(), one endpoint chart marginal at a
   time. estimate validates the full dynamic endpoint support, even for Q-only
   queries. No covariance output buffer. */
int scalar(core *c,unsigned coordinate,double *value,double *var){
 if(!c->qr.lease.valid||supported(&c->m,c->point))return -1;
 if(transported(c,coordinate,value,c->trial))return -1;
 if(coordinate==0&&(*value<0||*value>1))return -1;
 return variance(&c->qr,c->trial,var);
}
/* Optional host adapter emits a single whitened covariance-root row at a time.
   The embedded scalar interface does not need this compatibility operation. */
int root_row(core *c,unsigned coordinate,double *value,double *out){
 double v;if(scalar(c,coordinate,value,&v))return -1;
 memcpy(out,c->qr.scratch.y,16*sizeof(double));return 0;
}
