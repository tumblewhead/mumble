"""Unmerged continuous-SOC path oracle for small prefixes only."""
import math
import numpy as np
from experiments.joint_mass_codebook_001.model import ocv
from .history import History,lse


class Paths:
    def __init__(self,source):
        h=History(source,initial_sd=0.)
        idx=np.indices(h.shape).reshape(5,-1)
        self.j,self.initial,self.gq,self.gr,self.nu=idx
        self.z=h.mean.ravel().copy();self.logw=h.logw.ravel().copy()
        self.next_index=0;self.source=source;self.log_evidence=0.

    def step(self,op):
        if op['index']!=self.next_index or op['source']!=self.source:raise ValueError('oracle source/order')
        data=[[] for _ in range(7)]
        for dest in range(9):
            valid=op['P'][self.j,dest]>0
            if not np.any(valid):continue
            z=self.z[valid]-op['decrement'][dest,self.gq[valid]]
            if np.any((z<0)|(z>1)):raise ValueError('oracle physical SOC domain')
            volts=ocv(z)-op['current']*op['R'][dest,self.gr[valid]]-op['nuisance'][self.nu[valid]]
            ll=-.5*((volts-op['observation'])/op['sigma'])**2-math.log(op['sigma']*math.sqrt(2*math.pi))
            logw=self.logw[valid]+op['logP'][self.j[valid],dest]+ll
            values=[np.full(len(z),dest,dtype=int),self.initial[valid],self.gq[valid],self.gr[valid],self.nu[valid],z,logw]
            for bucket,value in zip(data,values):bucket.append(value)
        self.j,self.initial,self.gq,self.gr,self.nu,self.z,updated=[np.concatenate(x) for x in data]
        self.log_evidence+=lse(updated)-lse(self.logw)
        self.logw=updated-np.max(updated);self.next_index+=1

    def readout(self,op):
        w=np.exp(self.logw-lse(self.logw));Q=op['Q'][self.j,self.gq];R=op['R'][self.j,self.gr]
        z=float(w@self.z);q=float(w@Q);r=float(w@R)
        return dict(Q=q,R=r,SOC=z,Q_sd=math.sqrt(float(w@(Q-q)**2)),SOC_sd=math.sqrt(float(w@(self.z-z)**2)),
                    log_evidence=self.log_evidence,paths=len(w))
