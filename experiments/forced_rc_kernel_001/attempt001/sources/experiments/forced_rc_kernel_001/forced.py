"""Physical forced/free RC representation with retained parameter uncertainty."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'free_rc_kernel_001'))
from kernel import FreeHistory,carriers


def forced_coefficients(observations,c,k,initial=None):
    """Piecewise constant input; f is voltage per unit resistance (amperes)."""
    f=np.zeros(k) if initial is None else np.array(initial,copy=True)
    result=np.empty((len(observations),k))
    for j,(dt,current,*_) in enumerate(observations):
        beta=carriers(dt,c,k)
        drive=-beta;drive[0]=-np.expm1(-c*dt)
        f=np.convolve(beta,f)[:k]+current*drive
        result[j]=f
    return result


def compose(first,second):
    """Chronological affine block composition, second after first."""
    a1,f1=first;a2,f2=second;k=len(a1)
    return np.convolve(a2,a1)[:k],np.convolve(a2,f1)[:k]+f2


class JointRC(FreeHistory):
    def __init__(self,partition,family,k):
        super().__init__(partition,family,'all_three',k)
        self.keep=np.arange(6*self.basis.m,self.old_dim)
        self.dim=len(self.keep)+6*k

    def rows(self,old_design,observations):
        elapsed=np.cumsum(observations[:,0]);blocks=[];self.forced_end=[]
        for mode in self.modes:
            if self.family=='time_kernel':
                forced=forced_coefficients(observations,self.pivots[mode],self.k)
                free=carriers(elapsed,self.pivots[mode],self.k)
            else:
                tau=np.exp(self.log_nodes[mode]);f=np.zeros(self.k);samples=[]
                for dt,current,_ in observations:
                    f=np.exp(-dt/tau)*f-current*np.expm1(-dt/tau);samples.append(f.copy())
                forced=np.asarray(samples)@self.inverse.T
                free=np.exp(-elapsed[:,None]/tau[None,:])@self.inverse.T
            self.forced_end.append(forced[-1].copy())
            blocks.extend((-forced/.001,-free/.001))
        return np.ascontiguousarray(np.column_stack((old_design[:,self.keep],*blocks)))

    def query(self,x):
        # Reuse exactly the predecessor's free-feature and original-coordinate derivatives.
        free=super().query(x)
        if free is None:return None
        features=[free[0][:len(self.keep)]];jac=[free[1][:len(self.keep)]]
        for mode in self.modes:
            start=len(self.keep)+mode*self.k;sl=slice(start,start+self.k)
            fv=free[0][sl];fj=free[1][sl];powers=fj[:,12+mode]
            # Derivative of powers cannot be obtained by dividing by entering voltage:
            # zero entering voltage is valid and must retain the resistance derivative.
            if self.family=='time_kernel':
                rate=np.exp(-x[mode]);c=self.pivots[mode];z=(rate-c)/(rate+c)
                derivative=np.zeros(self.k)
                derivative[1:]=np.arange(1,self.k)*z**np.arange(self.k-1)*(-2*rate*c/(rate+c)**2)
            else:
                half=(self.basis.hi[mode]-self.basis.lo[mode])/2
                u=(x[mode]-(self.basis.lo[mode]+self.basis.hi[mode])/2)/half
                derivative=np.zeros(self.k)
                for j in range(1,self.k):
                    coeff=np.zeros(j+1);coeff[j]=1
                    derivative[j]=np.polynomial.chebyshev.chebval(u,np.polynomial.chebyshev.chebder(coeff))/half
            forced_j=np.zeros((self.k,16));forced_j[:,7+mode]=powers;forced_j[:,mode]=x[7+mode]*derivative
            features.extend((x[7+mode]*powers,fv));jac.extend((forced_j,fj))
        return np.concatenate(features),np.vstack(jac)

    def replace_components(self,base_parts,design,queries):
        result=base_parts.copy()
        for component in range(6):
            first=len(self.keep)+component*self.k;sl=slice(first,first+self.k)
            result[:,:,component]=queries[:,sl]@design[:,sl].T
        return result

    def endpoint(self,x,elapsed):
        result=self.basis.endpoint(x);query=self.query(x)
        if query is None:return None
        for mode in self.modes:
            first=len(self.keep)+2*mode*self.k
            result[mode+1]=self.forced_end[mode]@query[0][first:first+self.k]+x[12+mode]*np.exp(-elapsed/np.exp(x[mode]))
        return result

    def memory(self):
        base=self.partition.memory();f=self.dim;k=self.k
        qr=8*f*(f+1)//2;boundary=base['boundary_B']+24*k
        scratch=base['extra_query_scratch_B']+24*(f-self.old_dim)+8*(6*k+16)
        total=qr+boundary+400+32+3848+scratch
        return dict(features=f,QR_numeric_B=qr,boundary_B=boundary,metadata_B=400,elapsed_pivots_B=32,
            nonbank_B=3848,query_scratch_B=scratch,QR_planned_subsystem_B=total,
            optional_column_scaling_B=8*f,equilibrated_QR_planned_subsystem_B=total+8*f,
            fits_10240B=False,target_measured=False,integrated_workspace_qualified=False,
            pivots_per_s=self.pivots.tolist(),rho=self.rho.tolist())
