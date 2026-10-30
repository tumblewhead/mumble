#include <math.h>
#include <stddef.h>

/* Desktop diagnostic append kernel. All cross terms retained. Caller owns
 * state, source accounting and buffers; no solver or allocation here.
 * Caller prevalidates finite rows. A nonfinite accumulation is a latched
 * failure, not an atomic rollback or permission to drop an observation. */
int ph_append(double *g,double *b,double *mom,const double *rows,
              const double *charge,size_t n,unsigned m,unsigned k)
{
    size_t r;unsigned i,j;
    if(!g||!b||!mom||!rows||!charge||m<1||m>62||k<1||k>13)return -1;
    for(r=0;r<n;r++) {
        const double *s=rows+r*m,*t=charge+r*(2*k-1);
        size_t q=0;
        for(i=0;i<m;i++) {
            for(j=i;j<m;j++)g[q++]+=s[i]*s[j];
            for(j=0;j<k;j++)b[i*k+j]+=s[i]*t[j];
        }
        for(j=0;j<2*k-1;j++)mom[j]+=t[j];
    }
    for(i=0;i<m*(m+1)/2;i++)if(!isfinite(g[i]))return -2;
    for(i=0;i<m*k;i++)if(!isfinite(b[i]))return -2;
    for(i=0;i<2*k-1;i++)if(!isfinite(mom[i]))return -2;
    return 0;
}
