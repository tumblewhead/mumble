#include "../history_translation.h"
#include "../live_layout.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* Host-only independent dense polynomial differentiation. None of these
 * arrays or reference calculations are part of the proposed estimator. */
static unsigned assertions,points,cases;
static long double worst_ratio;
static const unsigned char independent_pairs[20][2]={
    {0,0},{0,7},{0,12},{1,1},{1,8},{1,13},{2,2},{2,9},{2,14},
    {3,3},{3,4},{4,4},{3,10},{3,15},{4,10},{4,15},{10,15},
    {11,11},{5,11},{5,5}
};

#define REQUIRE(x) do { ++assertions; if(!(x)) { \
    fprintf(stderr,"assertion_failed:%u:%s\n",(unsigned)__LINE__,#x); return 0; } } while(0)

static size_t independent_index(unsigned r,unsigned c)
{
    size_t start=0;unsigned k;
    for(k=0;k<r;k++)start+=37u-k;
    return start+c-r;
}

static void reference(const double *R,const long double *x,
                       long double *v,long double *envelope)
{
    unsigned r,k,i,j;
    for(k=0;k<153;k++)v[k]=envelope[k]=0.L;
    for(r=0;r<37;r++) {
        long double p=0.L,pa=0.L,g[16]={0},ga[16]={0},h[136]={0},ha[136]={0};
        for(k=r;k<37;k++) {
            long double a=R[independent_index(r,k)],term;
            if(k<20) {
                unsigned u=independent_pairs[k][0],w=independent_pairs[k][1];
                term=a*x[u]*x[w];p+=term;pa+=fabsl(term);
                g[u]+=a*x[w];ga[u]+=fabsl(a*x[w]);
                g[w]+=a*x[u];ga[w]+=fabsl(a*x[u]);
                i=u>w?u:w;j=u>w?w:u;
                h[i*(i+1u)/2u+j]+=a*(u==w?2.L:1.L);
                ha[i*(i+1u)/2u+j]+=fabsl(a)*(u==w?2.L:1.L);
            } else if(k<36) {
                i=k-20;term=a*x[i];p+=term;pa+=fabsl(term);
                g[i]+=a;ga[i]+=fabsl(a);
            } else { p+=a;pa+=fabsl(a); }
        }
        v[0]+=.5L*p*p;envelope[0]+=.5L*pa*pa;
        for(i=0;i<16;i++) {
            v[1+i]+=p*g[i];envelope[1+i]+=pa*ga[i];
            for(j=0;j<=i;j++) {
                k=i*(i+1u)/2u+j;
                v[17+k]+=g[i]*g[j]+p*h[k];
                envelope[17+k]+=ga[i]*ga[j]+pa*ha[k];
            }
        }
    }
}

static void fixture(double *R)
{
    unsigned r,c;
    for(r=0;r<37;r++)for(c=r;c<37;c++)
        R[independent_index(r,c)]=(double)((int)((r*19u+c*7u)%71u)-35)/64.;
}

static int compare(const double *before,const double *after,const double *shift,
                   unsigned count)
{
    unsigned p,i,k;
    const long double gamma=(16384.L*DBL_EPSILON)/(1.L-16384.L*DBL_EPSILON);
    for(p=0;p<count;p++) {
        long double oldx[16],newx[16],a[153],b[153],aa[153],bb[153];
        for(i=0;i<16;i++) {
            newx[i]=(long double)((int)((p*13u+i*17u)%59u)-29)/32.L;
            oldx[i]=newx[i]+(long double)shift[i];
        }
        reference(before,oldx,a,aa);reference(after,newx,b,bb);++points;
        for(k=0;k<153;k++) {
            long double error=fabsl(a[k]-b[k]),bound=gamma*(aa[k]+bb[k]);
            long double ratio=bound>0.L?error/bound:(error==0.L?0.L:INFINITY);
            if(ratio>worst_ratio)worst_ratio=ratio;
            REQUIRE(error<=bound);
        }
    }
    return 1;
}

static int translation_cases(void)
{
    double R[703],before[703],s[16],t[16],net[16];unsigned i,k;
    fixture(R);memcpy(before,R,sizeof(R));memset(s,0,sizeof(s));
    REQUIRE(ht_translate(R,s)==HT_OK);REQUIRE(memcmp(before,R,sizeof(R))==0);++cases;
    for(k=0;k<3;k++) {
        fixture(R);memcpy(before,R,sizeof(R));
        for(i=0;i<16;i++)s[i]=((double)((int)((i*7u+k*3u)%19u)-9))*(k==0?.031:k==1?.125:.41);
        REQUIRE(ht_translate(R,s)==HT_OK);REQUIRE(compare(before,R,s,32));
    }
    ++cases;
    fixture(R);memcpy(before,R,sizeof(R));
    for(i=0;i<16;i++){s[i]=((int)(i%7u)-3)*.125;t[i]=-s[i];net[i]=0.;}
    REQUIRE(ht_translate(R,s)==HT_OK);REQUIRE(ht_translate(R,t)==HT_OK);
    REQUIRE(compare(before,R,net,24));++cases;
    fixture(R);memcpy(before,R,sizeof(R));
    for(i=0;i<16;i++){s[i]=((int)(i%7u)-3)*.125;t[i]=((int)(i%5u)-2)*.0625;net[i]=s[i]+t[i];}
    REQUIRE(ht_translate(R,s)==HT_OK);REQUIRE(ht_translate(R,t)==HT_OK);
    REQUIRE(compare(before,R,net,24));++cases;
    for(k=0;k<37;k++) {
        memset(R,0,sizeof(R));R[independent_index(0,k)]=2.;memcpy(before,R,sizeof(R));
        for(i=0;i<16;i++)s[i]=((int)(i%5u)-2)*.125;
        REQUIRE(ht_translate(R,s)==HT_OK);REQUIRE(compare(before,R,s,3));
    }
    ++cases;
    return 1;
}

static int rejection_cases(void)
{
    double R[703],before[703],s[16]={0};unsigned i;
    fixture(R);memcpy(before,R,sizeof(R));
    REQUIRE(ht_translate(NULL,s)==HT_ARGUMENT);REQUIRE(ht_translate(R,NULL)==HT_ARGUMENT);
    REQUIRE(ht_translate(R,R+10)==HT_ALIAS);REQUIRE(memcmp(before,R,sizeof(R))==0);++cases;
    s[3]=NAN;REQUIRE(ht_translate(R,s)==HT_NONFINITE);REQUIRE(memcmp(before,R,sizeof(R))==0);
    s[3]=INFINITY;REQUIRE(ht_translate(R,s)==HT_NONFINITE);REQUIRE(memcmp(before,R,sizeof(R))==0);
    s[3]=0.;R[42]=NAN;memcpy(before,R,sizeof(R));
    REQUIRE(ht_translate(R,s)==HT_NONFINITE);REQUIRE(memcmp(before,R,sizeof(R))==0);
    fixture(R);R[0]=DBL_MAX;s[0]=2.;memcpy(before,R,sizeof(R));
    REQUIRE(ht_translate(R,s)==HT_NONFINITE);REQUIRE(memcmp(before,R,sizeof(R))==0);++cases;
    for(i=0;i<20;i++)REQUIRE(memcmp(ht_pair[i],independent_pairs[i],2)==0);
    return 1;
}

static int layout_case(void)
{
    REQUIRE(sizeof(adc12_raw_sample)==16);REQUIRE(sizeof(adc12_calibration)==56);
    REQUIRE(sizeof(lab_query_state)==224);REQUIRE(sizeof(lab_workspace)==1600);
    REQUIRE(sizeof(lab_result)==120);REQUIRE(sizeof(lab_core)==8088);
    REQUIRE(sizeof(lab_input_store)==408);REQUIRE(sizeof(lab_operational_layout)==8680);
    REQUIRE(sizeof(lab_operational_layout)+LAB_OWN_STACK_CAP+LAB_RUNTIME_IRQ_CALLER_CAP==10216);
    REQUIRE(sizeof(lab_operational_layout)+LAB_OWN_STACK_CAP+LAB_RUNTIME_IRQ_CALLER_CAP<=LAB_SRAM_LIMIT);
    REQUIRE(offsetof(lab_workspace,query.state)==1344);
    REQUIRE(offsetof(lab_workspace,query.decoded)==1568);
    REQUIRE(sizeof(((lab_workspace *)0)->merge)==728);
    REQUIRE(sizeof(((lab_workspace *)0)->proposal)==1600);++cases;
    return 1;
}

int main(void)
{
    if(!translation_cases() || !rejection_cases() || !layout_case())return 1;
    printf("{\"schema\":\"live_translation_qualification_v1\",\"passed\":true,"
           "\"cases\":%u,\"assertions\":%u,\"evaluation_points\":%u,"
           "\"worst_error_to_frozen_allowance\":%.17g,"
           "\"sizeof\":{\"raw_sample\":%zu,\"calibration\":%zu,\"query_state\":%zu,"
           "\"workspace\":%zu,\"result\":%zu,\"core\":%zu,\"input_store\":%zu,"
           "\"operational_layout\":%zu,\"planned_complete\":%zu},"
           "\"target_measured\":false,\"integrated_estimator\":false}\n",
           cases,assertions,points,(double)worst_ratio,sizeof(adc12_raw_sample),
           sizeof(adc12_calibration),sizeof(lab_query_state),sizeof(lab_workspace),
           sizeof(lab_result),sizeof(lab_core),sizeof(lab_input_store),
           sizeof(lab_operational_layout),sizeof(lab_operational_layout)+
           LAB_OWN_STACK_CAP+LAB_RUNTIME_IRQ_CALLER_CAP);
    return 0;
}
