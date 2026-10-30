"""Fixed-domain conditional response bases; diagnostic, not firmware."""
import math
import numpy as np


def cheb(u,degree):
    t=np.ones(degree+1);dt=np.zeros(degree+1)
    if degree:t[1]=u;dt[1]=1
    for k in range(2,degree+1):
        t[k]=2*u*t[k-1]-t[k-2]
        dt[k]=2*t[k-1]+2*u*dt[k-1]-dt[k-2]
    return t,dt


class Basis:
    def __init__(self,family,degree,domain,mean,sd,lower,upper):
        self.family,self.degree,self.domain=family,degree,domain
        self.m=degree+1
        lo=lower.copy();hi=upper.copy()
        if domain=='public_half_SD':lo=np.maximum(lo,mean-.5*sd);hi=np.minimum(hi,mean+.5*sd)
        self.lo=np.r_[lo[:5],lo[11],math.exp(-hi[5])]
        self.hi=np.r_[hi[:5],hi[11],math.exp(-lo[5])]
        self.center=(self.lo+self.hi)/2;self.half=(self.hi-self.lo)/2
        u=np.cos((2*np.arange(self.m)+1)*np.pi/(2*self.m))
        self.grid=np.array([self.inverse(u,j) for j in range(7)])
        v=np.polynomial.chebyshev.chebvander(u,degree)
        self.inv=np.linalg.inv(v)
        self.pairs=[(i,j) for i in range(self.m) for j in range(self.m-i)]
        self.tensor=np.array([[v[a,i]*v[b,j] for i,j in self.pairs]
                              for a in range(self.m) for b in range(self.m)])
        self.project=np.linalg.pinv(self.tensor)
        self.dim=6*self.m+3*len(self.pairs)+1

    def inverse(self,u,j):
        if self.family=='cayley_rational' and j<5:
            return self.center[j]+2*np.arctanh(u*np.tanh(self.half[j]/2))
        return self.center[j]+self.half[j]*u

    def coordinate(self,value,j):
        if self.family=='cayley_rational' and j<5:
            t=np.tanh((value-self.center[j])/2);den=np.tanh(self.half[j]/2)
            return t/den,.5*(1-t*t)/den
        return (value-self.center[j])/self.half[j],1/self.half[j]

    def features(self,x):
        y=np.r_[x[:5],x[11],math.exp(-x[5])]
        if np.any(y<self.lo) or np.any(y>self.hi):return None
        ts=[];ds=[]
        for j in range(7):
            u,d=self.coordinate(y[j],j);t,dt=cheb(u,self.degree);ts.append(t);ds.append(dt*d)
        features=[];jac=[]
        def add(value,entries):
            row=np.zeros(16)
            for index,v in entries:row[index]+=v
            features.append(value);jac.append(row)
        for mode in range(3):
            for amplitude in [7+mode,12+mode]:
                for k in range(self.m):
                    add(x[amplitude]*ts[mode][k],[(amplitude,ts[mode][k]),(mode,x[amplitude]*ds[mode][k])])
        for product in [False,True]:
            amp=x[10]*x[15] if product else x[10]
            for i,j in self.pairs:
                t=ts[3][i]*ts[4][j]
                entries=[(3,amp*ds[3][i]*ts[4][j]),(4,amp*ts[3][i]*ds[4][j]),(10,(x[15] if product else 1)*t)]
                if product:entries.append((15,x[10]*t))
                add(amp*t,entries)
        for i,j in self.pairs:
            add(ts[5][i]*ts[6][j],[(11,ds[5][i]*ts[6][j]),(5,-y[6]*ts[5][i]*ds[6][j])])
        add(x[6],[(6,1.)])
        return np.array(features),np.array(jac)

    def rows(self,observations):
        m=self.m;tau=np.exp(self.grid[:3]);gp=np.exp(self.grid[3])[:,None];gm=np.exp(self.grid[4])[None,:]
        f=np.zeros((3,m));a=np.ones((3,m));hb=np.zeros((m,m));ha=np.ones((m,m))
        charge=0.;design=np.empty((len(observations),self.dim))
        for index,(dt,current,voltage) in enumerate(observations):
            e=np.exp(-dt/tau);om=-np.expm1(-dt/tau);f=e*f+om*current;a=e*a
            if current and dt:
                q=(gp if current>0 else gm)*abs(current)*dt/3600
                e=np.exp(-q);om=-np.expm1(-q);hb=e*hb+om*np.sign(current);ha=e*ha
            charge+=current*dt/3600
            z=self.grid[5][:,None]-charge*self.grid[6][None,:]
            if np.any(z<0) or np.any(z>1):raise ValueError('basis-node SOC domain exceeded')
            ocv=3+1.15*z+.08*np.tanh(8*(z-.5))
            row=[]
            for mode in range(3):
                row.extend(-(self.inv@f[mode]));row.extend(-(self.inv@a[mode]))
            row.extend(-(self.project@hb.ravel()));row.extend(-(self.project@ha.ravel()))
            coeff=self.project@ocv.ravel();coeff[0]-=voltage
            row.extend(coeff);row.append(-current)
            design[index]=np.array(row)/.001
        self.boundary=(f,a,hb,ha,charge)
        return design

    def endpoint(self,x):
        if self.features(x) is None:return None
        f,a,hb,ha,charge=self.boundary;ts=[]
        for j in range(5):ts.append(cheb(self.coordinate(x[j],j)[0],self.degree)[0])
        state=[x[11]-charge/math.exp(x[5])]
        for mode in range(3):
            state.append(x[7+mode]*(ts[mode]@(self.inv@f[mode]))+x[12+mode]*(ts[mode]@(self.inv@a[mode])))
        pair=np.array([ts[3][i]*ts[4][j] for i,j in self.pairs])
        state.append(pair@(self.project@hb.ravel())+x[15]*(pair@(self.project@ha.ravel())))
        return np.array(state)


def independent(observations,points):
    """Direct scalar-model equations vectorized over candidates; no basis fitting."""
    x=np.asarray(points);tau=np.exp(x[:,:3]);f=np.zeros_like(tau);a=np.ones_like(tau)
    hb=np.zeros(len(x));ha=np.ones(len(x));charge=0.;cost=np.zeros(len(x))
    for dt,current,voltage in observations:
        e=np.exp(-dt/tau);om=-np.expm1(-dt/tau);f=e*f+om*current;a=e*a
        if current and dt:
            q=np.exp(x[:,3 if current>0 else 4])*abs(current)*dt/3600
            e=np.exp(-q);om=-np.expm1(-q);hb=e*hb+om*np.sign(current);ha=e*ha
        charge+=current*dt/3600;z=x[:,11]-charge/np.exp(x[:,5]);v=x[:,7:10]*f+x[:,12:15]*a;h=hb+ha*x[:,15]
        mu=3+1.15*z+.08*np.tanh(8*(z-.5))-current*x[:,6]-v.sum(axis=1)-x[:,10]*h
        cost+=.5*((mu-voltage)/.001)**2
    return cost,np.column_stack((z,v,h))
