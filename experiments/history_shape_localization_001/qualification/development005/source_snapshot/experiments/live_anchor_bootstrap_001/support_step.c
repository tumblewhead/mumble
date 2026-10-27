#include "support_step.h"
#include <float.h>
#include <math.h>
#include <string.h>

typedef char ss_binary64[(sizeof(double)==8 && DBL_MANT_DIG==53 &&
                         DBL_MAX_EXP==1024) ? 1 : -1];
typedef char ss_workspace_budget[(sizeof(ss_workspace)==1600) ? 1 : -1];
typedef char ss_result_budget[(sizeof(ss_result)<=120) ? 1 : -1];

typedef struct { double sum, correction; } ss_sum;
typedef struct {
    double q0, qscale, qlo, qhi, zlo, zhi;
    double lower_a, lower_c, upper_a, upper_c, zscale;
} ss_geometry;

size_t ss_workspace_bytes(void) { return sizeof(ss_workspace); }
size_t ss_input_bytes(void) { return sizeof(ss_input); }
size_t ss_result_bytes(void) { return sizeof(ss_result); }

static size_t ix(unsigned i,unsigned j)
{
    unsigned k;if(j>i){k=i;i=j;j=k;}
    return (size_t)i*(i+1u)/2u+j;
}

static int overlaps(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<=y ? y-x<na : x-y<nb;
}

static int sum_add(ss_sum *s,double x)
{
    double n,e;
    if(!isfinite(x))return 0;
    n=s->sum+x;if(!isfinite(n))return 0;
    e=fabs(s->sum)>=fabs(x)?(s->sum-n)+x:(x-n)+s->sum;
    s->sum=n;s->correction+=e;
    return isfinite(s->correction) && isfinite(s->sum+s->correction);
}

static double value(const ss_sum *s) { return s->sum+s->correction; }
static double up(double x) { return x==0.?0.:nextafter(x,INFINITY); }
static double add_up(double a,double b)
{
    if(a==0.)return b;
    if(b==0.)return a;
    return up(a+b);
}

/* The enlarged operation counts cover products/differences and compensated
 * summation of computed operands. eta terms also cover gradual underflow,
 * including multiplication by a second bounded proposal coordinate. These
 * guards do not certify the supplied gradient/metric or exp/log evaluation.
 */
static double allowance(unsigned operations,double scale,double multiplier)
{
    double u=DBL_EPSILON/2.,nu=operations*u;
    double gamma=up(nu/(1.-nu));
    double relative=up(gamma*scale);
    double absolute=up(up((operations+1.)*0x0.0000000000001p-1022)*
                       add_up(1.,multiplier));
    return add_up(relative,absolute);
}

static int original_support(const ss_input *in,const double *x,
                            double *support,double *step)
{
    double s=DBL_MAX,t=DBL_MAX,Q,zlo,zhi,d;unsigned i;
    for(i=0;i<SS_DIM;i++) {
        if(!isfinite(x[i]))return 0;
        s=fmin(s,fmin(x[i]-in->lower[i],in->upper[i]-x[i]));
        d=fabs(x[i]-in->anchor[i])/in->sd[i];
        if(!isfinite(d))return 0;
        t=fmin(t,1.-d);
    }
    Q=exp(x[5]);if(!isfinite(Q) || !(Q>0.))return 0;
    /* Preserve the model's division order, not charge*exp(-logQ). */
    zlo=x[11]-in->charge_max_Ah/Q;
    zhi=x[11]-in->charge_min_Ah/Q;
    if(!isfinite(zlo) || !isfinite(zhi))return 0;
    *support=fmin(s,fmin(zlo,1.-zhi));*step=t;
    return 1;
}

static int validate(const ss_input *in,const ss_workspace *w,
                    const ss_result *r)
{
    const double *p;double s,t;unsigned i,j;
    if(!in || !w || !r || !in->anchor || !in->sd || !in->lower ||
       !in->upper)return SS_ERR_ARGUMENT;
    if(overlaps(w,sizeof(*w),r,sizeof(*r)) ||
       overlaps(in,sizeof(*in),w,sizeof(*w)) ||
       overlaps(in,sizeof(*in),r,sizeof(*r)))return SS_ERR_ALIAS;
    for(j=0;j<4;j++) {
        p=j==0?in->anchor:j==1?in->sd:j==2?in->lower:in->upper;
        if(overlaps(p,SS_DIM*sizeof(double),w,sizeof(*w)) ||
           overlaps(p,SS_DIM*sizeof(double),r,sizeof(*r)))return SS_ERR_ALIAS;
    }
    if(!isfinite(in->charge_min_Ah) || !isfinite(in->charge_max_Ah))
        return SS_ERR_NONFINITE;
    if(in->charge_min_Ah>0. || in->charge_max_Ah<0. ||
       in->charge_min_Ah>in->charge_max_Ah)return SS_ERR_DOMAIN;
    for(i=0;i<SS_DIM;i++) {
        if(!isfinite(in->anchor[i]) || !isfinite(in->sd[i]) ||
           !isfinite(in->lower[i]) || !isfinite(in->upper[i]) ||
           !isfinite(w->gradient[i]))return SS_ERR_NONFINITE;
        if(!(in->sd[i]>0.) || in->lower[i]>in->upper[i] ||
           in->anchor[i]<in->lower[i] || in->anchor[i]>in->upper[i])
            return SS_ERR_DOMAIN;
    }
    for(i=0;i<SS_PACKED;i++)if(!isfinite(w->packed[i]))return SS_ERR_NONFINITE;
    if(!original_support(in,in->anchor,&s,&t))return SS_ERR_NONFINITE;
    return s>=0.?SS_OK:SS_ERR_DOMAIN;
}

static int geometry(const ss_input *in,ss_geometry *p)
{
    double lo=fmax(in->lower[5],in->anchor[5]-in->sd[5]);
    double hi=fmin(in->upper[5],in->anchor[5]+in->sd[5]);
    p->q0=exp(-in->anchor[5]);p->qscale=p->q0*in->sd[5];
    if(!isfinite(p->q0) || !isfinite(p->qscale) || !(p->q0>0.) ||
       !(p->qscale>0.))return 0;
    p->qlo=(exp(-hi)-p->q0)/p->qscale;
    p->qhi=(exp(-lo)-p->q0)/p->qscale;
    p->zlo=fmax(-1.,(in->lower[11]-in->anchor[11])/in->sd[11]);
    p->zhi=fmin(1.,(in->upper[11]-in->anchor[11])/in->sd[11]);
    p->lower_a=in->charge_max_Ah*p->qscale;
    p->lower_c=in->anchor[11]-in->charge_max_Ah*p->q0;
    p->upper_a=-in->charge_min_Ah*p->qscale;
    p->upper_c=1.-in->anchor[11]+in->charge_min_Ah*p->q0;
    p->zscale=in->sd[11];
    return isfinite(p->qlo) && isfinite(p->qhi) && isfinite(p->zlo) &&
           isfinite(p->zhi) && isfinite(p->lower_a) &&
           isfinite(p->lower_c) && isfinite(p->upper_a) &&
           isfinite(p->upper_c) && p->qlo<=p->qhi && p->zlo<=p->zhi;
}

/* a*x+b*y<=c. All six are generated from scalars, never stored as arrays. */
static void plane(const ss_geometry *p,unsigned k,double *a,double *b,double *c)
{
    switch(k) {
        case 0:*a=-1.;*b=0.;*c=-p->qlo;break;
        case 1:*a=1.;*b=0.;*c=p->qhi;break;
        case 2:*a=0.;*b=-1.;*c=-p->zlo;break;
        case 3:*a=0.;*b=1.;*c=p->zhi;break;
        case 4:*a=p->lower_a;*b=-p->zscale;*c=p->lower_c;break;
        default:*a=p->upper_a;*b=p->zscale;*c=p->upper_c;break;
    }
}

static int feasible(const ss_geometry *p,double x,double y,ss_result *r,
                    double *minimum)
{
    double a,b,c,v,s=DBL_MAX;unsigned k;int ok=1;
    if(!isfinite(x) || !isfinite(y))return -1;
    for(k=0;k<SS_PLANES;k++) {
        plane(p,k,&a,&b,&c);v=c-(a*x+b*y);++r->plane_tests;
        if(!isfinite(v))return -1;
        s=fmin(s,v);if(v<0.)ok=0;
    }
    if(minimum)*minimum=s;
    return ok;
}

/* Returns the weighted closest point to (tx,ty) on one feasible edge segment.
 * The endpoint limits enumerate vertices too. Parallel/redundant constraints
 * are explicit; no zero denominator is divided. Every edge tests all planes.
 */
static int edge_point(const ss_geometry *p,unsigned edge,double tx,double ty,
                      double mx,double my,double *x,double *y,ss_result *r)
{
    double a,b,c,scale,px,py,vx,vy,lo=-DBL_MAX,hi=DBL_MAX;
    double aa,bb,cc,den,num,t,w,s;unsigned k;int empty=0;
    plane(p,edge,&a,&b,&c);++r->edges_considered;
    scale=fmax(fabs(a),fabs(b));
    if(!(scale>0.) || !isfinite(scale))return -1;
    a/=scale;b/=scale;c/=scale;
    if(!isfinite(c))return -1;
    if(fabs(a)>=fabs(b)){px=c/a;py=0.;}else{px=0.;py=c/b;}
    vx=-b;vy=a;
    for(k=0;k<SS_PLANES;k++) {
        plane(p,k,&aa,&bb,&cc);++r->plane_tests;
        /* This supporting line defines the parameterization. Intersecting it
         * with its unnormalized copy can manufacture a rounded nonzero
         * denominator. Final strict feasibility still checks all six planes.
         */
        if(k==edge)continue;
        den=aa*vx+bb*vy;num=cc-(aa*px+bb*py);
        if(!isfinite(den) || !isfinite(num))return -1;
        if(den==0.){if(num<0.)empty=1;continue;}
        t=num/den;if(!isfinite(t))return -1;
        if(den>0.)hi=fmin(hi,t);else lo=fmax(lo,t);
    }
    if(empty || lo>hi)return 0;
    w=(mx*vx)*vx+(my*vy)*vy;
    s=(mx*vx)*(tx-px)+(my*vy)*(ty-py);
    if(!(w>0.) || !isfinite(w) || !isfinite(s))return -1;
    s/=w;if(!isfinite(s))return -1;
    s=fmax(lo,fmin(hi,s));
    *x=px+s*vx;*y=py+s*vy;
    return isfinite(*x) && isfinite(*y)?1:-1;
}

static int scaled_metric(const ss_input *in,ss_workspace *w,ss_result *r)
{
    double si,sj,a,m;unsigned i,j;
    for(i=0;i<SS_DIM;i++)for(j=0;j<=i;j++) {
        si=i==5?-in->sd[i]:in->sd[i];
        sj=j==5?-in->sd[j]:in->sd[j];
        /* One outer-product scale gives one symmetric stored entry. */
        a=w->packed[ix(i,j)]*(si*sj);
        if(!isfinite(a))return -1;
        w->packed[ix(i,j)]=a;
    }
    r->minimum_majorizer=DBL_MAX;
    for(i=0;i<SS_DIM;i++) {
        m=0.;for(j=0;j<SS_DIM;j++)m=add_up(m,fabs(w->packed[ix(i,j)]));
        if(!isfinite(m))return -1;
        if(!(m>0.))return 0;
        w->majorizer[i]=m;r->minimum_majorizer=fmin(r->minimum_majorizer,m);
        si=i==5?-in->sd[i]:in->sd[i];
        a=si*w->gradient[i];w->direction[i]=-a/m;
        if(!isfinite(a) || !isfinite(w->direction[i]))return -1;
    }
    return 1;
}

static double pair_cost(double x,double y,double hx,double hy,double mx,double my)
{
    return hx*x+hy*y+.5*((mx*x)*x+(my*y)*y);
}

static int select_point(const ss_input *in,const ss_geometry *p,
                        ss_workspace *w,ss_result *r)
{
    double hx=-in->sd[5]*w->gradient[5],hy=in->sd[11]*w->gradient[11];
    double best=0.,x=0.,y=0.,v,lo,hi,q;unsigned i,k;int status;
    status=feasible(p,0.,0.,r,&r->min_polygon_slack);
    if(status<0)return -1;
    if(!status)return 0; /* represented reciprocal chart lost anchor feasibility */
    r->selected_candidate=UINT32_MAX;r->candidates_considered=1;
    w->point[5]=0.;w->point[11]=0.;
    for(k=0;k<=SS_PLANES;k++) {
        if(k==0){x=w->direction[5];y=w->direction[11];}
        else {
            status=edge_point(p,k-1,w->direction[5],w->direction[11],
                              w->majorizer[5],w->majorizer[11],&x,&y,r);
            if(status<0)return -1;
            if(!status)continue;
        }
        ++r->candidates_considered;
        status=feasible(p,x,y,r,NULL);
        if(status<0)return -1;
        if(!status)continue;
        v=pair_cost(x,y,hx,hy,w->majorizer[5],w->majorizer[11]);
        if(!isfinite(v))return -1;
        if(v<best){best=v;w->point[5]=x;w->point[11]=y;r->selected_candidate=k;}
    }
    for(i=0;i<SS_DIM;i++)if(i!=5 && i!=11) {
        lo=fmax(-1.,(in->lower[i]-in->anchor[i])/in->sd[i]);
        hi=fmin(1.,(in->upper[i]-in->anchor[i])/in->sd[i]);
        w->point[i]=fmax(lo,fmin(hi,w->direction[i]));
    }
    for(i=0;i<SS_DIM;i++)w->direction[i]=w->point[i];
    status=feasible(p,w->direction[5],w->direction[11],r,&r->min_polygon_slack);
    if(status<0)return -1;
    if(!status)return 0;
    for(i=0;i<SS_DIM;i++) {
        if(i==5) {
            /* Exact zero step preserves the supplied anchor bits. */
            if(w->direction[i]==0.)w->point[i]=in->anchor[i];
            else {
                q=p->q0+p->qscale*w->direction[i];
                if(!isfinite(q) || !(q>0.))return -1;
                w->point[i]=-log(q);
            }
        } else w->point[i]=in->anchor[i]+in->sd[i]*w->direction[i];
        if(!isfinite(w->point[i]))return -1;
    }
    return 1;
}

static int diagnostics(const ss_input *in,const ss_workspace *w,ss_result *r)
{
    ss_sum original={0.,0.},linear={0.,0.},quadratic={0.,0.},diagonal={0.,0.};
    double ao=0.,al=0.,aq=0.,ad=0.,ag=0.,mt=0.,d,h,p;unsigned i,j;
    for(i=0;i<SS_DIM;i++) {
        d=w->point[i]-in->anchor[i];p=w->gradient[i]*d;++r->dot_products;
        if(!sum_add(&original,p))return 0;
        ao=add_up(ao,fabs(p));
        ag=add_up(ag,fabs(w->gradient[i]));
        h=(i==5?-in->sd[i]:in->sd[i])*w->gradient[i];
        p=h*w->direction[i];++r->dot_products;
        if(!sum_add(&linear,p))return 0;
        al=add_up(al,fabs(p));
        p=(w->majorizer[i]*w->direction[i])*w->direction[i];
        ++r->quadratic_products;
        if(!sum_add(&diagonal,p))return 0;
        ad=add_up(ad,fabs(p));
        mt=fmax(mt,fabs(w->direction[i]));
        for(j=0;j<SS_DIM;j++) {
            p=(w->packed[ix(i,j)]*w->direction[i])*w->direction[j];
            ++r->quadratic_products;
            if(!sum_add(&quadratic,p))return 0;
            aq=add_up(aq,fabs(p));
        }
    }
    r->original_slope=-value(&original);
    r->original_slope_allowance=allowance(256,ao,ag);
    r->tangent_model_decrease=-(value(&linear)+.5*value(&quadratic));
    r->tangent_model_allowance=allowance(8192,add_up(al,up(.5*aq)),mt);
    r->diagonal_model_decrease=-(value(&linear)+.5*value(&diagonal));
    r->diagonal_model_allowance=allowance(1024,add_up(al,up(.5*ad)),mt);
    return isfinite(r->original_slope) && isfinite(r->original_slope_allowance) &&
           isfinite(r->tangent_model_decrease) && isfinite(r->tangent_model_allowance) &&
           isfinite(r->diagonal_model_decrease) && isfinite(r->diagonal_model_allowance);
}

static int cholesky(ss_workspace *w,ss_result *r)
{
    double v;unsigned i,j,k;
    for(i=0;i<SS_DIM;i++)for(j=0;j<=i;j++) {
        v=w->packed[ix(i,j)];++r->cholesky_entries;
        for(k=0;k<j;k++){v-=w->packed[ix(i,k)]*w->packed[ix(j,k)];++r->cholesky_products;}
        if(!isfinite(v))return -1;
        if(i==j){if(!(v>0.))return 0;v=sqrt(v);}
        else v/=w->packed[ix(j,j)];
        if(!isfinite(v))return -1;
        w->packed[ix(i,j)]=v;
    }
    return 1;
}

static int finish(ss_result *r,int status,int reason)
{
    r->status=status;r->reason=reason;return status;
}

int ss_propose(const ss_input *in,ss_workspace *w,ss_result *r)
{
    ss_geometry p;int status,selection;
    status=validate(in,w,r);if(status)return status;
    memset(r,0,sizeof(*r));
    if(!geometry(in,&p))
        return finish(r,SS_ERR_NONFINITE,SS_REASON_NONFINITE);
    status=scaled_metric(in,w,r);
    if(status<0)return finish(r,SS_ERR_NONFINITE,SS_REASON_NONFINITE);
    if(!status)return finish(r,SS_ERR_METRIC,SS_REASON_METRIC);
    selection=select_point(in,&p,w,r);
    if(selection<0)return finish(r,SS_ERR_NONFINITE,SS_REASON_NONFINITE);
    if(selection>0 && !diagnostics(in,w,r))
        return finish(r,SS_ERR_NONFINITE,SS_REASON_NONFINITE);
    status=cholesky(w,r);
    if(status<0)return finish(r,SS_ERR_NONFINITE,SS_REASON_NONFINITE);
    if(!status)return finish(r,SS_ERR_METRIC,SS_REASON_METRIC);
    if(!selection)return finish(r,SS_UNRESOLVED,SS_REASON_ROUNDING);
    if(!original_support(in,w->point,&r->min_support_slack,&r->min_step_slack))
        return finish(r,SS_ERR_NONFINITE,SS_REASON_NONFINITE);
    if(r->min_support_slack<0. || r->min_step_slack<0.)
        return finish(r,SS_UNRESOLVED,SS_REASON_ROUNDING);
    if(!(r->original_slope>r->original_slope_allowance) ||
       !(r->tangent_model_decrease>r->tangent_model_allowance) ||
       !(r->diagonal_model_decrease>r->diagonal_model_allowance))
        return finish(r,SS_UNRESOLVED,SS_REASON_NO_DIRECTION);
    return finish(r,SS_OK,SS_REASON_NONE);
}
