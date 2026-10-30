"""Geometric probability codecs with explicit dictionary and distortion costs."""
from dataclasses import dataclass
import math
import numpy as np
from experiments.monotone_codebook_001.splines import Codebook


def distribution(p):
    p = np.asarray(p,dtype=float)
    if p.ndim != 1 or not len(p) or not np.isfinite(p).all() or np.any(p < 0) or abs(float(p.sum())-1) > 1e-10:
        raise ValueError('normalized finite probability vector required')
    return p


def distances(p, q):
    p,q = distribution(p),distribution(q)
    if p.shape != q.shape: raise ValueError('probability shape mismatch')
    affinity = float(np.sqrt(p)@np.sqrt(q))
    # Norm formulation retains tiny Hellinger distances better than 1-affinity.
    chord = float(np.linalg.norm(np.sqrt(p)-np.sqrt(q)))
    return dict(TV=.5*float(np.abs(p-q).sum()), Hellinger=chord/math.sqrt(2),
                chord=chord, affinity=affinity,
                spherical_TV_bound=chord*math.sqrt(max(0.,1-chord*chord/4)))


def pack(codes,bits):
    value = 0
    for i,x in enumerate(codes): value |= int(x)<<(i*bits)
    return value.to_bytes((len(codes)*bits+7)//8,'little')


def unpack(raw,bits,size):
    if type(raw) is not bytes or len(raw) != (size*bits+7)//8: raise ValueError('packet size')
    value = int.from_bytes(raw,'little')
    if value>>(bits*size): raise ValueError('nonzero padding')
    mask = (1<<bits)-1
    return np.array([(value>>(i*bits))&mask for i in range(size)],dtype=float)


@dataclass(frozen=True)
class SphereCodebook:
    size: int
    bits: int

    def __post_init__(self):
        if type(self.size) is not int or self.size < 1 or self.bits not in (8,12): raise ValueError('codec descriptor')

    def encode(self,p):
        p = distribution(p)
        if len(p) != self.size: raise ValueError('codec shape')
        code = np.ceil(((1<<self.bits)-1)*np.sqrt(p)).astype(np.uint64)
        raw = pack(code,self.bits)
        return raw

    def decode(self,raw):
        codes = unpack(raw,self.bits,self.size)
        energy = float(codes@codes)
        if energy == 0: raise ValueError('empty probability codeword')
        return codes*codes/energy

    def encode_checked(self,p):
        raw = self.encode(p); q = self.decode(raw)
        error = distances(p,q)
        error['a_priori_TV_bound'] = min(1.,2*math.sqrt(np.count_nonzero(p))/((1<<self.bits)-1))
        if not np.array_equal(np.asarray(p)>0,q>0): raise ValueError('support changed')
        return raw,q,error


def moments_shape(p,features):
    p = distribution(p); mu = p@features; centered = features-mu
    cov = (centered.T*p)@centered
    np.linalg.cholesky(cov)  # No covariance jitter or truth-guided repair.
    return dict(mean=mu.tolist(), precision=np.linalg.inv(cov).tolist())


class ShapeDictionary:
    """Frozen joint Gaussian geometry templates plus an exact support bitmap.

    A uniform template always exists. Templates approximate shape, not just a
    centroid. The caller must account for distortion at every use.
    """
    def __init__(self,features,shapes):
        self.features = np.asarray(features,dtype=float)
        self.shapes = shapes
        if len(shapes) > 254: raise ValueError('one-byte dictionary index overflow')
        self.logs = [np.zeros(len(features))]
        for shape in shapes:
            d = self.features-np.asarray(shape['mean'])
            self.logs.append(-.5*np.einsum('ij,jk,ik->i',d,np.asarray(shape['precision']),d))
        dim = self.features.shape[1]
        self.packed_parameter_bytes = len(shapes)*8*(dim+dim*(dim+1)//2)

    def decode(self,raw):
        size = len(self.features)
        if type(raw) is not bytes or len(raw) != 1+(size+7)//8 or raw[0] >= len(self.logs): raise ValueError('shape packet')
        packed_mask = int.from_bytes(raw[1:],'little')
        if packed_mask>>size: raise ValueError('shape padding')
        mask = np.unpackbits(np.frombuffer(raw[1:],dtype=np.uint8),bitorder='little')[:size].astype(bool)
        if not np.any(mask): raise ValueError('empty support')
        out = np.zeros(size); logits = self.logs[raw[0]][mask]; out[mask] = np.exp(logits-logits.max())
        if np.any(out[mask] == 0): raise ValueError('template tail underflow unresolved')
        return out/out.sum()

    def encode_checked(self,p):
        p = distribution(p); mask = np.packbits(p>0,bitorder='little').tobytes()
        best = None
        for index in range(len(self.logs)):
            raw = bytes([index])+mask
            try: q = self.decode(raw)
            except ValueError: continue
            error = distances(p,q)
            if best is None or error['Hellinger'] < best[2]['Hellinger']: best = raw,q,error
        if best is None: raise ValueError('no applicable codeword')
        return best


def bivariate_mass(a,b,rho,order=160):
    if not (-4<=a<=4 and -4<=b<=4 and abs(rho)<=.9): raise ValueError('support geometry outside control domain')
    nodes,weights = np.polynomial.legendre.leggauss(order)
    x = -12+(a+12)*.5*(nodes+1)
    cdf = np.array([.5*math.erfc(-(b-rho*v)/math.sqrt(2*(1-rho*rho))) for v in x])
    return float((a+12)*.5*(weights@(np.exp(-x*x/2)/math.sqrt(2*math.pi)*cdf)))


def geometry_code(a,b,rho,bits):
    cb = Codebook((-4.,-4.,-.9),(4.,4.,.9),bits)
    raw = cb.encode([a,b,rho]); aq,bq,rq = cb.decode(raw)
    # Bound coordinate displacement first at fixed rho, then the Gaussian-law
    # change at fixed decoded thresholds. Numerical evaluation is not outward rounded.
    kl = .5*(2*rq*(rq-rho)/(1-rq*rq)+math.log1p((rho*rho-rq*rq)/(1-rho*rho)))
    if kl < -1e-14: raise ValueError('Gaussian KL arithmetic unresolved')
    bound = min(1.,(abs(a-aq)+abs(b-bq))/math.sqrt(2*math.pi)+math.sqrt(max(0.,kl)/2))
    mass = bivariate_mass(a,b,rho); decoded_mass = bivariate_mass(aq,bq,rq)
    return dict(bits=bits, payload_B=len(raw), original=[a,b,rho], decoded=[float(aq),float(bq),float(rq)],
                mass=mass, decoded_mass=decoded_mass, absolute_error=abs(mass-decoded_mass),
                real_arithmetic_bound=bound, quadrature_omitted_tail_upper=.5*math.erfc(12/math.sqrt(2)),
                numerical_bound_certified=False, log_mass_error=abs(math.log(mass)-math.log(decoded_mass)))
