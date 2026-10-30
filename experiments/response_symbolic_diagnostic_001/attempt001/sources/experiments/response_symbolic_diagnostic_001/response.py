"""Fixed-domain coordinate interventions; no changes to physical laws."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'history_basis_comparison_001'))
from basis import Basis,cheb


class ResponseBasis(Basis):
    def __init__(self,arm,domain,mean,sd,lower,upper):
        self.physical_RC=arm['physical_RC'];self.physical_hysteresis=arm['physical_hysteresis']
        super().__init__('log_chebyshev',4,domain,mean,sd,lower,upper)
        if arm['tensor_hysteresis']:
            # Inherited OCV columns also expand, but are ignored: the separate
            # charge-coordinate OCV representation remains unchanged.
            self.pairs=[(i,j) for i in range(self.m) for j in range(self.m)]
            u=np.cos((2*np.arange(self.m)+1)*np.pi/(2*self.m))
            v=np.polynomial.chebyshev.chebvander(u,4)
            self.tensor=np.array([[v[a,i]*v[b,j] for i,j in self.pairs]
                                 for a in range(self.m) for b in range(self.m)])
            self.project=np.linalg.inv(self.tensor)
            self.dim=6*self.m+3*len(self.pairs)+1

    def sign(self,j):
        if j<3 and self.physical_RC:return -1
        if 3<=j<5 and self.physical_hysteresis:return 1
        return 0

    def physical_domain(self,j):
        sign=self.sign(j);ends=np.exp(sign*np.array([self.lo[j],self.hi[j]]))
        return np.mean(ends),np.ptp(ends)/2

    def inverse(self,u,j):
        sign=self.sign(j)
        if not sign:return super().inverse(u,j)
        center,half=self.physical_domain(j)
        return np.log(center+half*u)/sign

    def coordinate(self,value,j):
        sign=self.sign(j)
        if not sign:return super().coordinate(value,j)
        center,half=self.physical_domain(j);v=np.exp(sign*value)
        return (v-center)/half,sign*v/half


def exact_trace(obs,points):
    """Original recurrence independently vectorized over queries, not fitted."""
    x=np.asarray(points);tau=np.exp(x[:,:3]);f=np.zeros_like(tau);a=np.ones_like(tau)
    hb=np.zeros(len(x));ha=np.ones(len(x));charge=0.;elapsed=0.;qp=0.;qm=0.
    parts=np.empty((len(x),len(obs),9));hs=np.empty((len(x),len(obs),2))
    max_free_gap=0.
    for k,(dt,current,voltage) in enumerate(obs):
        e=np.exp(-dt/tau);om=-np.expm1(-dt/tau);f=e*f+om*current;a=e*a
        if current and dt:
            q=np.exp(x[:,3 if current>0 else 4])*abs(current)*dt/3600
            e=np.exp(-q);om=-np.expm1(-q);hb=e*hb+om*np.sign(current);ha=e*ha
        charge+=current*dt/3600;elapsed+=dt
        qp+=max(current,0)*dt/3600;qm+=max(-current,0)*dt/3600
        max_free_gap=max(max_free_gap,float(np.max(abs(a-np.exp(-elapsed/tau)))),
                         float(np.max(abs(ha-np.exp(-np.exp(x[:,3])*qp-np.exp(x[:,4])*qm)))))
        for mode in range(3):
            parts[:,k,2*mode]=-x[:,7+mode]*f[:,mode]/.001
            parts[:,k,2*mode+1]=-x[:,12+mode]*a[:,mode]/.001
        parts[:,k,6]=-x[:,10]*hb/.001;parts[:,k,7]=-x[:,10]*x[:,15]*ha/.001
        z=x[:,11]-charge/np.exp(x[:,5]);parts[:,k,8]=(3+1.15*z+.08*np.tanh(8*(z-.5)))/.001
        hs[:,k,0]=hb;hs[:,k,1]=ha
    endpoint=np.column_stack((z,x[:,7:10]*f+x[:,12:15]*a,hb+x[:,15]*ha))
    offset=(-x[:,6,None]*obs[None,:,1]-obs[None,:,2])/.001
    return parts,offset,hs,endpoint,dict(elapsed_s=elapsed,positive_throughput_Ah=qp,
        negative_throughput_Ah=qm,max_free_response_closed_form_gap=max_free_gap)


def approximate_parts(basis,partition,full,obs,charges,points):
    results=[partition.query(x) for x in points]
    if any(v is None for v in results):raise ValueError('query outside frozen domain')
    features=np.stack([v[0] for v in results]);m=basis.m;t=len(basis.pairs)
    bounds=[0,m,2*m,3*m,4*m,5*m,6*m,6*m+t,6*m+2*t]
    parts=np.empty((len(points),len(obs),9))
    for j in range(8):parts[:,:,j]=features[:,bounds[j]:bounds[j+1]]@full[:,bounds[j]:bounds[j+1]].T
    charge_rows=partition.charge_rows(charges)
    if charge_rows is None:raise ValueError('charge domain exceeded')
    parts[:,:,8]=features[:,-partition.k:]@charge_rows[:,:partition.k].T
    return parts,results


def approximate_hysteresis(basis,full,points):
    phi=[]
    for x in points:
        a=cheb(basis.coordinate(x[3],3)[0],4)[0];b=cheb(basis.coordinate(x[4],4)[0],4)[0]
        phi.append([a[i]*b[j] for i,j in basis.pairs])
    phi=np.array(phi);start=6*basis.m;t=len(basis.pairs)
    return np.stack((-.001*phi@full[:,start:start+t].T,-.001*phi@full[:,start+t:start+2*t].T),axis=2)


def summarize(approx,exact,offset,ids):
    ld=np.longdouble;delta=approx.astype(ld)-exact.astype(ld)
    residual=exact.astype(ld).sum(axis=2)+offset.astype(ld);total=delta.sum(axis=2)
    linear=(residual*total).sum(axis=1);quadratic=(total*total).sum(axis=1)/2;gap=linear+quadratic
    attribution=(delta*(residual+total/2)[:,:,None]).sum(axis=1)
    low=int(np.argmin(gap));high=int(np.argmax(gap));span=gap[high]-gap[low]
    contributions=attribution[high]-attribution[low]
    corr=[]
    for j in range(9):
        rr=residual.ravel();dd=delta[:,:,j].ravel();den=np.sqrt((rr*rr).sum()*(dd*dd).sum())
        corr.append(float((rr*dd).sum()/den) if den else None)
    energy=(delta*delta).sum(axis=(0,1));rms=np.sqrt((residual*residual).mean(axis=1))*.001
    direct_exact=(residual*residual).sum(axis=1)/2
    direct_approx=((residual+total)**2).sum(axis=1)/2
    return dict(error_oscillation_NLL=float(span),error_min_NLL=float(gap[low]),error_max_NLL=float(gap[high]),
        witness_query_indices=[int(ids[low]),int(ids[high])],signed_witness_contributions_NLL=contributions.astype(float).tolist(),
        signed_witness_percent=(100*contributions/span).astype(float).tolist() if span else None,
        linear_witness_span_NLL=float(linear[high]-linear[low]),quadratic_witness_span_NLL=float(quadratic[high]-quadratic[low]),
        max_quadratic_error_NLL=float(np.max(quadratic)),peak_component_voltage_error_V=(np.max(abs(delta),axis=(0,1))*.001).astype(float).tolist(),
        RMS_component_voltage_error_V=(np.sqrt(energy/(len(ids)*approx.shape[1]))*.001).astype(float).tolist(),
        residual_component_cosine=corr,exact_residual_RMS_V_range=[float(np.min(rms)),float(np.max(rms))],
        attribution_identity_max_gap=float(np.max(abs(attribution.sum(axis=1)-gap))),
        cost_identity_max_gap=float(np.max(abs(direct_approx-direct_exact-gap))),
        cost_identity_roundoff_scale=float(np.max(abs(direct_approx)+abs(direct_exact))),
        cost_gaps=gap.astype(float).tolist(),direct_approx_costs=direct_approx.astype(float).tolist())
