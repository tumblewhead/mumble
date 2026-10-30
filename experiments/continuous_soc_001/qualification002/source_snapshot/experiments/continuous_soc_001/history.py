"""Continuous conditional-SOC history for a bounded joint hypothesis family.

This is a deterministic moment approximation, not exact nonlinear marginal
closure. Physical mixtures create variance; translating SOC does not.
"""
import math
from functools import lru_cache
import numpy as np
from experiments.joint_mass_codebook_001 import model as old


def lse(x,axis=None):
    pivot=np.max(x,axis=axis,keepdims=True)
    if np.any(~np.isfinite(pivot)):raise ValueError('empty/nonfinite probability support')
    out=pivot+np.log(np.sum(np.exp(x-pivot),axis=axis,keepdims=True))
    return float(out.ravel()[0]) if axis is None else np.squeeze(out,axis=axis)


@lru_cache(maxsize=32)
def health_kernel(exposure):
    P,tail,_=old.transition(3,exposure)
    logP=np.full_like(P,-np.inf);np.log(P,out=logP,where=P>0)
    P.flags.writeable=False;logP.flags.writeable=False
    return P,logP,tail


class Operator:
    def __init__(self,source,aging_scale=.01):
        self.base=old.Model(17,aging_scale);self.source=source;self.next_index=0;self.elapsed=0.

    def prepare(self,frame,source):
        b=self.base
        if source!=self.source or frame.index!=self.next_index or type(frame.index) is not int:
            raise ValueError('source/order mismatch')
        if (not all(math.isfinite(x) for x in [frame.dt,frame.current,frame.temperature,frame.voltage,frame.sigma]) or
            frame.dt<0 or abs(frame.current)>.25 or not 15<=frame.temperature<=35 or frame.sigma<=0):
            raise ValueError('input domain')
        activity=1+.02*((b.temperature+frame.temperature)/2-25)
        exposure=b.aging_scale*activity*(frame.dt/86400+abs(frame.current)*frame.dt/3600/.06)
        P,logP,tail=health_kernel(exposure)
        f0=1+b.gq*(b.temperature-25);f1=1+b.gq*(frame.temperature-25)
        delta=(f1-f0)/f0;ratio=np.ones(3)
        np.divide(np.log1p(delta),delta,out=ratio,where=delta!=0)
        decrement=frame.current*frame.dt/3600*ratio[None,:]/(b.qbase[:,None]*f0[None,:])
        decay=np.exp(-frame.dt/b.tau)
        v=decay*b.v-np.expm1(-frame.dt/b.tau)*b.Rp*frame.current
        h=b.h.copy()
        if frame.current:
            exposure_h=(b.gp if frame.current>0 else b.gm)*abs(frame.current)*frame.dt/3600
            h=np.exp(-exposure_h)*h-np.expm1(-exposure_h)*np.sign(frame.current)
        nuisance=v.sum(axis=1)+b.H*h
        R=b.rbase[:,None]*(1+b.gr[None,:]*(frame.temperature-25))
        Q=b.qbase[:,None]*(1+b.gq[None,:]*(frame.temperature-25))
        op=dict(source=source,index=frame.index,dt=frame.dt,current=frame.current,temperature=frame.temperature,
                observation=frame.voltage,sigma=frame.sigma,P=P,logP=logP,tail_bound=tail,
                decrement=decrement,Q=Q,R=R,nuisance=nuisance)
        b.v,b.h,b.temperature=v,h,frame.temperature;self.next_index+=1;self.elapsed+=frame.dt
        return op


def encode_log(logw,kind):
    centered=logw-np.max(logw)
    if not np.isfinite(centered).all():raise ValueError('finite supported log masses required')
    if kind=='float64':return centered,None,0.
    if kind=='float32':
        code=centered.astype('<f4')
        if not np.isfinite(code).all():raise ValueError('binary32 log range unresolved')
        decoded=code.astype(float)
    elif kind=='log16':
        delta=512/65534
        amplitude=centered/(2*math.log(2))
        if np.min(amplitude)<-512:raise ValueError('fixed log16 amplitude dynamic range unresolved')
        code=(65535+np.rint(amplitude/delta)).astype('<u2')
        decoded=(code.astype(float)-65535)*(2*math.log(2)*delta)
    else:raise ValueError('unknown codebook')
    return decoded,code.tobytes(),float(np.ptp(centered-decoded))


class History:
    def __init__(self,source,encoding='float64',initial_sd=0.):
        base=old.Model();self.shape=(9,3,3,3,3);self.source=source;self.next_index=0;self.encoding=encoding
        p=base.prior[:,[8,10,12],:,:,:]
        self.logw=np.log(p);self.mean=np.broadcast_to(np.array([.5,.625,.75])[None,:,None,None,None],self.shape).copy()
        self.variance=np.full(self.shape,initial_sd**2)
        self.log_evidence=0.;self.elapsed=0.;self.packet=None;self.local_log_distortion=0.;self.cumulative_weight_log_distortion=0.
        self.inputs=0

    def step(self,op):
        if op['source']!=self.source or op['index']!=self.next_index:raise ValueError('history source/order mismatch')
        # Mix previous health states conditional on the new health, while
        # retaining initial-SOC identity and every static nuisance coordinate.
        joint=self.logw[None,...]+op['logP'].T[:,:,None,None,None,None]
        predicted_logw=lse(joint,axis=1)
        weights=np.exp(joint-predicted_logw[:,None,...])
        mean=np.sum(weights*self.mean[None,...],axis=1)
        variance=np.sum(weights*(self.variance[None,...]+(self.mean[None,...]-mean[:,None,...])**2),axis=1)
        mean=mean-op['decrement'][:,None,:,None,None]
        if np.any((mean<0)|(mean>1)):raise ValueError('continuous conditional SOC center outside physical domain')
        t=np.tanh(8*(mean-.5));U=3+1.15*mean+.08*t;slope=1.15+.64*(1-t*t)
        predicted=U-op['current']*op['R'][:,None,None,:,None]-op['nuisance'][None,None,None,None,:]
        residual=op['observation']-predicted
        innovation=op['sigma']**2+slope*slope*variance
        new_mean=mean+variance*slope/innovation*residual
        new_variance=variance*(op['sigma']**2/innovation)
        if np.any((new_mean<0)|(new_mean>1)) or not np.isfinite(new_variance).all():
            raise ValueError('conditional correction outside physical/numerical domain')
        logL=-.5*(residual*residual/innovation+np.log(2*math.pi*innovation))
        updated=predicted_logw+logL
        increment=lse(updated)-lse(self.logw)
        decoded,packet,distortion=encode_log(updated,self.encoding)
        # Commit atomically. Encoding failure does not advance this history.
        self.logw,self.mean,self.variance=decoded,new_mean,new_variance
        self.packet=packet;self.local_log_distortion=distortion;self.cumulative_weight_log_distortion+=distortion
        self.log_evidence+=increment;self.elapsed+=op['dt'];self.next_index+=1;self.inputs+=1

    def readout(self,op):
        w=np.exp(self.logw-lse(self.logw));Q=op['Q'][:,None,:,None,None];R=op['R'][:,None,None,:,None]
        z=float(np.sum(w*self.mean));q=float(np.sum(w*Q));r=float(np.sum(w*R))
        return dict(Q=q,R=r,SOC=z,Q_sd=math.sqrt(float(np.sum(w*(Q-q)**2))),
                    SOC_sd=math.sqrt(float(np.sum(w*(self.variance+(self.mean-z)**2)))),
                    Q_SOC_covariance=float(np.sum(w*(Q-q)*(self.mean-z))),
                    log_evidence=self.log_evidence,log_weight_span=float(np.ptp(self.logw)),
                    weight_log_distortion=self.local_log_distortion,
                    cumulative_weight_log_distortion=self.cumulative_weight_log_distortion,
                    hypotheses=self.logw.size,source_next_index=self.next_index)

    def bytes(self):
        return dict(live_primary_arrays_B=self.logw.nbytes+self.mean.nbytes+self.variance.nbytes,
                    encoded_weights_B=len(self.packet) if self.packet is not None else self.logw.nbytes,
                    float64_SOC_moments_B=self.mean.nbytes+self.variance.nbytes,
                    packed_payload_with_float64_SOC_B=(len(self.packet) if self.packet is not None else self.logw.nbytes)+self.mean.nbytes+self.variance.nbytes,
                    total_subsystem_B=None)
