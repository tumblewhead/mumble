"""Prior-free centered square-root likelihood; no constrained posterior claim."""
import copy
import math
import numpy as np


def translate_upper(R,old_center,new_center):
    R=np.asarray(R,dtype=float);old=np.asarray(old_center,dtype=float);new=np.asarray(new_center,dtype=float)
    d=len(old)
    if (old.shape!=(d,) or new.shape!=(d,) or R.shape!=(d+1,d+1)
            or not np.isfinite(R).all() or not np.isfinite(old).all() or not np.isfinite(new).all()
            or np.any(np.tril(R,-1)!=0)):
        raise ValueError('invalid centered upper factor')
    out=R.copy();out[:,-1]=R[:,:-1]@(new-old)+R[:,-1]
    if not np.isfinite(out).all():raise ValueError('recenter arithmetic unresolved')
    return out


def qr_upper(rows):
    _,R=np.linalg.qr(rows,mode='reduced')
    return np.where(np.diag(R)<0,-1.,1.)[:,None]*R


class Factor:
    arithmetic_bound=None

    def __init__(self,center,source,basis_id,first=0,entry_time=0.):
        c=np.asarray(center,dtype=float)
        if c.ndim!=1 or not len(c) or not np.isfinite(c).all():raise ValueError('invalid center')
        if not all(type(s) is str and s for s in (source,basis_id)):raise ValueError('missing source/basis identity')
        if type(first) is not int or not 0<=first<2**64 or not math.isfinite(entry_time):raise ValueError('invalid boundary')
        self.center=c.copy();self.R=np.zeros((len(c)+1,len(c)+1))
        self.source=source;self.basis_id=basis_id;self.first=first;self.stop=first
        self.entry_time=float(entry_time);self.exit_time=float(entry_time)
        self.log_normalizer=0.;self.E2=0.;self.recenter_count=0

    def append(self,a,y,sigma,index,time,source,residual_error=0.):
        a=np.asarray(a,dtype=float)
        if (a.shape!=self.center.shape or not np.isfinite(a).all() or not np.isfinite([y,sigma,time,residual_error]).all()
                or sigma<=0 or residual_error<0 or type(index) is not int or index!=self.stop
                or self.stop==2**64-1 or source!=self.source or time<self.exit_time):
            raise ValueError('invalid observation, chronology or ownership')
        row=np.r_[a,a@self.center-y]/sigma
        R=qr_upper(np.vstack((self.R,row)))
        logn=self.log_normalizer+math.log(sigma*math.sqrt(2*math.pi))
        E2=self.E2+(residual_error/sigma)**2
        if not np.isfinite(R).all() or not np.isfinite([logn,E2]).all():raise ValueError('append arithmetic unresolved')
        self.R,self.log_normalizer,self.E2=R,float(logn),float(E2)
        self.stop+=1;self.exit_time=float(time)

    def recenter(self,new_center):
        R=translate_upper(self.R,self.center,new_center)
        self.R,self.center=R,np.array(new_center,dtype=float,copy=True)
        self.recenter_count+=1

    def query(self,theta):
        x=np.asarray(theta,dtype=float)
        if x.shape!=self.center.shape or not np.isfinite(x).all():raise ValueError('invalid query')
        u=np.r_[x-self.center,1.];r=self.R@u
        if not np.isfinite(r).all():raise ValueError('query arithmetic unresolved')
        return dict(nll=float(.5*r@r+self.log_normalizer),gradient=self.R[:,:-1].T@r,
                    residual_defect_bound=float(np.linalg.norm(r)*math.sqrt(self.E2)+.5*self.E2),
                    numerical_bound=None)

    def then(self,other):
        if (type(other) is not Factor or self.source!=other.source or self.basis_id!=other.basis_id
                or self.center.shape!=other.center.shape or self.stop!=other.first or self.exit_time!=other.entry_time):
            raise ValueError('incompatible or overlapping source/basis/boundary')
        Rb=translate_upper(other.R,other.center,self.center)
        out=copy.deepcopy(self);out.R=qr_upper(np.vstack((self.R,Rb)))
        out.log_normalizer+=other.log_normalizer;out.E2+=other.E2
        out.stop=other.stop;out.exit_time=other.exit_time
        out.recenter_count+=other.recenter_count+int(not np.array_equal(self.center,other.center))
        if not np.isfinite(out.R).all() or not np.isfinite([out.log_normalizer,out.E2]).all():raise ValueError('merge arithmetic unresolved')
        return out

    def packet(self,codebook):
        codes=codebook.encode(self.center)
        out=copy.deepcopy(self);out.recenter(codebook.decode(codes))
        return dict(schema='centered-square-root-v1',codebook=dict(lower=codebook.lower,upper=codebook.upper,bits=codebook.bits,version=codebook.version),
                    codes_hex=codes.hex(),R=out.R.tolist(),source=out.source,basis_id=out.basis_id,
                    first=out.first,stop=out.stop,entry_time=out.entry_time,exit_time=out.exit_time,
                    log_normalizer=out.log_normalizer,E2=out.E2,recenter_count=out.recenter_count,
                    arithmetic_bound=None)

    @classmethod
    def restore(cls,packet,codebook,expected_source,expected_basis):
        descriptor=dict(lower=codebook.lower,upper=codebook.upper,bits=codebook.bits,version=codebook.version)
        # JSON may turn tuples into lists; compare the actual numeric descriptor.
        received=packet['codebook']
        if (packet['schema']!='centered-square-root-v1' or packet['source']!=expected_source
                or packet['basis_id']!=expected_basis or received['bits']!=descriptor['bits']
                or received['version']!=descriptor['version'] or tuple(received['lower'])!=descriptor['lower']
                or tuple(received['upper'])!=descriptor['upper'] or packet['arithmetic_bound'] is not None):
            raise ValueError('packet contract mismatch')
        center=codebook.decode(bytes.fromhex(packet['codes_hex']))
        out=cls(center,expected_source,expected_basis,packet['first'],packet['entry_time'])
        out.R=translate_upper(packet['R'],center,center)
        if (type(packet['stop']) is not int or not out.first<=packet['stop']<2**64
                or not np.isfinite([packet['exit_time'],packet['E2'],packet['log_normalizer']]).all()
                or packet['exit_time']<out.entry_time or packet['E2']<0
                or type(packet['recenter_count']) is not int or packet['recenter_count']<0):
            raise ValueError('invalid packet metadata')
        for key in ('stop','exit_time','E2','log_normalizer','recenter_count'):setattr(out,key,packet[key])
        if out.stop==out.first and (np.any(out.R) or out.E2!=0 or out.log_normalizer!=0 or out.exit_time!=out.entry_time):
            raise ValueError('empty interval must contain no evidence')
        return out
