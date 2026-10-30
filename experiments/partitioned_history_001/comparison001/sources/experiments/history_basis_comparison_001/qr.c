#include <stddef.h>
#include <math.h>

/* Diagnostic generic packed square-root append. No dimension truncation,
 * normal equations, observation reweighting or diagonal repair. Host runner
 * owns rows/workspace; this is not a complete M23 implementation. */
int hb_qr_append(double *upper, const double *rows, size_t count, unsigned dim)
{
    double row[76];size_t k;unsigned i,j;
    if(!upper || (!rows && count) || dim<1 || dim>76)return -1;
    for(k=0;k<count;k++) {
        for(i=0;i<dim;i++) {
            row[i]=rows[k*dim+i];if(!isfinite(row[i]))return -2;
        }
        for(i=0;i<dim;i++) {
            size_t start=(size_t)i*dim-(size_t)i*(i-1)/2;
            double a=upper[start],b=row[i],r=hypot(a,b),c,s;
            if(!isfinite(r))return -2;
            if(r==0)continue;
            c=a/r;s=b/r;upper[start]=r;
            for(j=i+1;j<dim;j++) {
                double u=upper[start+j-i],v=row[j];
                upper[start+j-i]=c*u+s*v;row[j]=-s*u+c*v;
                if(!isfinite(upper[start+j-i]) || !isfinite(row[j]))return -2;
            }
        }
    }
    return 0;
}
