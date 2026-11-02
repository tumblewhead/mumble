"""Experimental mixed-degree joint field: RC degree5, independently refined hysteresis.

Public calibration and ordered observations only. No truth or harness imports.
No production estimator changes. All likelihood cross terms are retained.
"""
import ctypes as C
import math
from pathlib import Path
import subprocess
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from experiments.joint_rate_history_001.field import Field,DP,pointer
from experiments.foster_uncertainty_audit_001.conditional_packet import partition,transport as amplitude_transport


def build(directory):
    directory.mkdir(parents=True,exist_ok=False)
    binary=directory/'response.so'
    subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off',
        '-Wall','-Wextra','-Werror','-pedantic','-fPIC','-shared',str(Path(__file__).with_name('response.c')),
        '-lm','-o',str(binary)],check=True)
    return binary


class MixedField(Field):
    def __init__(self,config,center,halfwidth,hdegree,binary,source='fixture'):
        super().__init__(config,center,halfwidth,5,binary,source)
        if not isinstance(hdegree,int) or not 5<=hdegree<=8:raise ValueError('hysteresis degree5..8')
        self.hdegree=hdegree;self.m=hdegree+1
        nodes=np.cos(np.pi*(np.arange(self.m)+.5)/self.m)
        V=chebvander(nodes,hdegree)
        self.pairs=[(i,j) for i in range(self.m) for j in range(self.m) if i+j<=hdegree]
        V2=np.column_stack([np.outer(V[:,i],V[:,j]).ravel() for i,j in self.pairs])
        self.p2=np.ascontiguousarray(np.linalg.pinv(V2));self.b=len(self.pairs)
        hrates=self.center[3:,None]*np.exp(self.halfwidth[3:,None]*nodes)
        self.rates=np.ascontiguousarray(np.r_[self.rates[:3].ravel(),hrates.ravel()])
        self.width=4+6*self.n+2*self.b
        self.root=np.zeros((self.width,self.width))
        self.state=np.zeros(6*self.n+2*self.m*self.m+3)
        self.state[:3*self.n]=1;self.state[6*self.n:6*self.n+self.m*self.m]=1
        self.fn.argtypes=[DP,C.c_size_t,DP,C.c_int,C.c_int,C.c_int,DP,DP,DP,DP,DP]

    def _stage_rows(self,first,observations,source=None):
        if first!=self.count or (source is not None and source!=self.source):raise ValueError('source/order mismatch')
        obs=np.ascontiguousarray(observations,dtype=float)
        if obs.ndim!=2 or obs.shape[1]!=5 or not np.isfinite(obs).all():raise ValueError('observation shape/values')
        rows=np.empty((len(obs),self.width));state=self.state.copy()
        status=self.fn(pointer(obs),len(obs),pointer(self.cal),self.n,self.m,self.b,
            pointer(self.rates),pointer(self.p1),pointer(self.p2),pointer(state),pointer(rows))
        if status or not np.isfinite(rows).all() or not np.isfinite(state).all():raise ValueError('response recurrence failed')
        count=self.count+len(obs)
        noise=self.noise+float(np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi))
        if not math.isfinite(noise):raise ValueError('nonfinite noise normalizer')
        return rows,state,count,noise

    def rows(self,first,observations,source=None):
        # Row-generator API: advances response only, deliberately not the root.
        rows,state,count,noise=self._stage_rows(first,observations,source)
        self.state,self.count,self.noise=state,count,noise
        return rows

    def update(self,first,observations,source=None,return_rows=False):
        rows,state,count,noise=self._stage_rows(first,observations,source)
        root=np.linalg.qr(np.vstack([self.root,rows]),mode='r')
        root*=np.where(np.diag(root)<0,-1.,1.)[:,None]
        if not np.isfinite(root).all():raise ValueError('nonfinite likelihood root')
        # No fallible numerical/allocation work follows the commit. Single owner;
        # asynchronous interruption and concurrent readers require another layer.
        self.root,self.state,self.count,self.noise=root,state,count,noise
        return rows if return_rows else None

    def outgoing(self,chart):
        amplitude,shape=partition(chart);self.features(chart)
        t=np.log(shape/self.center)/self.halfwidth;T=chebvander(t,max(self.n,self.m)-1)
        h=np.array([T[3,i]*T[4,j] for i,j in self.pairs]);n=self.n;m=self.m
        E=self.state[:3*n].reshape(3,n);u=self.state[3*n:6*n].reshape(3,n)
        Eh=self.state[6*n:6*n+m*m];uh=self.state[6*n+m*m:6*n+2*m*m]
        coeff=np.r_[self.state[-3],[T[j,:n]@self.p1@E[j] for j in range(3)],
                    [T[j,:n]@self.p1@u[j] for j in range(3)],h@self.p2@Eh,h@self.p2@uh]
        return amplitude_transport(coeff)@amplitude

    def storage(self):
        return dict(rc_degree=5,hysteresis_degree=self.hdegree,width=self.width,
            packed_joint_root_B=8*self.width*(self.width+1)//2,
            live_collocation_state_B=self.state.nbytes,
            dense_Python_root_B=self.root.nbytes,
            projection_tables_B=self.p1.nbytes+self.p2.nbytes,
            exclusions='Prior, rate tables, tangent carrier, workspace, binding and Python overhead; not complete SRAM')

    def features(self, chart):
        chart=np.asarray(chart,dtype=float)
        if chart.shape!=(16,) or not np.isfinite(chart).all():raise ValueError('finite16D chart required')
        amplitude,shape=partition(chart)
        if not np.isfinite(amplitude).all() or np.any(amplitude[4:10]<=0):raise ValueError('physical amplitude support')
        t=np.log(shape/self.center)/self.halfwidth
        if not np.isfinite(t).all() or np.any(abs(t)>1+1e-12):raise ValueError('outside computational rate box; unresolved, not excluded')
        A,lo,hi=self.state[-3:];z,q,H,B=amplitude[[0,4,9,10]]
        if z-q*hi<0 or z-q*lo>1 or abs(B)>H:raise ValueError('physical trajectory support')
        T=chebvander(t,max(self.n,self.m)-1);h=np.array([T[3,i]*T[4,j] for i,j in self.pairs])
        values=[amplitude[0],amplitude[4],amplitude[5]]
        for j in range(3):
            values.extend(amplitude[1+j]*T[j,:self.n]);values.extend(amplitude[6+j]*T[j,:self.n])
        values.extend(amplitude[9]*h);values.extend(amplitude[10]*h);values.append(1.)
        return np.asarray(values)


def features_jacobian(field,x):
    """Analytic derivative of the existing lifted feature vector, same chart."""
    field.features(x)  # Same support checks; never extrapolate.
    a,s=partition(x);da=np.zeros((11,16));da[:4,:4]=np.eye(4)
    da[4,5]=-a[4]
    for row,col in [(5,6),(6,7),(7,9),(8,11),(9,13)]:da[row,col]=a[row]
    e=np.exp(-2*abs(x[4]));da[10,4]=a[9]*4*e/(1+e)**2;da[10,13]=a[10]
    dt=np.zeros((5,16));gaps=np.exp(x[[8,10,12]])
    for i in range(3):dt[i,[8,10,12][:i+1]]=gaps[:i+1]/s[i]/field.halfwidth[i]
    for i,col in [(3,14),(4,15)]:dt[i,col]=1/field.halfwidth[i];dt[i,5]=-1/field.halfwidth[i]
    t=np.log(s/field.center)/field.halfwidth
    T=np.ones((5,max(field.n,field.m)));D=np.zeros_like(T);T[:,1]=t;D[:,1]=1
    for k in range(2,max(field.n,field.m)):
        T[:,k]=2*t*T[:,k-1]-T[:,k-2]
        D[:,k]=2*T[:,k-1]+2*t*D[:,k-1]-D[:,k-2]
    rows=[da[0],da[4],da[5]]
    for i in range(3):
        for amp in [1+i,6+i]:
            for k in range(field.n):rows.append(T[i,k]*da[amp]+a[amp]*D[i,k]*dt[i])
    for amp in [9,10]:
        for i,j in field.pairs:
            base=T[3,i]*T[4,j]
            grad=D[3,i]*T[4,j]*dt[3]+T[3,i]*D[4,j]*dt[4]
            rows.append(base*da[amp]+a[amp]*grad)
    rows.append(np.zeros(16));return np.array(rows)


def transported(field,x):
    """Analytic joint endpoint transport; static parameter coordinates stay exact."""
    features=field.features(x);J=features_jacobian(field,x)
    W=np.zeros((5,field.width));W[0,0]=1;W[0,1]=-field.state[-3]
    n=field.n;m=field.m;b=field.b;state=field.state
    for i in range(3):
        W[1+i,3+2*i*n:3+(2*i+1)*n]=field.p1@state[i*n:(i+1)*n]
        W[1+i,3+(2*i+1)*n:3+(2*i+2)*n]=field.p1@state[(3+i)*n:(4+i)*n]
    start=3+6*n;hstart=6*n
    W[4,start:start+b]=field.p2@state[hstart+m*m:hstart+2*m*m]
    W[4,start+b:start+2*b]=field.p2@state[hstart:hstart+m*m]
    physical=W@features;D=np.eye(16);D[:5]=W@J
    H=math.exp(x[13]);h=physical[4]/H
    if not -1<h<1 or not 0<=physical[0]<=1:raise ValueError('native field endpoint outside physical chart support')
    D[4]/=H;D[4,13]-=h;D[4]/=(1-h*h)
    end=x.copy();end[:4]=physical[:4];end[4]=np.arctanh(h)
    return end,D


class Compressed:
    def __init__(self,field,mean,root):self.field,self.mean,self.root=field,mean,root;self.calls=0
    def __call__(self,w):
        x=self.mean+self.root@w;r=self.field.residual(x)
        B=self.field.root@features_jacobian(self.field,x)@self.root
        self.calls+=1
        return .5*float(w@w+r@r),w+B.T@r,np.eye(16)+B.T@B,None,None
