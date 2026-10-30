"""Stationary charge-basis history; all likelihood and GN cross terms retained."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'history_basis_comparison_001'))
from basis import Basis


def ocv(z):return 3+1.15*z+.08*np.tanh(8*(z-.5))
def slope(z):return 1.15+.64*(1-np.tanh(8*(z-.5))**2)


class Partition:
    def __init__(self,basis,degree,charge_limits):
        self.basis=basis;self.degree=degree;self.k=degree+1
        self.m=6*basis.m+2*len(basis.pairs)+2
        self.limits=np.asarray(charge_limits);self.center=np.mean(self.limits);self.half=np.ptp(self.limits)/2
        u=np.cos((2*np.arange(self.k)+1)*np.pi/(2*self.k))
        self.nodes=self.center+self.half*u
        self.inverse=np.linalg.inv(np.polynomial.chebyshev.chebvander(u,degree))

    def charge_rows(self,charges):
        c=np.asarray(charges)
        if np.any(c<self.limits[0]) or np.any(c>self.limits[1]):return None
        return np.ascontiguousarray(np.polynomial.chebyshev.chebvander((c-self.center)/self.half,2*self.degree))

    def query(self,x):
        result=self.basis.features(x)
        if result is None:return None
        f,j=result;end=6*self.basis.m+2*len(self.basis.pairs)
        dynamic=np.r_[f[:end],f[-1],1.]
        jd=np.vstack((j[:end],j[-1],np.zeros(16)))
        chi=np.exp(-x[5]);z=x[11]-chi*self.nodes
        if np.any(z<0) or np.any(z>1):return None
        u=(self.inverse@ocv(z))/.001
        ju=np.zeros((self.k,16))
        ju[:,11]=(self.inverse@slope(z))/.001
        ju[:,5]=(self.inverse@(slope(z)*chi*self.nodes))/.001
        return np.r_[dynamic,u],np.vstack((jd,ju))

    def gram(self,g,b,mom):
        matrix=np.zeros((self.m+self.k,self.m+self.k))
        upper=np.zeros((self.m,self.m));upper[np.triu_indices(self.m)]=g
        matrix[:self.m,:self.m]=upper+np.triu(upper,1).T
        matrix[:self.m,self.m:]=b;matrix[self.m:,:self.m]=b.T
        i,j=np.indices((self.k,self.k))
        matrix[self.m:,self.m:]=(mom[i+j]+mom[abs(i-j)])/2
        return matrix

    def memory(self):
        m,k,d=self.m,self.k,self.basis.degree
        numeric=8*(m*(m+1)//2+m*k+2*k-1)
        qr=8*(m+k)*(m+k+1)//2
        boundary=8*(6*(d+1)+2*(d+1)**2+1)
        scratch=8*(3*(m+k)+3*k+10*(d+1)+16)
        common=boundary+400+3848+scratch
        return dict(moment_numeric_B=numeric,QR_numeric_B=qr,exact_numeric_saving_B=qr-numeric,
                    boundary_B=boundary,new_bank_metadata_estimate_domains_B=400,
                    inherited_nonbank_reservations_B=3848,extra_query_scratch_B=scratch,
                    moment_planned_subsystem_B=numeric+common,QR_planned_subsystem_B=qr+common,
                    moment_retained_numeric_and_boundary_B=numeric+boundary,
                    fits_declared_10240B_plan=numeric+common<=10240,
                    target_measured=False,integrated_workspace_qualified=False)


def dynamic_rows(basis,full_rows,observations):
    end=6*basis.m+2*len(basis.pairs)
    return np.ascontiguousarray(np.column_stack((full_rows[:,:end],full_rows[:,-1],-observations[:,2]/.001)))
