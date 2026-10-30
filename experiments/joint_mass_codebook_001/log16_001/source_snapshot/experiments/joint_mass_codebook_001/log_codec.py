"""Fixed logarithmic relative-amplitude lattice: controlled density ratios.

This is a geometric probability encoding, not exponential aging/forgetting.
Original support zeros stay zero; out-of-domain ratios explicitly reject.
"""
from dataclasses import dataclass
import math
import numpy as np
from .codecs import distribution, distances, pack, unpack


def oscillation(p,q):
    p,q=distribution(p),distribution(q)
    if not np.array_equal(p>0,q>0):raise ValueError('strong ratio metric needs common support')
    active=p>0
    log_ratio=np.log(p[active])-np.log(q[active])
    return float(np.ptp(log_ratio))


@dataclass(frozen=True)
class LogSphereCodebook:
    size:int
    bits:int=12
    span:float=512.

    def __post_init__(self):
        if type(self.size) is not int or self.size<1 or self.bits not in (8,12) or self.span!=512.:
            raise ValueError('unqualified log-codebook descriptor')

    @property
    def delta(self):return self.span/((1<<self.bits)-2)

    def encode(self,p):
        p=distribution(p)
        if len(p)!=self.size:raise ValueError('shape mismatch')
        active=p>0
        log_amplitude=.5*(np.log2(p[active])-math.log2(float(p.max())))
        if np.any(log_amplitude< -self.span):raise ValueError('amplitude dynamic range unresolved')
        maximum=(1<<self.bits)-1
        codes=np.zeros(self.size,dtype=np.uint64)
        codes[active]=(maximum+np.rint(log_amplitude/self.delta)).astype(np.uint64)
        if np.any(codes[active]<1) or codes.max()!=maximum:raise ValueError('log-code invariant')
        return pack(codes,self.bits)

    def decode(self,raw):
        codes=unpack(raw,self.bits,self.size);active=codes>0
        if not np.any(active) or codes.max()!=(1<<self.bits)-1:raise ValueError('noncanonical log codeword')
        q=np.zeros(self.size);q[active]=np.exp2(2*self.delta*(codes[active]-((1<<self.bits)-1)))
        q/=q.sum()
        if np.any(q[active]==0):raise ValueError('decoded tail underflow unresolved')
        return q

    def encode_checked(self,p):
        raw=self.encode(p);q=self.decode(raw);error=distances(p,q)
        error['log_oscillation']=oscillation(p,q)
        error['a_priori_log_oscillation_bound']=2*math.log(2)*self.delta
        error['a_priori_TV_bound']=math.tanh(error['a_priori_log_oscillation_bound']/4)
        return raw,q,error
