"""Study-only RC projections using value/sensitivity states and one joint factor."""
import ctypes as C
from pathlib import Path
import subprocess
import numpy as np
from numpy.polynomial.chebyshev import chebvander,chebder,chebval
from experiments.response_basis_attribution_001.basis import BasisField


def build(directory,kind):
    if kind not in ('taylor2','hermite3'):raise ValueError('sensitivity kernel kind')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    binary=directory/'response.so';mode=2 if kind=='taylor2' else 3
    subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off',
                    '-Wall','-Wextra','-Werror','-pedantic',f'-DRC_KIND={mode}',
                    '-fPIC','-shared',str(Path(__file__).with_name('response.c')),
                    '-lm','-o',str(binary)],check=True)
    return binary


class SensitivityField(BasisField):
    def __init__(self,config,center,binary,kind,source='fixture'):
        if kind not in ('taylor2','hermite3','chebyshev3'):raise ValueError('RC basis kind')
        super().__init__(config,center,binary,2,'log',source)
        self.kind=kind
        flag=getattr(self.lib,'rc_response_kind',None)
        if kind=='chebyshev3':
            if flag is not None:raise ValueError('ordinary RC control requires a value-only kernel')
        else:
            if flag is None:raise ValueError('sensitivity kernel mode symbol missing')
            flag.argtypes=[];flag.restype=C.c_int
            if flag()!=(2 if kind=='taylor2' else 3):raise ValueError('kernel/representation mismatch')
        h_rates=self.rates[3*self.n:].copy()
        if kind=='taylor2':
            self.n=3;self.nodes=np.zeros(3);self.anchors=np.array([0.])
            self.p1=np.ascontiguousarray([[1.,0.,.25],[0.,1.,0.],[0.,0.,.25]])
        elif kind=='hermite3':
            self.n=4;self.anchors=np.array([-1.,1.])/np.sqrt(2)
            self.nodes=np.r_[self.anchors,self.anchors]
            V=chebvander(self.anchors,3)
            D=np.column_stack([chebval(self.anchors,chebder(np.eye(4)[j])) for j in range(4)])
            self.p1=np.ascontiguousarray(np.linalg.inv(np.vstack((V,D))))
        else:
            self.n=4;self.nodes=np.cos(np.pi*(np.arange(4)+.5)/4);self.anchors=self.nodes.copy()
            self.p1=np.ascontiguousarray(np.linalg.inv(chebvander(self.nodes,3)))
        self.degree=self.n-1
        self.rates=np.ascontiguousarray(np.r_[(self.center[:3,None]*np.exp(self.nodes)).ravel(),h_rates])
        self.state=np.zeros(6*self.n+2*self.m*self.m+3)
        for j in range(3):
            size=1 if kind=='taylor2' else 2 if kind=='hermite3' else self.n
            self.state[j*self.n:j*self.n+size]=1.
        self.state[6*self.n:6*self.n+self.m*self.m]=1.
        self.width=4+6*self.n+2*self.b;self.root=np.zeros((self.width,self.width))

    def storage(self):
        result=super().storage();result['rc_degree']=self.n-1;result['RC_representation']=self.kind
        result['RC_anchors_per_branch']=len(self.anchors)
        result['response_state_semantics']='Value/derivative slots for sensitivity candidates; H unchanged'
        return result
