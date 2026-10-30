"""Exact product packing and PSD-bounded rank storage, desktop diagnostics."""
import numpy as np


def envelopes(bank,lower,upper):
    """Public support only; not empirical norms or fitted parameter values."""
    bound=np.maximum(abs(lower),abs(upper));p=bank.partition
    w=np.r_[np.full(15,bound[10]),np.full(15,bound[10]*bound[15]),bound[6],1.,
        np.sum(abs(p.inverse),axis=1)*4.23/.001]
    for mode in range(3):
        for amp in [7+mode,12+mode]:w=np.r_[w,bound[amp]*bank.rho[mode]**np.arange(bank.k)]
    if np.any(w<=0) or not np.all(np.isfinite(w)):raise ValueError('nonpositive or nonfinite feature envelope')
    return w


class ProductPacked:
    """Retain mixed blocks and the self-block moments needed by cost and GN."""
    def __init__(self,design,bank,charges):
        self.bank=bank;self.f=design.shape[1];self.k=bank.k;g=design.T@design
        mask=np.triu(np.ones((self.f,self.f),dtype=bool));self.moments=[]
        k=self.k;nn,mm=np.indices((k,k));s=(nn+mm).ravel()
        def pack(block,weights):return np.bincount(s,weights=(block*weights).ravel(),minlength=2*k-1)
        for mode in range(3):
            first=len(bank.keep)+2*mode*k;ff=g[first:first+k,first:first+k];aa=g[first+k:first+2*k,first+k:first+2*k]
            fa=g[first:first+k,first+k:first+2*k]
            self.moments.append(np.array([pack(ff,1),pack(ff,nn*mm),pack(aa,1),pack(aa,nn*mm),pack(fa,1),pack(fa,nn),pack(fa,nn*mm)]))
            mask[first:first+2*k,first:first+2*k]=False
        self.ocv_start=len(bank.keep)-bank.partition.k
        sl=slice(self.ocv_start,len(bank.keep));mask[sl,sl]=False
        self.i,self.j=np.nonzero(mask);self.values=g[self.i,self.j]
        self.charge_moments=np.sum(bank.partition.charge_rows(charges),axis=0)
        self.numeric_bytes=self.values.nbytes+self.charge_moments.nbytes+sum(m.nbytes for m in self.moments)

    def metrics(self,x,query,gn=False):
        phi,jac=query;i=self.i;j=self.j;weight=self.values*np.where(i==j,.5,1.)
        cost=np.sum(weight*phi[i]*phi[j]);gradient=np.sum(weight[:,None]*(phi[i,None]*jac[j]+phi[j,None]*jac[i]),axis=0)
        metric=jac[i].T@(weight[:,None]*jac[j])+jac[j].T@(weight[:,None]*jac[i]) if gn else None
        start=self.ocv_start;size=self.bank.partition.k;ii,jj=np.indices((size,size))
        ocv=(self.charge_moments[ii+jj]+self.charge_moments[abs(ii-jj)])/2
        v=phi[start:start+size];q=jac[start:start+size]
        cost+=.5*v@ocv@v;gradient+=q.T@ocv@v
        if gn:metric+=q.T@ocv@q
        for mode,m in enumerate(self.moments):
            rate=np.exp(-x[mode]);c=self.bank.pivots[mode];z=(rate-c)/(rate+c);dz=-2*c*rate/(rate+c)**2
            s=np.arange(2*self.k-1)
            ev=lambda coeff,shift=0:np.polynomial.polynomial.polyval(z,coeff[shift:])
            ff,ffnm,aa,aanm,fa,fan,fanm=m
            ff0=ev(ff);aa0=ev(aa);fa0=ev(fa)
            ff1=ev(s*ff/2,1);aa1=ev(s*aa/2,1);fan1=ev(fan,1);fam1=ev(s*fa-fan,1)
            ff2=ev(ffnm,2);aa2=ev(aanm,2);fa2=ev(fanm,2)
            u=x[7+mode];v=x[12+mode]
            cost+=.5*(u*u*ff0+2*u*v*fa0+v*v*aa0)
            local_g=np.array([u*ff0+v*fa0,u*fa0+v*aa0,u*u*ff1+u*v*(fan1+fam1)+v*v*aa1])
            transform=np.zeros((3,16));transform[0,7+mode]=1;transform[1,12+mode]=1;transform[2,mode]=dz
            gradient+=transform.T@local_g
            if gn:
                local_m=np.array([[ff0,fa0,u*ff1+v*fam1],[fa0,aa0,u*fan1+v*aa1],
                    [u*ff1+v*fam1,u*fan1+v*aa1,u*u*ff2+2*u*v*fa2+v*v*aa2]])
                metric+=transform.T@local_m@transform
        return float(cost),gradient,metric


class RankHistory:
    """Fixed rank plus a bound on discarded PSD information; no forgetting."""
    def __init__(self,rank,features,signature,start=0):
        self.rank=rank;self.features=features;self.signature=signature;self.start=start;self.stop=start
        self.factor=np.empty((0,features));self.delta=0.;self.svd_calls=0

    def reduce(self,rows):
        if len(rows)<=self.rank:self.factor=np.array(rows,copy=True);return
        _,s,vt=np.linalg.svd(rows,full_matrices=False);self.svd_calls+=1
        self.factor=s[:self.rank,None]*vt[:self.rank]
        if len(s)>self.rank:self.delta+=float(s[self.rank]**2)

    def append(self,row,index):
        if index!=self.stop:raise ValueError('noncontiguous or repeated source')
        if not np.all(np.isfinite(row)):raise ValueError('nonfinite source row')
        self.reduce(np.vstack((self.factor,row)));self.stop+=1

    def merge(self,other):
        if (self.signature,self.rank,self.features)!=(other.signature,other.rank,other.features):raise ValueError('incompatible domain/configuration')
        if self.stop!=other.start:raise ValueError('overlapping or nonadjacent sources')
        result=RankHistory(self.rank,self.features,self.signature,self.start)
        result.stop=other.stop;result.delta=self.delta+other.delta
        result.reduce(np.vstack((self.factor,other.factor)))
        return result

    def metrics(self,psi,jac,gn=False):
        residual=self.factor@psi;projected=self.factor@jac
        return float(residual@residual/2),projected.T@residual,projected.T@projected if gn else None

    def cost_width(self,psi):return float(self.delta*(psi@psi)/2)

    def gradient_width(self,psi,jac):return self.delta*np.linalg.norm(psi)*np.linalg.norm(jac,axis=0)


def rank_memory(bank,rank):
    base=bank.memory();f=bank.dim;common=base['QR_planned_subsystem_B']-base['QR_numeric_B']
    payload=8*(rank*f+1)
    # Nonaliasing lower ledger for current NumPy/SVD update; library workspace unknown.
    explicit_update=8*((rank+1)*f+(rank+1)*f+(rank+1)**2+(rank+1))
    return dict(factor_and_remainder_B=payload,inherited_complete_nonfactor_B=common,
        retained_and_query_plan_B=common+payload,explicit_append_SVD_arrays_B=explicit_update,
        subsystem_plus_explicit_update_lower_B=common+payload+explicit_update,
        numerical_library_workspace_B=None,merged_update_workspace_qualified=False,
        target_measured=False,complete_deployment_qualified=False)
