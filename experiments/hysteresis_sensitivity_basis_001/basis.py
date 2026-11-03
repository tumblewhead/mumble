"""Study-only matched Taylor RC with collocation or derivative H response."""
import ctypes as C
from pathlib import Path
import subprocess
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from experiments.rc_sensitivity_basis_001.basis import SensitivityField


def build(directory, mode):
    if mode not in ('collocation', 'derivative'):
        raise ValueError('H kernel mode')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    binary=directory/'response.so'
    subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off',
                    '-Wall','-Wextra','-Werror','-pedantic',
                    '-DH_KIND='+('2' if mode=='derivative' else '0'),'-fPIC','-shared',
                    str(Path(__file__).with_name('response.c')),'-lm','-o',str(binary)],check=True)
    return binary


class HField(SensitivityField):
    def __init__(self,config,center,rc_binary,h_binary,kind,source='fixture'):
        if kind not in ('H2','c22','tensor','TaylorH2','H7'):
            raise ValueError('H representation')
        # Legacy RC binding initializes its reviewed state/feature layout only.
        super().__init__(config,center,rc_binary,'taylor2',source)
        lib=C.CDLL(str(h_binary));flag=getattr(lib,'h_sensitivity_kind',None)
        if flag is None:raise ValueError('H kernel mode missing')
        flag.argtypes=[];flag.restype=C.c_int
        if flag()!=(2 if kind=='TaylorH2' else 0):raise ValueError('H representation/kernel mismatch')
        fn=lib.h_sensitivity_rows;fn.argtypes=self.fn.argtypes;fn.restype=self.fn.restype
        self.lib,self.fn=lib,fn
        self.hkind=kind;self.hdegree=7 if kind=='H7' else 2;self.m=self.hdegree+1
        nodes=np.cos(np.pi*(np.arange(self.m)+.5)/self.m)
        self.pairs=[(i,j) for i in range(self.m) for j in range(self.m) if i+j<=self.hdegree]
        V=chebvander(nodes,self.hdegree)
        if kind=='c22':self.pairs += [(2,2)]
        if kind=='tensor':self.pairs=[(i,j) for i in range(3) for j in range(3)]
        if kind in ('c22','tensor'):
            inverse=np.linalg.inv(V);full=np.kron(inverse,inverse)
            self.p2=np.ascontiguousarray(full[[3*i+j for i,j in self.pairs]])
        elif kind=='TaylorH2':
            # State slots [f00,f10,f01,f20,f11,f02,0,0,0].
            self.p2=np.zeros((6,9));self.p2[0,[0,3,5]]=[1,.25,.25]
            self.p2[1,2]=1;self.p2[2,5]=.25;self.p2[3,1]=1
            self.p2[4,4]=1;self.p2[5,3]=.25
            nodes=np.zeros(3)
        else:
            V2=np.column_stack([np.outer(V[:,i],V[:,j]).ravel() for i,j in self.pairs])
            self.p2=np.ascontiguousarray(np.linalg.pinv(V2))
        self.b=len(self.pairs);self.width=4+6*self.n+2*self.b
        self.rates=np.ascontiguousarray(np.r_[self.rates[:3*self.n],
            (self.center[3:,None]*np.exp(nodes)).ravel()])
        self.state=np.zeros(6*self.n+2*self.m*self.m+3)
        for j in range(3):self.state[j*self.n]=1.
        if kind=='TaylorH2':self.state[6*self.n]=1.
        else:self.state[6*self.n:6*self.n+self.m*self.m]=1.
        self.root=np.zeros((self.width,self.width))

    def storage(self):
        out=super().storage();out['H_representation']=self.hkind
        out['H_derivative_padding_slots']=6 if self.hkind=='TaylorH2' else 0
        out['response_state_semantics']='Taylor RC plus '+self.hkind+' H; derivatives are features, not evidence'
        return out
