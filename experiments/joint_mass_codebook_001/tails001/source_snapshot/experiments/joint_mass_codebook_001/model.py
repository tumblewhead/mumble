"""Small explicit joint finite-state aging/thermal comparator, not firmware.

The event model applies an aging boundary kernel, freezes that health value
during the held-current event, and transports SOC. This splitting and the SOC
grid are part of the declared numerical model, not exact continuous aging.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class Frame:
    index: int
    dt: float
    current: float
    temperature: float
    voltage: float
    sigma: float = .04


def ocv(z): return 3+1.15*z+.08*np.tanh(8*(z-.5))


def transition(n, exposure, rates=(.3, .2, .5), terms=48):
    """Monotone pure-birth CTMC by uniformization; explicit remainder bound.

    Missing Poisson tail is assigned to the identity, giving stochastic rows
    and a real-arithmetic TV error at most the stated tail. No mass is discarded.
    The exponential here is event-count probability, not history forgetting.
    """
    if n < 2 or exposure < 0 or not math.isfinite(exposure) or len(rates) != 3 or min(rates) < 0:
        raise ValueError('invalid aging generator')
    size = n*n; gen = np.zeros((size, size))
    for i in range(n):
        for j in range(n):
            old = i*n+j
            for di, dj, rate in [(1, 0, rates[0]), (0, 1, rates[1]), (1, 1, rates[2])]:
                if i+di < n and j+dj < n:
                    gen[old, (i+di)*n+j+dj] += rate
            gen[old, old] = -gen[old].sum()
    rate = float(max(-np.diag(gen)))
    if exposure == 0 or rate == 0: return np.eye(size), 0., gen
    u = rate*exposure
    if u > 2: raise ValueError('uniformization workload outside declared control domain')
    step = np.eye(size)+gen/rate; power = np.eye(size); weight = math.exp(-u)
    out = weight*power
    for k in range(1, terms+1):
        power = power@step; weight *= u/k; out += weight*power
    next_weight = weight*u/(terms+1)
    tail_bound = next_weight/(1-u/(terms+2))
    # Floating summation residual is bookkeeping, not the analytic tail bound.
    residual = 1-out.sum(axis=1)
    if np.max(np.abs(residual)) > 1e-12: raise ValueError('stochastic arithmetic unresolved')
    out[np.diag_indices(size)] += residual
    if np.min(out) < 0: raise ValueError('negative transition probability')
    return out, tail_bound, gen


class Model:
    def __init__(self, soc_nodes=17, aging_scale=0.):
        if soc_nodes not in (17,33,65) or not math.isfinite(aging_scale) or aging_scale < 0:
            raise ValueError('unsupported comparator configuration')
        self.n = 3; self.nz = soc_nodes; self.aging_scale = aging_scale
        self.damage = np.linspace(0, .3, self.n); self.z = np.linspace(0, 1, self.nz)
        self.gq = np.array([-.002, 0., .002]); self.gr = np.array([-.01, 0., .01])
        self.nu = np.array([-1., 0., 1.]); self.shape = (9, self.nz, 3, 3, 3)
        self.temperature = 25.; self.next_index = 0
        self.Rp = (1+.2*self.nu[:,None])*np.array([.04,.08,.12])
        self.tau = (1+.25*self.nu[:,None])*np.array([.05,.5,5.])
        self.H = .015*(1+.2*self.nu)
        self.gp = 100*(1+.2*self.nu); self.gm = 150*(1+.1*self.nu)
        self.v0 = .002*self.nu[:,None]*np.array([1.,-.4,.2]); self.h0 = .2*self.nu
        self.v = self.v0.copy(); self.h = self.h0.copy()
        health = 1+np.eye(3); thermal = 1+.5*np.eye(3)
        zprob = np.zeros(self.nz)
        for z,w in zip([.5,.625,.75],[.25,.5,.25]): zprob[int(z*(self.nz-1))] = w
        p = health.reshape(9,1,1,1,1)*zprob[None,:,None,None,None]*thermal[None,None,:,:,None]*np.array([.25,.5,.25])[None,None,None,None,:]
        self.prior = p/p.sum()
        iq,ir = np.divmod(np.arange(9),3)
        self.qbase = .06*(1-self.damage[iq]); self.rbase = .1*(1+self.damage[ir])
        values = np.broadcast_arrays(self.damage[iq,None,None,None,None], self.damage[ir,None,None,None,None],
                    self.z[None,:,None,None,None], self.nu[None,None,:,None,None],
                    self.nu[None,None,None,:,None], self.nu[None,None,None,None,:])
        self.features = np.stack([a.ravel() for a in values],axis=1)

    def prepare(self, frame):
        if (type(frame.index) is not int or frame.index != self.next_index or
            not all(math.isfinite(x) for x in [frame.dt,frame.current,frame.temperature,frame.voltage,frame.sigma]) or
            frame.dt < 0 or abs(frame.current) > .25 or not 15 <= frame.temperature <= 35 or frame.sigma <= 0):
            raise ValueError('frame source/domain mismatch')
        t0, t1 = self.temperature, frame.temperature
        # Integral of the declared linear thermal activity along measured T(t).
        activity = 1+.02*((t0+t1)/2-25)
        exposure = self.aging_scale*activity*(frame.dt/86400+abs(frame.current)*frame.dt/3600/.06)
        health, tail, generator = transition(self.n, exposure)
        f0 = 1+self.gq*(t0-25); f1 = 1+self.gq*(t1-25)
        delta = (f1-f0)/f0
        ratio = np.ones(3); np.divide(np.log1p(delta), delta, out=ratio, where=delta != 0)
        invQ = ratio[None,:]/(self.qbase[:,None]*f0[None,:])
        target = self.z[None,:,None]-frame.current*frame.dt/3600*invQ[:,None,:]
        valid = (target >= 0)&(target <= 1)
        position = np.where(valid, target*(self.nz-1), 0.)
        lo = np.minimum(np.floor(position).astype(int), self.nz-2)
        upper_weight = position-lo
        decay = np.exp(-frame.dt/self.tau)
        v = decay*self.v-np.expm1(-frame.dt/self.tau)*self.Rp*frame.current
        h = self.h.copy()
        if frame.current != 0:
            gamma = self.gp if frame.current > 0 else self.gm
            exposure_h = gamma*abs(frame.current)*frame.dt/3600
            h = np.exp(-exposure_h)*h-np.expm1(-exposure_h)*np.sign(frame.current)
        nuisance = v.sum(axis=1)+self.H*h
        resistance = self.rbase[:,None]*(1+self.gr[None,:]*(t1-25))
        voltage = ocv(self.z)[None,:,None,None,None]-frame.current*resistance[:,None,None,:,None]-nuisance[None,None,None,None,:]
        voltage = np.broadcast_to(voltage,self.shape).copy()
        log_likelihood = -.5*((voltage-frame.voltage)/frame.sigma)**2-math.log(frame.sigma*math.sqrt(2*math.pi))
        op = dict(health=health, tail_bound=tail, generator=generator, lo=lo, upper_weight=upper_weight,
                  valid=valid, log_likelihood=log_likelihood, voltage=voltage,
                  Q=np.broadcast_to((self.qbase[:,None]*(1+self.gq[None,:]*(t1-25)))[:,None,:,None,None],self.shape),
                  R=np.broadcast_to(resistance[:,None,None,:,None],self.shape),
                  soc=np.broadcast_to(self.z[None,:,None,None,None],self.shape), index=frame.index)
        # Commit only once the entire frame is prepared successfully.
        self.v,self.h,self.temperature,self.next_index = v,h,t1,self.next_index+1
        return op


def predict(p, op):
    h = np.tensordot(op['health'].T,p,axes=(1,0)); out = np.zeros_like(p)
    lost = float(np.sum(h*np.logical_not(op['valid'])[:,:,:,None,None]))
    if lost > 0: raise ValueError('SOC-domain probability unresolved: '+str(lost))
    for j in range(len(h)):
        for a in range(3):
            np.add.at(out[j,:,a],op['lo'][j,:,a],h[j,:,a]*(1-op['upper_weight'][j,:,a,None,None]))
            np.add.at(out[j,:,a],op['lo'][j,:,a]+1,h[j,:,a]*op['upper_weight'][j,:,a,None,None])
    return out


def observe(p, op):
    pivot = float(op['log_likelihood'].max()); L = np.exp(op['log_likelihood']-pivot)
    product = p*L; total = float(product.sum())
    if not total > 0 or np.any((p > 0)&(L > 0)&(product == 0)):
        raise ValueError('likelihood normalization underflow unresolved')
    return product/total, math.log(total)+pivot, 2/total


def moments(p, op):
    return {name:float(np.sum(p*op[name])) for name in ['Q','R','soc']}


def batch_paths(model, operators):
    """Unmerged path sum, no intermediate normalization or posterior reuse.

    Only tiny prefixes are qualified. Every predecessor path is kept separately
    until final bincount; this is an oracle, not a deployable algorithm.
    """
    shape = model.shape; result = np.zeros(shape); evidence = 0.; path_count = 0
    for a in range(3):
        for b in range(3):
            for nu in range(3):
                initial = model.prior[:,:,a,b,nu]
                j,z = np.nonzero(initial); w = initial[j,z].copy()
                for op in operators:
                    jj,zz,ww = [],[],[]
                    for dest in range(9):
                        base = w*op['health'][j,dest]
                        for side in (0,1):
                            weight = op['upper_weight'][dest,z,a]
                            dest_z = op['lo'][dest,z,a]+side
                            new = base*(weight if side else 1-weight)*np.exp(op['log_likelihood'][dest,dest_z,a,b,nu])
                            active = new > 0
                            if np.any(active & ~op['valid'][dest,z,a]): raise ValueError('batch SOC domain')
                            jj.append(np.full(np.count_nonzero(active),dest,dtype=int));zz.append(dest_z[active]);ww.append(new[active])
                    j,z,w = np.concatenate(jj),np.concatenate(zz),np.concatenate(ww)
                path_count += len(w); evidence += float(w.sum())
                result[:,:,a,b,nu] = np.bincount(j*model.nz+z,weights=w,minlength=9*model.nz).reshape(9,model.nz)
    return result/evidence, math.log(evidence), path_count
