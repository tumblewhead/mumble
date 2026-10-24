/* Independent higher-precision diagnosis of frozen remainder-audit failures.
 * Fixed 3RC smooth model, chronological actual intervals and analytic anchor
 * sensitivities. This does not call the estimator, evidence or remainder core.
 * Original double inputs are converted exactly to long double before candidate
 * parameter addition. All model arithmetic and libm calls below use long
 * double. No optimization, truth, interval validation or bound alteration.
 */
#include <ctype.h>
#include <errno.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NT 7
#define NA 9
#define DIM 16
#define MAX_CANDIDATES 32

typedef struct {
    long double tau[3],gamma[2],Q,z0,charge,elapsed;
    long double f[3],a[3],df[3],da[3],hb,ha,dhb[2],dha[2];
} model;
typedef struct {
    long double ocv,X[NA],jac[NT];
} row;
typedef struct {
    model state;
    long double theta[NT],alpha[NA],delta[DIM],physical_theta_delta[NT];
    long double error_norm,error_max,affine_cost,nonlinear_cost,cost_difference;
} candidate;

static model anchor;
static long double anchor_theta[NT],anchor_alpha[NA],scales[DIM],sigma;
static candidate candidates[MAX_CANDIDATES];
static row anchor_row,candidate_row;
static unsigned candidate_count;
static char csv_line[4096];

static void number(long double value)
{
    if(isfinite(value))printf("%.*Lg",DECIMAL_DIG,value);else fputs("null",stdout);
}
static void array(const long double *v,int n)
{
    int i;putchar('[');for(i=0;i<n;i++){if(i)putchar(',');number(v[i]);}putchar(']');
}
static const char *space(const char *s)
{
    while(isspace((unsigned char)*s))s++;
    return s;
}
static int integer(const char *s,uint64_t *out)
{
    char *end;unsigned long long n;s=space(s);
    if(!*s||*s=='-')return -1;
    errno=0;n=strtoull(s,&end,10);
    if(errno||end==s||*space(end)||n>UINT64_MAX)return -1;
    *out=(uint64_t)n;return 0;
}
static int init(model *s,const long double *t)
{
    int i;memset(s,0,sizeof(*s));
    for(i=0;i<NT;i++)if(!isfinite(t[i]))return -1;
    for(i=0;i<3;i++){s->tau[i]=expl(t[i]);s->a[i]=1.;}
    s->gamma[0]=expl(t[3]);s->gamma[1]=expl(t[4]);
    s->z0=t[5];s->Q=expl(t[6]);s->ha=1.;
    if(s->z0<0||s->z0>1||!isfinite(s->Q)||s->Q<=0)return -1;
    for(i=0;i<3;i++)if(!isfinite(s->tau[i])||s->tau[i]<=0)return -1;
    for(i=0;i<2;i++)if(!isfinite(s->gamma[i])||s->gamma[i]<=0)return -1;
    return 0;
}
static int step(model *s,long double dt,long double current,const long double *alpha,row *r,int derivative)
{
    long double z,t,uprime,q,e,one_minus,oldf,olda,oldb,d,sign;
    int i,j,k;
    if(dt<0||!isfinite(dt)||!isfinite(current))return -1;
    s->charge+=current*dt/3600.L;s->elapsed+=dt;z=s->z0-s->charge/s->Q;
    if(z<0||z>1||!isfinite(z))return -1;
    /* Lift the original C binary64 OCV literals too, so the independent
     * precision diagnostic changes arithmetic, not model coefficients. */
    t=tanhl(8.L*(z-.5L));r->ocv=3.L+(long double)1.15*z+(long double).08*t;
    uprime=(long double)1.15+(long double).64*(1.L-t*t);r->X[0]=-current;
    for(i=0;i<3;i++) {
        q=dt/s->tau[i];e=expl(-q);one_minus=-expm1l(-q);
        oldf=s->f[i];olda=s->a[i];s->f[i]=e*oldf+one_minus*current;s->a[i]=e*olda;
        if(derivative) {
            d=q*e;s->df[i]=e*s->df[i]+d*(oldf-current);s->da[i]=e*s->da[i]+d*olda;
            r->jac[i]=-s->df[i]*alpha[1+i]-s->da[i]*alpha[5+i];
        }
        r->X[1+i]=-s->f[i];r->X[5+i]=-s->a[i];
    }
    if(current!=0&&dt!=0) {
        k=current>0?0:1;sign=current>0?1.L:-1.L;
        q=s->gamma[k]*fabsl(current)*dt/3600.L;e=expl(-q);one_minus=-expm1l(-q);
        oldb=s->hb;olda=s->ha;s->hb=e*oldb+one_minus*sign;s->ha=e*olda;
        if(derivative)for(j=0;j<2;j++) {
            d=j==k?-q*e:0;
            s->dhb[j]=e*s->dhb[j]+d*(oldb-sign);s->dha[j]=e*s->dha[j]+d*olda;
        }
    }
    r->X[4]=-s->hb;r->X[8]=-s->ha;
    if(derivative) {
        r->jac[3]=-s->dhb[0]*alpha[4]-s->dha[0]*alpha[8];
        r->jac[4]=-s->dhb[1]*alpha[4]-s->dha[1]*alpha[8];
        r->jac[5]=uprime;r->jac[6]=uprime*s->charge/s->Q;
    }
    return 0;
}
static int read_double(FILE *f,long double *value)
{
    double original;
    if(fscanf(f,"%lf",&original)!=1||!isfinite(original))return -1;
    *value=(long double)original;return 0;
}
static int read_config(const char *path)
{
    FILE *f=fopen(path,"r");int modes,i,j,ch,rc=-1;
    if(!f)return -1;
    if(fscanf(f,"%d",&modes)!=1||modes!=3||read_double(f,&sigma)||sigma<=0)goto done;
    for(i=0;i<NT;i++)if(read_double(f,&anchor_theta[i]))goto done;
    for(i=0;i<NA;i++)if(read_double(f,&anchor_alpha[i]))goto done;
    for(i=0;i<DIM;i++)if(read_double(f,&scales[i])||scales[i]<=0)goto done;
    if(fscanf(f,"%u",&candidate_count)!=1||!candidate_count||candidate_count>MAX_CANDIDATES)goto done;
    if(init(&anchor,anchor_theta))goto done;
    for(j=0;j<(int)candidate_count;j++) {
        candidate *c=&candidates[j];
        for(i=0;i<DIM;i++)if(read_double(f,&c->delta[i]))goto done;
        for(i=0;i<NT;i++) {
            c->physical_theta_delta[i]=scales[i]*c->delta[i];
            c->theta[i]=anchor_theta[i]+c->physical_theta_delta[i];
        }
        for(i=0;i<NA;i++)c->alpha[i]=anchor_alpha[i]+scales[NT+i]*c->delta[NT+i];
        if(init(&c->state,c->theta))goto done;
    }
    do{ch=fgetc(f);}while(ch!=EOF&&isspace((unsigned char)ch));
    if(ch!=EOF||ferror(f))goto done;
    rc=0;
done:
    if(fclose(f)&&rc==0)rc=-1;
    return rc;
}
static int read_sample(FILE *f,uint64_t expected,long double *dt,long double *current,long double *voltage)
{
    const char *p;char *end;unsigned long long index;double values[3];int i;
    if(!fgets(csv_line,sizeof(csv_line),f))return -1;
    if(!strchr(csv_line,'\n')&&!feof(f))return -1;
    p=space(csv_line);if(!*p||*p=='-')return -1;
    errno=0;index=strtoull(p,&end,10);
    if(errno||end==p||index>UINT64_MAX||(uint64_t)index!=expected)return -1;
    p=space(end);if(*p++!=',')return -1;
    for(i=0;i<3;i++) {
        errno=0;values[i]=strtod(p,&end);if(errno||end==p||!isfinite(values[i]))return -1;
        p=space(end);if(i<2){if(*p++!=',')return -1;}else if(*p)return -1;
    }
    if(values[0]<0)return -1;
    *dt=(long double)values[0];*current=(long double)values[1];*voltage=(long double)values[2];return 0;
}
int main(int argc,char **argv)
{
    FILE *f;uint64_t count,index;int i,j;size_t length;
    if(argc!=4||integer(argv[3],&count)||!count) {
        fprintf(stderr,"Usage: %s DATA.csv INPUT.txt END_SAMPLES\n",argv[0]);return 2;
    }
    if(read_config(argv[2])){fprintf(stderr,"Invalid audit input\n");return 2;}
    f=fopen(argv[1],"r");if(!f){fprintf(stderr,"Cannot open data\n");return 2;}
    if(!fgets(csv_line,sizeof(csv_line),f)){fclose(f);return 2;}
    length=strlen(csv_line);while(length&&(csv_line[length-1]=='\n'||csv_line[length-1]=='\r'))csv_line[--length]=0;
    if(strcmp(csv_line,"sample_index,dt_s,current_A,voltage_V")){fclose(f);return 2;}
    for(index=0;index<count;index++) {
        long double dt,current,voltage;
        if(read_sample(f,index,&dt,&current,&voltage)||step(&anchor,dt,current,anchor_alpha,&anchor_row,1))goto failed;
        for(j=0;j<(int)candidate_count;j++) {
            candidate *c=&candidates[j];long double ma=anchor_row.ocv,mn,ra,rn,error;
            if(step(&c->state,dt,current,c->alpha,&candidate_row,0))goto failed;
            mn=candidate_row.ocv;
            for(i=0;i<NA;i++){ma+=anchor_row.X[i]*c->alpha[i];mn+=candidate_row.X[i]*c->alpha[i];}
            for(i=0;i<NT;i++)ma+=anchor_row.jac[i]*c->physical_theta_delta[i];
            ra=(ma-voltage)/sigma;rn=(mn-voltage)/sigma;error=(mn-ma)/sigma;
            c->error_norm=hypotl(c->error_norm,error);c->error_max=fmaxl(c->error_max,fabsl(mn-ma));
            c->affine_cost+=.5L*ra*ra;c->nonlinear_cost+=.5L*rn*rn;
            c->cost_difference+=.5L*error*(rn+ra);
        }
    }
    if(fclose(f))return 1;
    printf("{\"schema\":\"mumble_remainder_precision_probe_v1\",\"samples\":%" PRIu64 ",\"candidate_count\":%u,\"LDBL_MANT_DIG\":%d,\"DBL_MANT_DIG\":%d,\"FLT_RADIX\":%d,\"long_double_bytes\":%zu,\"LDBL_EPSILON\":",
           count,candidate_count,LDBL_MANT_DIG,DBL_MANT_DIG,FLT_RADIX,sizeof(long double));number(LDBL_EPSILON);
    fputs(",\"arithmetic_validated\":false,\"truth_used\":false,\"new_nonlinear_fits\":0,\"input_semantics\":\"original_double_values_converted_exactly_before_long_double_parameter_addition_and_model_arithmetic\",\"charge_Ah\":",stdout);number(anchor.charge);
    fputs(",\"elapsed_s\":",stdout);number(anchor.elapsed);
    fputs(",\"candidates\":[",stdout);
    for(j=0;j<(int)candidate_count;j++) {
        candidate *c=&candidates[j];if(j)putchar(',');
        printf("{\"candidate_index\":%d,\"delta_scaled\":",j);array(c->delta,DIM);
        fputs(",\"actual_whitened_remainder_norm\":",stdout);number(c->error_norm);
        fputs(",\"prediction_remainder_rms_V\":",stdout);number(c->error_norm*sigma/sqrtl((long double)count));
        fputs(",\"prediction_remainder_max_V\":",stdout);number(c->error_max);
        fputs(",\"affine_NLL\":",stdout);number(c->affine_cost);
        fputs(",\"nonlinear_NLL\":",stdout);number(c->nonlinear_cost);
        fputs(",\"nonlinear_minus_affine_NLL\":",stdout);number(c->cost_difference);putchar('}');
    }
    fputs("]}\n",stdout);return 0;
failed:
    fprintf(stderr,"Audit model/input failure at sample %" PRIu64 "\n",index);fclose(f);return 1;
}
