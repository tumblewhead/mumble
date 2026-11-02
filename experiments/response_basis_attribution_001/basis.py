"""Stationary mixed response-basis study; unchanged native recurrence and joint QR."""
import ctypes as C
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from experiments.joint_rate_history_001.field import Field,DP
from experiments.hysteresis_refinement_001.field import MixedField
from experiments.foster_uncertainty_audit_001.conditional_packet import transport, partition


class BasisField(MixedField):
    def __init__(self,config,center,binary,hdegree=2,hcoordinate='log',source='fixture'):
        if hdegree not in (2,3) or hcoordinate not in ('log','rate'):raise ValueError('study basis')
        if config['reference_temperature_K']!=298.15:raise ValueError('stationary reference temperature')
        Field.__init__(self,config,center,1.,2,binary,source)
        self.hdegree=hdegree;self.m=hdegree+1;self.hcoordinate=hcoordinate
        nodes=np.cos(np.pi*(np.arange(self.m)+.5)/self.m);V=chebvander(nodes,hdegree)
        self.pairs=[(i,j) for i in range(self.m) for j in range(self.m) if i+j<=hdegree]
        V2=np.column_stack([np.outer(V[:,i],V[:,j]).ravel() for i,j in self.pairs])
        self.p2=np.ascontiguousarray(np.linalg.pinv(V2));self.b=len(self.pairs)
        hrates=self.center[3:,None]*(np.exp(nodes) if hcoordinate=='log' else np.cosh(1)+np.sinh(1)*nodes)
        self.rates=np.ascontiguousarray(np.r_[self.rates[:3].ravel(),hrates.ravel()])
        self.width=4+6*self.n+2*self.b;self.root=np.zeros((self.width,self.width))
        self.state=np.zeros(6*self.n+2*self.m*self.m+3);self.state[:3*self.n]=1;self.state[6*self.n:6*self.n+self.m*self.m]=1
        self.fn.argtypes=[DP,C.c_size_t,DP,C.c_int,C.c_int,C.c_int,DP,DP,DP,DP,DP]

    def _stage_rows(self,first,observations,source=None):
        obs=np.asarray(observations)
        if obs.ndim!=2 or obs.shape[1]!=5 or not 1<=len(obs)<=1024 or np.any(obs[:,2]!=25.):raise ValueError('bounded stationary input')
        return super()._stage_rows(first,obs,source)

    def basis_query(self,a,s):
        a=np.asarray(a,dtype=float);s=np.asarray(s,dtype=float)
        if a.shape!=(11,) or s.shape!=(5,) or not np.isfinite(a).all() or not np.isfinite(s).all() or np.any(s<=0):raise ValueError('query shape/finite')
        t=np.log(s/self.center)
        if np.any(abs(t)>1+1e-12):raise ValueError('outside computational rate box; unresolved, not excluded')
        A,lo,hi=self.state[-3:]
        if min(a[4:10])<=0 or abs(a[10])>a[9] or a[0]-a[4]*hi<0 or a[0]-a[4]*lo>1:raise ValueError('physical path unsupported')
        chain=np.ones(5)
        if self.hcoordinate=='rate':
            t[3:]=(s[3:]/self.center[3:]-np.cosh(1))/np.sinh(1);chain[3:]=s[3:]/self.center[3:]/np.sinh(1)
        maxdegree=max(self.n,self.m)-1;T=chebvander(t,maxdegree);D=np.zeros_like(T);D[:,1]=1
        for k in range(2,maxdegree+1):D[:,k]=2*T[:,k-1]+2*t*D[:,k-1]-D[:,k-2]
        W=[];JW=[]
        def add(amp,value,dshape):
            W.append(a[amp]*value);row=np.zeros(16);row[amp]=value;row[11:]=a[amp]*dshape;JW.append(row)
        for amp in (0,4,5):add(amp,1.,np.zeros(5))
        for j in range(3):
            for amp in (1+j,6+j):
                for k in range(self.n):
                    ds=np.zeros(5);ds[j]=D[j,k];add(amp,T[j,k],ds)
        for amp in (9,10):
            for i,j in self.pairs:
                ds=np.zeros(5);ds[3]=D[3,i]*T[4,j]*chain[3];ds[4]=T[3,i]*D[4,j]*chain[4]
                add(amp,T[3,i]*T[4,j],ds)
        W.append(1.);JW.append(np.zeros(16))
        return np.array(W),np.array(JW),T

    def features(self,chart):
        # Keep inherited residual/nll consistent with this field's coordinate map.
        a,s=partition(np.asarray(chart,dtype=float))
        return self.basis_query(a,s)[0]

    def outgoing(self,chart):
        a,s=partition(np.asarray(chart,dtype=float))
        return self.evaluate(a,s)['end']

    def evaluate(self,a,s):
        W,D,T=self.basis_query(a,s);r=self.root@W;J=self.root@D;g=J.T@r
        n=self.n;m=self.m;E=self.state[:3*n].reshape(3,n);u=self.state[3*n:6*n].reshape(3,n)
        h=np.array([T[3,i]*T[4,j] for i,j in self.pairs]);hs=self.state[6*n:6*n+2*m*m].reshape(2,m*m)
        coeff=np.r_[self.state[-3],[T[j,:n]@self.p1@E[j] for j in range(3)],[T[j,:n]@self.p1@u[j] for j in range(3)],[h@self.p2@v for v in hs]]
        return dict(nll=.5*float(r@r)+self.noise,gradient_amplitude=g[:11],gradient_shape=g[11:],precision_amplitude=J[:,:11].T@J[:,:11],end=transport(coeff)@a)

    def storage(self):
        arrays={k:v.nbytes for k,v in vars(self).items() if isinstance(v,np.ndarray)};packed=8*self.width*(self.width+1)//2
        return dict(rc_degree=2,hysteresis_degree=self.hdegree,hysteresis_coordinate=self.hcoordinate,lifted_width=self.width,
            packed_factor_B=packed,live_response_B=self.state.nbytes,numeric_factor_response_domain_scalars_B=packed+self.state.nbytes+96,
            retained_numpy_arrays_B=sum(arrays.values()),array_breakdown_B=arrays,
            input_chunk_B=1024*5*8,response_rows_B=1024*self.width*8,stacked_QR_input_B=(1024+self.width)*self.width*8,
            old_dense_root_B=self.root.nbytes,new_dense_root_B=self.root.nbytes,trial_state_B=self.state.nbytes,
            query_root_product_J_B=self.width*16*8,
            exclusions='Packed subtotal excludes calibration/rate/projection tables, metadata, prior, solver and all scratch/stack/ISR; actual NumPy arrays exclude Python/library allocations. Listed scratch categories overlap lifetimes; no full MCU memory or timing claim.')
