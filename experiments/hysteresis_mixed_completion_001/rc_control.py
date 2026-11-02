"""Follow-up diagnostic: increase only RC fidelity; not a target-memory candidate."""
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from .basis import CompletedField


class RC5Control(CompletedField):
    def __init__(self,config,center,binary,completion,source='fixture'):
        if completion not in ('td2','c22','tensor'):raise ValueError('RC control H basis')
        super().__init__(config,center,binary,'c22' if completion=='td2' else completion,source)
        if completion=='td2':
            self.pairs=self.pairs[:-1];self.p2=self.p2[:-1].copy();self.b=len(self.pairs)
        self.completion=completion
        h_rates=self.rates[3*self.n:].copy()
        self.n=6;self.degree=5
        self.nodes=np.cos(np.pi*(np.arange(self.n)+.5)/self.n)
        self.p1=np.ascontiguousarray(np.linalg.inv(chebvander(self.nodes,5)))
        self.rates=np.ascontiguousarray(np.r_[(self.center[:3,None]*np.exp(self.nodes)).ravel(),h_rates])
        self.state=np.zeros(6*self.n+2*self.m*self.m+3)
        self.state[:3*self.n]=1.;self.state[6*self.n:6*self.n+self.m*self.m]=1.
        self.width=4+6*self.n+2*self.b;self.root=np.zeros((self.width,self.width))

    def storage(self):
        value=super().storage();value['rc_degree']=5
        value['scope']='RC fidelity diagnostic only; unchanged H grid, not a 10 KiB candidate'
        return value
