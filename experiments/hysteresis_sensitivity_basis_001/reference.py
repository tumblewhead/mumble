"""Independent Python response derivative checks and H6 envelope, offline only."""
from math import comb, exp
import numpy as np


INDICES=[(a,n-a) for n in range(4) for a in range(n+1)]
SLOTS=[(0,0),(1,0),(0,1),(2,0),(1,1),(0,2)]


def jet(observations,rates):
    states=[{a:float(a==(0,0)) for a in INDICES},{a:0. for a in INDICES}]
    history=[]
    for dt,I,*_ in observations:
        if I:
            j=0 if I>0 else 1;s=1 if I>0 else -1
            d=rates[j]*abs(I)*dt/3600;E=exp(-d)
            ed=[E,-d*E,(d*d-d)*E,(-d**3+3*d*d-d)*E]
            for kind in range(2):
                old=states[kind].copy();target=s if kind else 0.
                for a in INDICES:
                    value=E*old[a]
                    for k in range(1,a[j]+1):
                        other=list(a);other[j]-=k;other=tuple(other)
                        value+=comb(a[j],k)*ed[k]*(old[other]-(target if other==(0,0) else 0.))
                    if a==(0,0):value+=(1-E)*target
                    states[kind][a]=value
        history.append([[q[a] for a in INDICES] for q in states])
    return np.array(history)


def constants(order=3):
    C={(0,0):1}
    for n in range(1,order+1):
        for a in [(j,n-j) for j in range(n+1)]:
            terms=[]
            for j in range(2):
                if not a[j]:continue
                total=0
                for k in range(1,a[j]+1):
                    other=list(a);other[j]-=k
                    total+=comb(a[j],k)*C[tuple(other)]
                terms.append(total)
            C[a]=max(terms)
    return C


def envelope(a,shape,center):
    p,m=abs(np.log(np.asarray(shape)[3:]/np.asarray(center)[3:]))
    value=(13*p**3+9*p*p*m+9*p*m*m+13*m**3)/6
    S=abs(a[10])+2*a[9]
    bounds=np.zeros(16);bounds[9]=2*value;bounds[10]=value
    bounds[14]=S*(13*p*p+6*p*m+3*m*m)/2
    bounds[15]=S*(3*p*p+6*p*m+13*m*m)/2
    return bounds,S*value
