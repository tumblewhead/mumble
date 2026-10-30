"""Separate source-time free-RC carriers with original-coordinate queries."""
import numpy as np


def carriers(t,c,k):
    """Taylor coefficients of exp[-ct(1+z)/(1-z)], not forgetting weights."""
    t=np.asarray(t);x=2*c*t
    b=np.empty(t.shape+(k,));b[...,0]=np.exp(-c*t)
    if k>1:b[...,1]=(1-x)*b[...,0]
    for n in range(1,k-1):b[...,n+1]=((2*n+1-x)*b[...,n]-n*b[...,n-1])/(n+1)
    beta=b.copy()
    if k>1:beta[...,1:]=b[...,1:]-b[...,:-1]
    return beta


class FreeHistory:
    def __init__(self,partition,family,scope,k):
        self.partition=partition;self.basis=partition.basis
        self.family=family;self.modes=[2] if scope=='slowest_only' else [0,1,2];self.k=k
        self.pivots=np.exp(-(self.basis.lo[:3]+self.basis.hi[:3])/2)
        self.rho=np.tanh((self.basis.hi[:3]-self.basis.lo[:3])/4)
        self.old_slices={mode:slice((2*mode+1)*self.basis.m,(2*mode+2)*self.basis.m) for mode in self.modes}
        removed={i for s in self.old_slices.values() for i in range(s.start,s.stop)}
        self.old_dim=partition.m+partition.k
        self.keep=np.array([i for i in range(self.old_dim) if i not in removed])
        self.dim=len(self.keep)+len(self.modes)*k
        roots=np.cos((2*np.arange(k)+1)*np.pi/(2*k))
        self.log_nodes={i:(self.basis.lo[i]+self.basis.hi[i])/2+(self.basis.hi[i]-self.basis.lo[i])*roots/2 for i in self.modes}
        self.inverse=np.linalg.inv(np.polynomial.chebyshev.chebvander(roots,k-1))

    def rows(self,old_design,elapsed):
        blocks=[]
        for mode in self.modes:
            if self.family=='time_kernel':block=carriers(elapsed,self.pivots[mode],self.k)
            else:
                values=np.exp(-elapsed[:,None]/np.exp(self.log_nodes[mode])[None,:])
                block=values@self.inverse.T
            blocks.append(-block/.001)
        return np.ascontiguousarray(np.column_stack((old_design[:,self.keep],*blocks)))

    def query(self,x):
        old=self.partition.query(x)
        if old is None:return None
        features=[old[0][self.keep]];jac=[old[1][self.keep]]
        for mode in self.modes:
            if self.family=='time_kernel':
                rate=np.exp(-x[mode]);c=self.pivots[mode];z=(rate-c)/(rate+c)
                dz=-2*rate*c/(rate+c)**2
                powers=z**np.arange(self.k);derivative=np.zeros(self.k)
                if self.k>1:derivative[1:]=np.arange(1,self.k)*z**np.arange(self.k-1)*dz
            else:
                center=(self.basis.lo[mode]+self.basis.hi[mode])/2;half=(self.basis.hi[mode]-self.basis.lo[mode])/2
                u=(x[mode]-center)/half;powers=np.polynomial.chebyshev.chebvander(u,self.k-1).ravel()
                derivative=np.zeros(self.k)
                for j in range(1,self.k):
                    coefficients=np.zeros(j+1);coefficients[j]=1
                    derivative[j]=np.polynomial.chebyshev.chebval(u,np.polynomial.chebyshev.chebder(coefficients))/half
            amplitude=12+mode;row=np.zeros((self.k,16))
            row[:,amplitude]=powers;row[:,mode]=x[amplitude]*derivative
            features.append(x[amplitude]*powers);jac.append(row)
        return np.concatenate(features),np.vstack(jac)

    def replace_components(self,base_parts,design,queries):
        result=base_parts.copy();first=len(self.keep)
        for mode in self.modes:
            block=slice(first,first+self.k)
            result[:,:,2*mode+1]=queries[:,block]@design[:,block].T
            first+=self.k
        return result

    def endpoint(self,x,elapsed):
        result=self.basis.endpoint(x)
        if result is None:return None
        f,a,_,_,_=self.basis.boundary
        for mode in self.modes:
            u=self.basis.coordinate(x[mode],mode)[0]
            values=np.polynomial.chebyshev.chebvander(u,4).ravel()
            forced=x[7+mode]*(values@(self.basis.inv@f[mode]))
            result[mode+1]=forced+x[12+mode]*np.exp(-elapsed/np.exp(x[mode]))
        return result

    def memory(self):
        base=self.partition.memory();k=self.k;f=self.dim
        factor=8*f*(f+1)//2;extra_scratch=8*(4*k+16)
        scratch=base['extra_query_scratch_B']+24*(f-self.old_dim)+extra_scratch
        total=factor+base['boundary_B']+base['new_bank_metadata_estimate_domains_B']+32+base['inherited_nonbank_reservations_B']+scratch
        return dict(features=f,QR_numeric_B=factor,boundary_B=base['boundary_B'],
            metadata_estimate_domains_B=base['new_bank_metadata_estimate_domains_B'],elapsed_pivot_reserve_B=32,
            inherited_nonbank_reservations_B=base['inherited_nonbank_reservations_B'],query_scratch_B=scratch,
            QR_planned_subsystem_B=total,retained_kernel_tail_bound=[float(self.rho[i]**k/(1-self.rho[i])) for i in self.modes],
            selected_modes=self.modes,pivots_per_s=self.pivots[self.modes].tolist(),rho=self.rho[self.modes].tolist(),
            bound_applies_to_family='time_kernel_only',target_measured=False,integrated_workspace_qualified=False)
