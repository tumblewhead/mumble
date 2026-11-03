/* Study-only Taylor RC plus collocation (H_KIND=0) or six H derivatives
 * (H_KIND=2). Distinct entry point prevents legacy interpretation of H state.
 * Derivatives are response features, never additional measurement evidence. */
#include <math.h>
#include <stddef.h>
#define RC_KIND 2
#if !defined(H_KIND) || (H_KIND != 0 && H_KIND != 2)
#error Define H_KIND as 0 or 2
#endif
int h_sensitivity_kind(void) { return H_KIND; }
int h_sensitivity_rows(const double *obs, size_t count, const double *cal,
                  int n, int m, int b, const double *rates, const double *p1,
                  const double *p2, double *state, double *rows) {
    if (n!=3) return -3;
#if H_KIND == 2
    if (m!=3 || b!=6) return -3;
#else
    if (!((m==3 && (b==6 || b==7 || b==9)) || (m==8 && b==36))) return -3;
#endif
    const int nn=m*m, width=4+6*n+2*b;
    double *E=state, *u=E+3*n, *Eh=u+3*n, *uh=Eh+nn;
    double *A=uh+nn, *lo=A+1, *hi=lo+1;
    for(size_t k=0;k<count;k++) {
        const double *o=obs+5*k;
        double dt=o[0], I=o[1], T=o[2], sigma=o[4], f[11];
        if(!isfinite(dt)||!isfinite(I)||!isfinite(T)||!isfinite(o[3])||!isfinite(sigma)||
           dt<0||dt>1||fabs(I)>.25||T<15||T>35||sigma<=0) return -1;
        for(int j=0;j<11;j++) f[j]=exp(cal[3+j]*(1/(T+273.15)-1/cal[0]));
        *A+=I*dt/(3600*f[0]); *lo=fmin(*lo,*A); *hi=fmax(*hi,*A);
        for(int j=0;j<3;j++) {
            double drive=f[2+2*j]*I;
#if RC_KIND == 2
            int ix=j*n;
            double dose=dt/(rates[ix]*f[3+2*j]);
            double decay=exp(-dose), one=-expm1(-dose);
            double d1=dose*decay, d2=(dose*dose-dose)*decay;
            double oldF=E[ix], oldF1=E[ix+1], oldU=u[ix], oldU1=u[ix+1];
            E[ix+2]=decay*E[ix+2]+2*d1*oldF1+d2*oldF;
            u[ix+2]=decay*u[ix+2]+2*d1*oldU1+d2*(oldU-drive);
            E[ix+1]=decay*oldF1+d1*oldF;
            u[ix+1]=decay*oldU1+d1*(oldU-drive);
            E[ix]=decay*oldF;
            u[ix]=decay*oldU+one*drive;
#else
            for(int q=0;q<2;q++) {
                int ix=j*n+q;
                double dose=dt/(rates[ix]*f[3+2*j]);
                double decay=exp(-dose), one=-expm1(-dose), d1=dose*decay;
                double oldF=E[ix], oldU=u[ix];
                E[ix+2]=decay*E[ix+2]+d1*oldF;
                u[ix+2]=decay*u[ix+2]+d1*(oldU-drive);
                E[ix]=decay*oldF;
                u[ix]=decay*oldU+one*drive;
            }
#endif
        }
        if(I!=0) {
#if H_KIND == 2
            int j=I>0?1:2, l=I>0?2:1, jj=I>0?3:5;
            double rate=rates[3*n+(I>0?0:m)];
            double dose=rate*f[I>0?9:10]*fabs(I)*dt/(3600*f[0]);
            double decay=exp(-dose), one=-expm1(-dose);
            double e1=-dose*decay, e2=(dose*dose-dose)*decay;
            for(int kind=0;kind<2;kind++) {
                double *v=kind?uh:Eh, old[6];
                double target=kind?(I>0?1:-1):0;
                for(int q=0;q<6;q++) old[q]=v[q];
                for(int q=0;q<6;q++) v[q]=decay*old[q];
                v[0]+=one*target;
                v[j]+=e1*(old[0]-target);
                v[jj]+=2*e1*old[j]+e2*(old[0]-target);
                v[4]+=e1*old[l];
            }
#else
            for(int q=0;q<m;q++) for(int r=0;r<m;r++) {
                int ix=q*m+r; double rate=I>0?rates[3*n+q]:rates[3*n+m+r];
                double dose=rate*f[I>0?9:10]*fabs(I)*dt/(3600*f[0]);
                double decay=exp(-dose), one=-expm1(-dose);
                Eh[ix]*=decay; uh[ix]=decay*uh[ix]+one*(I>0?1:-1);
            }
#endif
        }
        double *row=rows+k*width; int col=0;
        row[col++]=cal[2]/sigma; row[col++]=-cal[2]*(*A)/sigma;
        row[col++]=-I*f[1]/sigma;
        for(int j=0;j<3;j++) for(int kind=0;kind<2;kind++) for(int d=0;d<n;d++) {
            double sum=0; const double *v=(kind?u:E)+j*n;
            for(int q=0;q<n;q++) sum+=p1[d*n+q]*v[q];
            row[col++]=-sum/sigma;
        }
        for(int kind=0;kind<2;kind++) for(int d=0;d<b;d++) {
            double sum=0; const double *v=kind?Eh:uh;
            for(int q=0;q<nn;q++) sum+=p2[d*nn+q]*v[q];
            row[col++]=f[8]*sum/sigma;
        }
        row[col++]=(cal[1]-o[3])/sigma;
        if(col!=width) return -2;
    }
    return 0;
}
