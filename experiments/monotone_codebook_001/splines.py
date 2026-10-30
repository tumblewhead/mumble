"""Small positive-basis curves and explicit uniform product codebooks."""
from dataclasses import dataclass
import math
import numpy as np


def basis(x, sites, family):
    sites=np.asarray(sites,dtype=float); x=np.atleast_1d(np.asarray(x,dtype=float))
    if (sites.shape!=(4,) or not np.isfinite(sites).all() or np.any(np.diff(sites)<=0)
            or not np.isfinite(x).all() or np.any(x<sites[0]) or np.any(x>sites[-1])):
        raise ValueError('invalid sites or out-of-domain query; no extrapolation')
    if family=='linear':
        i=np.minimum(np.searchsorted(sites,x,side='right')-1,2)
        weight=(x-sites[i])/(sites[i+1]-sites[i])
        out=np.zeros((len(x),4));out[np.arange(len(x)),i]=1-weight
        out[np.arange(len(x)),i+1]=weight
        return out
    if family=='bernstein':
        # Only endpoints set this single segment's domain; four coefficients
        # are control points, not interpolation values at the interior sites.
        u=(x-sites[0])/(sites[-1]-sites[0])
        return np.column_stack(((1-u)**3,3*u*(1-u)**2,3*u*u*(1-u),u**3))
    raise ValueError('unknown basis family')


def monotone(values,direction):
    v=np.asarray(values,dtype=float)
    if v.shape!=(4,) or not np.isfinite(v).all() or direction not in (-1,1):
        raise ValueError('invalid monotone curve')
    if np.any(direction*np.diff(v)<0):
        raise ValueError('coefficient order violates the chosen aging direction')
    return v


def thermal_basis(T,sites,family,reference=25.):
    return (basis(T,sites,family)-basis([reference],sites,family))[:,:3]


def lipschitz(coefficients,sites,family):
    v=np.asarray(coefficients,dtype=float); k=np.asarray(sites,dtype=float)
    basis(k,k,family)
    if v.shape!=(4,) or not np.isfinite(v).all():raise ValueError('invalid coefficients')
    if family=='linear':return float(np.max(abs(np.diff(v))/np.diff(k)))
    return float(3*np.max(abs(np.diff(v)))/(k[-1]-k[0]))


@dataclass(frozen=True)
class Codebook:
    lower: tuple
    upper: tuple
    bits: int
    version: str = 'uniform-product-v1'

    def __post_init__(self):
        lo=np.asarray(self.lower,dtype=float);hi=np.asarray(self.upper,dtype=float)
        if (lo.ndim!=1 or not len(lo) or lo.shape!=hi.shape or not np.isfinite(lo).all()
                or not np.isfinite(hi).all() or np.any(lo>=hi) or type(self.bits) is not int
                or self.bits not in (8,12,16) or self.version!='uniform-product-v1'):
            raise ValueError('invalid codebook descriptor')
        object.__setattr__(self,'lower',tuple(map(float,lo)))
        object.__setattr__(self,'upper',tuple(map(float,hi)))

    @property
    def delta(self):return (np.array(self.upper)-self.lower)/(2**self.bits-1)

    def encode(self,values):
        v=np.asarray(values,dtype=float)
        if (v.shape!=(len(self.lower),) or not np.isfinite(v).all()
                or np.any(v<self.lower) or np.any(v>self.upper)):
            raise ValueError('outside codebook range; no clipping')
        codes=np.rint((v-self.lower)/self.delta).astype(np.uint64)
        if np.any(codes>=2**self.bits):raise ValueError('code overflow')
        packed=sum(int(code)<<(self.bits*i) for i,code in enumerate(codes))
        return packed.to_bytes(math.ceil(len(v)*self.bits/8),'little')

    def decode(self,packet):
        if type(packet) is not bytes or len(packet)!=math.ceil(len(self.lower)*self.bits/8):
            raise ValueError('invalid code length')
        n=int.from_bytes(packet,'little');mask=2**self.bits-1
        if n>>(len(self.lower)*self.bits):raise ValueError('nonzero unused padding bits')
        codes=np.array([(n>>(self.bits*i))&mask for i in range(len(self.lower))],dtype=float)
        return np.array(self.lower)+self.delta*codes

    def encode_monotone(self,values,direction):
        v=monotone(values,direction)
        if len(set(self.lower))!=1 or len(set(self.upper))!=1:
            raise ValueError('monotone proof requires a common ordered grid')
        packet=self.encode(v);monotone(self.decode(packet),direction)
        return packet
