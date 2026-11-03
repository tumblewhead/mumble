"""Study-only compact column selection with independently projected RC families."""
import ctypes as C
import math
from pathlib import Path
import subprocess
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from experiments.hysteresis_sensitivity_basis_001.basis import HField
from experiments.hysteresis_refinement_001.field import features_jacobian as legacy_jacobian, transported as legacy_transport
from experiments.joint_rate_history_001.field import pointer
from experiments.foster_uncertainty_audit_001.conditional_packet import partition


def build(directory,forced):
    if forced not in (2,5):raise ValueError('forced kind')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False);binary=directory/'response.so'
    subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-pedantic',
        '-DFORCED_KIND='+str(forced),'-fPIC','-shared',str(Path(__file__).with_name('response.c')),'-lm','-o',str(binary)],check=True)
    return binary


class PartitionField(HField):
    def __init__(self,config,center,rc_binary,h_binary,binary,free_degree,forced_degree=2,source='fixture'):
        if (free_degree,forced_degree) not in [(3,2),(5,2),(5,5)]:raise ValueError('registered degrees')
        super().__init__(config,center,rc_binary,h_binary,'TaylorH2',source)
        lib=C.CDLL(str(Path(binary).resolve()));flag=lib.rc_partition_kind;flag.argtypes=[];flag.restype=C.c_int
        if flag()!=forced_degree:raise ValueError('RC partition/kernel mismatch')
        fn=lib.rc_partition_rows;fn.argtypes=self.fn.argtypes;fn.restype=self.fn.restype;self.lib,self.fn=lib,fn
        self.n=free_degree+1;self.nu=forced_degree+1;self.degree=free_degree
        self.nodes=np.cos(np.pi*(np.arange(self.n)+.5)/self.n);self.anchors=self.nodes.copy()
        self.p1=np.ascontiguousarray(np.linalg.inv(chebvander(self.nodes,free_degree)))
        self.pu=np.zeros((self.n,self.n))
        if forced_degree==2:self.pu[:3,:3]=[[1,0,.25],[0,1,0],[0,0,.25]]
        else:self.pu[:]=self.p1
        self.native_projection=np.ascontiguousarray(np.r_[self.p1.ravel(),self.pu.ravel()])
        self.rates=np.ascontiguousarray(np.r_[(self.center[:3,None]*np.exp(self.nodes)).ravel(),
            np.repeat(self.center[3:],3),self.center[:3]])
        self.full_width=4+6*self.n+2*self.b
        columns=[0,1,2]
        for j in range(3):
            columns.extend(range(3+2*j*self.n,3+(2*j+1)*self.n))
            columns.extend(range(3+(2*j+1)*self.n,3+(2*j+1)*self.n+self.nu))
        columns.extend(range(3+6*self.n,self.full_width))
        self.columns=np.array(columns);self.width=len(columns);self.root=np.zeros((self.width,self.width))
        self.state=np.zeros(6*self.n+21);self.state[:3*self.n]=1.;self.state[6*self.n]=1.
        self.kind='partitioned_free_collocation_forced_'+str(forced_degree)

    def _stage_rows(self,first,observations,source=None):
        if first!=self.count or (source is not None and source!=self.source):raise ValueError('source/order mismatch')
        obs=np.ascontiguousarray(observations,dtype=float)
        if obs.ndim!=2 or obs.shape[1]!=5 or not 1<=len(obs)<=1024 or not np.isfinite(obs).all() or np.any(obs[:,2]!=25.):raise ValueError('bounded stationary input')
        full=np.empty((len(obs),self.full_width));state=self.state.copy()
        status=self.fn(pointer(obs),len(obs),pointer(self.cal),self.n,self.m,self.b,
            pointer(self.rates),pointer(self.native_projection),pointer(self.p2),pointer(state),pointer(full))
        if status or not np.isfinite(full).all() or not np.isfinite(state).all():raise ValueError('response recurrence failed')
        rows=np.ascontiguousarray(full[:,self.columns])
        noise=self.noise+float(np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi))
        if not math.isfinite(noise):raise ValueError('nonfinite normalizer')
        return rows,state,self.count+len(obs),noise

    def features(self,x):return super().features(x)[self.columns]

    def physical_transport_matrix(self):
        W=np.zeros((5,self.width));W[0,0]=1;W[0,1]=-self.state[-3];col=3
        for j in range(3):
            W[1+j,col:col+self.n]=self.p1@self.state[j*self.n:(j+1)*self.n];col+=self.n
            W[1+j,col:col+self.nu]=(self.pu@self.state[(3+j)*self.n:(4+j)*self.n])[:self.nu];col+=self.nu
        start=6*self.n
        W[4,col:col+self.b]=self.p2@self.state[start+9:start+18];col+=self.b
        W[4,col:col+self.b]=self.p2@self.state[start:start+9]
        return W

    def evaluate(self,a,s):
        # Preserve the public physical-amplitude interface; only projection differs.
        W,D,_=super().basis_query(a,s);W,D=W[self.columns],D[self.columns]
        r=self.root@W;J=self.root@D;g=J.T@r;end=np.array(a,copy=True)
        physical=self.physical_transport_matrix()@W;end[:4]=physical[:4];end[10]=physical[4]
        return dict(nll=.5*float(r@r)+self.noise,gradient_amplitude=g[:11],gradient_shape=g[11:],
            precision_amplitude=J[:,:11].T@J[:,:11],end=end)

    def outgoing(self,x):
        a,s=partition(x);return self.evaluate(a,s)['end']

    def storage(self):
        out=super().storage();out.update(free_degree=self.degree,forced_degree=self.nu-1,
            RC_representation=self.kind,RC_anchors_per_branch=self.n,
            native_full_rows_B=1024*self.full_width*8,selected_rows_B=1024*self.width*8,
            response_state_semantics='Free collocation, forced Taylor derivatives or collocation; padded native state counted')
        return out


def features_jacobian(field,x):
    J=legacy_jacobian(field,x)
    return J[field.columns] if isinstance(field,PartitionField) else J


def transported(field,x):
    if not isinstance(field,PartitionField):return legacy_transport(field,x)
    physical=field.physical_transport_matrix()@field.features(x)
    D=np.eye(16);D[:5]=field.physical_transport_matrix()@features_jacobian(field,x)
    H=math.exp(x[13]);h=physical[4]/H
    if not -1<h<1 or not 0<=physical[0]<=1:raise ValueError('field endpoint outside physical support')
    D[4]/=H;D[4,13]-=h;D[4]/=1-h*h
    end=x.copy();end[:4]=physical[:4];end[4]=np.arctanh(h)
    return end,D


class Compressed:
    def __init__(self,field,mean,root):self.field,self.mean,self.root=field,mean,root
    def __call__(self,w):
        x=self.mean+self.root@w;r=self.field.residual(x);B=self.field.root@features_jacobian(self.field,x)@self.root
        return .5*float(w@w+r@r),w+B.T@r,np.eye(16)+B.T@B,None,None
