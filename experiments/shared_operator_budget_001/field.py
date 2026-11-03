"""Fixed-width shared Cayley query; inherited native streaming is unchanged."""
import math
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from experiments.hysteresis_sensitivity_basis_001.basis import HField
from experiments.foster_uncertainty_audit_001.conditional_packet import partition


class SharedField(HField):
    def __init__(self,config,center,rc_binary,h_binary,source='fixture'):
        super().__init__(config,center,rc_binary,h_binary,'TaylorH2',source)
        self.kind='shared_cayley2'

    def basis_query(self,a,s):
        # Delegate all original physical/path/rate checks before transforming RC queries.
        super().basis_query(a,s)
        a=np.asarray(a,dtype=float);t=np.log(np.asarray(s)/self.center)
        w=np.tanh(t[:3]/2);chain=np.ones(5);chain[:3]=1-w*w;t[:3]=2*w
        T=chebvander(t,2);D=np.column_stack((np.zeros(5),np.ones(5),4*t))
        W=[];JW=[]
        def add(amp,value,dshape):
            W.append(a[amp]*value);row=np.zeros(16);row[amp]=value;row[11:]=a[amp]*dshape;JW.append(row)
        for amp in (0,4,5):add(amp,1.,np.zeros(5))
        for j in range(3):
            for amp in (1+j,6+j):
                for k in range(3):
                    ds=np.zeros(5);ds[j]=D[j,k]*chain[j];add(amp,T[j,k],ds)
        for amp in (9,10):
            for i,j in self.pairs:
                ds=np.zeros(5);ds[3]=D[3,i]*T[4,j];ds[4]=T[3,i]*D[4,j]
                add(amp,T[3,i]*T[4,j],ds)
        W.append(1.);JW.append(np.zeros(16))
        return np.array(W),np.array(JW),T

    def storage(self):
        out=super().storage();out['RC_representation']='shared_cayley_query_on_exact_central_jets'
        out['query_chain']='s=2*tanh(log(tau/tauc)/2), ds/dlogtau=sech^2(log(tau/tauc)/2)'
        out['new_native_recurrence_or_numeric_state_bytes']=0
        return out


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
    if isinstance(field,SharedField):
        w=np.tanh(t[:3]/2);dt[:3]*=(1-w*w)[:,None];t[:3]=2*w
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
    def __init__(self,field,mean,root):self.field,self.mean,self.root=field,mean,root
    def __call__(self,w):
        x=self.mean+self.root@w;r=self.field.residual(x);B=self.field.root@features_jacobian(self.field,x)@self.root
        return .5*float(w@w+r@r),w+B.T@r,np.eye(16)+B.T@B,None,None
