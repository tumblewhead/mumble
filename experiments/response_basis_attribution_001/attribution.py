"""Signed response/sensitivity error decomposition; no new independent evidence."""
import numpy as np
from itertools import combinations

GROUPS={'RC1':([1,6],[11]),'RC2':([2,7],[12]),'RC3':([3,8],[13]),'hysteresis':([9,10],[14,15])}
PAIRS=list(combinations(range(4),2))


def split_defects(amplitude,exact_J,approx_J):
    delta=approx_J-exact_J;dr=[];dJ=[]
    for amp,shape in GROUPS.values():
        v=np.zeros_like(delta);v[:,amp+shape]=delta[:,amp+shape]
        dr.append(delta[:,amp]@amplitude[amp]);dJ.append(v)
    return np.asarray(dr),np.asarray(dJ)


def terms(r,J,dr,dJ):
    parts=[]
    for p in range(4):parts.append([J.T@dr[p],dJ[p].T@r,dJ[p].T@dr[p]])
    pairs=[dJ[p].T@dr[q]+dJ[q].T@dr[p] for p,q in PAIRS]
    return np.array(parts),np.array(pairs)


class Attribution:
    def __init__(self,a):
        self.a=np.asarray(a);self.scale=np.r_[np.maximum(abs(self.a),[.1,.01,.01,.01,1.,.01,.01,.01,.01,.001,.001]),np.ones(5)]
        self.parts=np.zeros((4,3,16));self.pairs=np.zeros((6,16));self.exact_gradient=np.zeros(16);self.approx_gradient=np.zeros(16)
        self.row_sq=np.zeros(4);self.row_max=np.zeros(4);self.rate_sq=np.zeros(5);self.rate_max=np.zeros(5)
        self.count=0;self.response_closure=0.;self.jacobian_closure=0.
    def advance(self,r,J,approx_r,approx_J,sigma):
        dr,dJ=split_defects(self.a,J,approx_J);parts,pairs=terms(r,J,dr,dJ)
        self.parts+=parts;self.pairs+=pairs;self.exact_gradient+=J.T@r;self.approx_gradient+=approx_J.T@approx_r
        voltage=dr*sigma[None,:];rates=(approx_J[:,11:]-J[:,11:])*sigma[:,None]
        self.row_sq+=np.sum(voltage**2,axis=1);self.row_max=np.maximum(self.row_max,np.max(abs(voltage),axis=1))
        self.rate_sq+=np.sum(rates**2,axis=0);self.rate_max=np.maximum(self.rate_max,np.max(abs(rates),axis=0))
        self.response_closure=max(self.response_closure,float(np.max(abs((approx_r-r-dr.sum(axis=0))*sigma))))
        self.jacobian_closure=max(self.jacobian_closure,float(np.max(abs((approx_J-J-dJ.sum(axis=0))*self.scale[None,:]*sigma[:,None]))))
        self.count+=len(r)
    def report(self,qr_gradient):
        den=max(1.,np.linalg.norm(self.exact_gradient*self.scale));total=self.approx_gradient-self.exact_gradient
        reconstructed=self.parts.sum(axis=(0,1))+self.pairs.sum(axis=0)
        groups={}
        for i,name in enumerate(GROUPS):
            vector=self.parts[i].sum(axis=0)
            groups[name]=dict(signed_gradient_terms=self.parts[i],scaled_gradient_term_norms=np.linalg.norm(self.parts[i]*self.scale,axis=1),
                one_group_relative_gradient_defect=float(np.linalg.norm(vector*self.scale)/den),
                voltage_RMS_V=float(np.sqrt(self.row_sq[i]/self.count)),voltage_max_V=float(self.row_max[i]))
        return dict(groups=groups,pair_interaction_vectors=self.pairs,pair_names=[list((list(GROUPS)[p],list(GROUPS)[q])) for p,q in PAIRS],
            relative_pair_interaction_norms=np.linalg.norm(self.pairs*self.scale,axis=1)/den,
            exact_gradient=self.exact_gradient,total_gradient_defect=total,reconstructed_defect=reconstructed,gradient_scale=self.scale,
            relative_total_gradient_defect=float(np.linalg.norm(total*self.scale)/den),
            relative_attribution_closure=float(np.linalg.norm((reconstructed-total)*self.scale)/den),
            relative_QR_gradient_closure=float(np.linalg.norm((qr_gradient-self.approx_gradient)*self.scale)/den),
            response_partition_closure_max_V=self.response_closure,jacobian_partition_closure_max_scaled_V=self.jacobian_closure,
            shape_derivative_RMS_V=np.sqrt(self.rate_sq/self.count),shape_derivative_max_V=self.rate_max,
            shape_channel_order=['logtau1','logtau2','logtau3','logkplus','logkminus'])
