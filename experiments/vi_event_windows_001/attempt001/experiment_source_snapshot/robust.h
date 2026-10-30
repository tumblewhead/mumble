/* Experimental scale mixture; no truth, event score or fault mask inputs. */
#ifndef EXP_EPS
#define EXP_EPS 0.001
#endif
#ifndef EXP_SCALE
#define EXP_SCALE 20.0
#endif
/* rho excludes log(sigma)+log(2*pi)/2. weight*r is its exact derivative.
 * weight is EM complete-data precision, NOT the observed mixture Hessian. */
double experiment_noise(double r,double *weight,double *ordinary) {
    if(EXP_EPS==0.) {*weight=1.;*ordinary=1.;return .5*r*r;}
    double a=log1p(-EXP_EPS)-.5*r*r;
    double b=log(EXP_EPS)-log(EXP_SCALE)-.5*(r/EXP_SCALE)*(r/EXP_SCALE);
    double top=fmax(a,b),aa=exp(a-top),bb=exp(b-top);
    *ordinary=aa/(aa+bb);*weight=*ordinary+(1.-*ordinary)/(EXP_SCALE*EXP_SCALE);
    return -top-log(aa+bb);
}
static double experiment_rho(double r) {double w,p;return experiment_noise(r,&w,&p);}
static double experiment_sqrt_weight(double r) {double w,p;experiment_noise(r,&w,&p);return sqrt(w);}
int experiment_token(const double *anchor,const FBPhysical *ph,const double *obs,int n,int encoding,unsigned char *token) {
    if(EXP_EPS==0.)return fb_token(anchor,ph,obs,n,encoding,token);
    if(n<1||n>16)return FB_INPUT;
    double adjusted[80],correction=0.;memcpy(adjusted,obs,(size_t)n*5*sizeof(double));
    for(int i=0;i<n;i++) {
        double r=(ph->v[i]-obs[5*i+3])/obs[5*i+4],w,p;
        double rho=experiment_noise(r,&w,&p);
        adjusted[5*i+4]=obs[5*i+4]/sqrt(w);
        correction+=rho-.5*w*r*r+.5*log(w);
    }
    int bytes=fb_token(anchor,ph,adjusted,n,encoding,token);
    if(bytes<0)return bytes;
    /* Token's binary64 constant follows tag, anchor16, end16. */
    uint64_t bits=0;double constant;
    for(int i=0;i<8;i++)bits|=(uint64_t)token[257+i]<<(8*i);
    memcpy(&constant,&bits,8);constant+=correction;
    if(!isfinite(constant))return FB_NUMERIC;
    memcpy(&bits,&constant,8);
    for(int i=0;i<8;i++)token[257+i]=(unsigned char)((bits>>(8*i))&255);
    return bytes;
}
