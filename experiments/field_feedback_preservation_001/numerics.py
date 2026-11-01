"""Experimental original-origin tangent updates; no plant/truth access."""
import numpy as np
from experiments.slow_likelihood_diagnostic_001.numerics import features_jacobian
from experiments.foster_campaign_001.field_backend import transported


class Tangent:
    """Original-prior field linearized once per scheduled refresh.

    New rows own only samples after the anchor. The outgoing Gaussian is a
    reporting object, never the input of the next history update.
    """
    def __init__(self,objective,w,first):
        self.field=objective.field;self.mean=objective.mean;self.L=objective.root
        if first!=self.field.count:raise ValueError('anchor/history chronology mismatch')
        self.source=self.field.source
        self.anchor=np.asarray(w).copy();self.count=first;self.first=first
        x=self.mean+self.L@self.anchor
        self.phi=self.field.features(x)
        self.J=features_jacobian(self.field,x)@self.L
        old_r=self.field.root@self.phi;old_B=self.field.root@self.J
        self.factor=np.linalg.qr(np.vstack([np.column_stack([np.eye(16),self.anchor]),
                                           np.column_stack([old_B,old_r])]),mode='r')

    @property
    def P(self):return self.factor[:16,:16].T@self.factor[:16,:16]

    @property
    def g(self):return self.factor[:16,:16].T@self.factor[:16,16]

    def update(self,first,rows,source=None):
        rows=np.asarray(rows)
        if first!=self.count or (source is not None and source!=self.source):
            raise ValueError('source chronology/ownership mismatch')
        if rows.ndim!=2 or rows.shape[1]!=len(self.phi) or not np.isfinite(rows).all():
            raise ValueError('finite lifted response rows required')
        r=rows@self.phi;B=rows@self.J
        self.factor=np.linalg.qr(np.vstack([self.factor,np.column_stack([B,r])]),mode='r')
        self.count+=len(rows)

    def query(self):
        if self.field.count!=self.count:raise ValueError('readout/history chronology mismatch')
        R=self.factor[:16,:16];step=-np.linalg.solve(R,self.factor[:16,16])
        w=self.anchor+step;x=self.mean+self.L@w
        root=self.L@np.linalg.solve(R,np.eye(16))
        end,D=transported(self.field,x)
        return dict(w=w,x=x,root=root,end=end,endpoint_root=D@root,
                    linearized_cost=float(.5*self.factor[16,16]**2),
                    anchor_displacement_GN=float(np.linalg.norm(R@step)))

    def storage(self):
        return dict(packed_joint_tangent_factor_B=17*18//2*8,anchor_B=128,
                    features_B=self.phi.nbytes,dense_feature_derivative_B=self.J.nbytes,
                    subtotal_packed_B=17*18//2*8+128+self.phi.nbytes+self.J.nbytes,
                    scope='Additional dense-cache prototype payload; excludes field, prior and solver workspace; not an M23 layout')


def observed_hessian(objective,w,step=1e-4):
    """Diagnostic FD of analytic gradients in prior-whitened coordinates."""
    columns=[]
    for j in range(len(w)):
        d=np.zeros(len(w));d[j]=step
        columns.append((objective(w+d)[1]-objective(w-d)[1])/(2*step))
    H=np.column_stack(columns)
    return .5*(H+H.T),float(np.linalg.norm(H-H.T))


def polish_stationary(objective,w,max_rounds=12):
    """Observed-Newton diagnostic to resolve stalled GN fits, no new evidence.

    Accept by gradient residual when objective decrease is beneath roundoff;
    independently recheck Hessian/step stability afterward. Never treat GN
    and observed covariance as interchangeable.
    """
    w=np.asarray(w).copy();iterations=[];stop='round_limit'
    for _ in range(max_rounds):
        cost,g,P,_,_=objective(w);H,asym=observed_hessian(objective,w)
        vals=np.linalg.eigvalsh(H)
        if vals[0]<=0:stop='nonpositive_observed_hessian';break
        delta=-np.linalg.solve(H,g);decrement=float(g@np.linalg.solve(H,g))
        iterations.append(dict(cost=cost,gradient_inf=float(np.max(abs(g))),decrement=decrement,
                               Hessian_min_eigenvalue=float(vals[0]),Hessian_asymmetry_norm=asym))
        if decrement<=32*np.spacing(max(1.,abs(cost))):stop='observed_decrement_at_cost_roundoff';break
        accepted=False
        for power in range(18):
            trial=w+2.**-power*delta
            try:nc,ng,_,_,_=objective(trial)
            except (ValueError,OverflowError):continue
            # Same local stationarity equation even when scalar cost cannot
            # resolve a predicted improvement. Use a fixed observed metric.
            residual_decreased=ng@np.linalg.solve(H,ng)<decrement
            if nc<cost or (nc<=cost+64*np.spacing(max(1.,abs(cost))) and residual_decreased):
                w=trial;accepted=True;break
        if not accepted:stop='no_descent_or_residual_reduction';break
    cost,g,P,end,F=objective(w)
    H,asym=observed_hessian(objective,w);H2,_=observed_hessian(objective,w,step=3e-5)
    root=objective.root@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16))
    eig=np.linalg.eigvalsh(H)
    return dict(w=w,x=objective.mean+objective.root@w,root=root,end=end,F=F,cost=cost,stop=stop,
                gradient=g,GN_decrement=float(g@np.linalg.solve(P,g)),
                observed_decrement=float(g@np.linalg.solve(H,g)) if eig[0]>0 else None,
                Hessian_min_eigenvalue=float(eig[0]),Hessian_step_relative_difference=float(np.linalg.norm(H-H2)/np.linalg.norm(H)),
                Hessian_asymmetry_norm=asym,iterations=iterations)
