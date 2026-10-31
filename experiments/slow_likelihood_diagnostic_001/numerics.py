"""Bounded-workspace exact diagnostics and local constrained GN optimization."""
import numpy as np
from experiments.foster_uncertainty_audit_001.conditional_packet import partition


class Exact:
    """Original prior once plus all ordered observations; transport initial J exactly."""
    def __init__(self, model, obs, mean, root, chunk=16384):
        self.model,self.obs,self.mean,self.root,self.chunk=model,obs,mean,root,chunk
        self.calls=0;self.cached=None;self.value=None

    def __call__(self,w):
        if self.cached is not None and np.array_equal(w,self.cached):return self.value
        x=self.mean+self.root@w;end=x.copy();F=np.eye(16)
        cost=.5*float(w@w);g=w.copy();P=np.eye(16)
        for first in range(0,len(self.obs),self.chunk):
            o=self.obs[first:first+self.chunk]
            v,J,newend,A=self.model.evaluate(end,o)
            r=(v-o[:,3])/o[:,4];B=(J@(F@self.root))/o[:,4,None]
            cost+=.5*float(r@r);g+=B.T@r;P+=B.T@B
            end=newend;F=A@F
        if not np.isfinite(cost) or not np.isfinite(g).all():raise ValueError('nonfinite exact objective')
        self.calls+=1;self.cached=w.copy();self.value=(cost,g,P,end,F)
        return self.value


def features_jacobian(field,x):
    """Analytic derivative of the existing lifted feature vector, same chart."""
    field.features(x)  # Same support checks; never extrapolate.
    a,s=partition(x);da=np.zeros((11,16));da[:4,:4]=np.eye(4)
    da[4,5]=-a[4]
    for row,col in [(5,6),(6,7),(7,9),(8,11),(9,13)]:da[row,col]=a[row]
    e=np.exp(-2*abs(x[4]));da[10,4]=a[9]*4*e/(1+e)**2;da[10,13]=a[10]
    dt=np.zeros((5,16));gaps=np.exp(x[[8,10,12]])
    for i in range(3):dt[i,[8,10,12][:i+1]]=gaps[:i+1]/s[i]/field.halfwidth[i]
    for i,col in [(3,14),(4,15)]:dt[i,col]=1/field.halfwidth[i];dt[i,5]=-1/field.halfwidth[i]
    t=np.log(s/field.center)/field.halfwidth
    T=np.ones((5,field.n));D=np.zeros_like(T);T[:,1]=t;D[:,1]=1
    for k in range(2,field.n):
        T[:,k]=2*t*T[:,k-1]-T[:,k-2]
        D[:,k]=2*T[:,k-1]+2*t*D[:,k-1]-D[:,k-2]
    rows=[da[0],da[4],da[5]]
    for i in range(3):
        for amp in [1+i,6+i]:
            for k in range(field.n):rows.append(T[i,k]*da[amp]+a[amp]*D[i,k]*dt[i])
    for amp in [9,10]:
        for i,j in field.pairs:
            base=T[3,i]*T[4,j]
            grad=D[3,i]*T[4,j]*dt[3]+T[3,i]*D[4,j]*dt[4]
            rows.append(base*da[amp]+a[amp]*grad)
    rows.append(np.zeros(16));return np.array(rows)


class Compressed:
    def __init__(self,field,mean,root):self.field,self.mean,self.root=field,mean,root;self.calls=0
    def __call__(self,w):
        x=self.mean+self.root@w;r=self.field.residual(x)
        B=self.field.root@features_jacobian(self.field,x)@self.root
        self.calls+=1
        return .5*float(w@w+r@r),w+B.T@r,np.eye(16)+B.T@B,None,None


def constrained_basis(mean,root,logq):
    if logq is None:return np.zeros(16),np.eye(16)
    a=root[5];b=logq-mean[5]
    if not a@a>0:raise ValueError('fixed-Q constraint has zero prior support')
    _,_,V=np.linalg.svd(a[None,:],full_matrices=True)
    return a*b/(a@a),V[1:].T


def solve(objective,start=None,logq=None,max_rounds=60):
    w0,Z=constrained_basis(objective.mean,objective.root,logq)
    w=w0.copy() if start is None else w0+Z@(Z.T@(np.asarray(start)-w0))
    cost,g,P,_,_=objective(w);reject=0;stop='round_limit'
    for iteration in range(max_rounds):
        grad=Z.T@g;H=Z.T@P@Z;step=-np.linalg.solve(H,grad)
        decrement=float(-grad@step)
        # Cost-scaled roundoff stop, distinct from physical convergence/coverage.
        if decrement <= 32*np.spacing(max(abs(cost),1.)):
            stop='GN_decrement_at_cost_roundoff';break
        if np.max(abs(grad))<1e-6:stop='gradient';break
        accepted=False
        for power in range(18):
            trial=w+2.**-power*(Z@step)
            try:new=objective(trial)
            except (ValueError,OverflowError,FloatingPointError):reject+=1;continue
            if new[0]<cost:
                w=trial;cost,g,P,_,_=new;accepted=True;break
        if not accepted:stop='no_descent';break
    cost,g,P,end,F=objective(w)
    H=Z.T@P@Z;grad=Z.T@g
    diagnostic={'stop':stop,'rounds':iteration+1,'cost':cost,'domain_rejections':reject,
        'free_gradient_inf':float(np.max(abs(grad))),
        'free_GN_decrement_squared':float(grad@np.linalg.solve(H,grad)),
        'cost_ulp':float(np.spacing(cost)),'fixed_logQ':logq}
    root=objective.root@Z@np.linalg.solve(np.linalg.cholesky(H).T,np.eye(Z.shape[1]))
    return {'w':w,'x':objective.mean+objective.root@w,'root':root,'diagnostic':diagnostic,
            'end':end,'F':F}


def predictive(model,end,root,future):
    v,J,_,_=model.evaluate(end,future);r=(v-future[:,3])/future[:,4]
    B=(J@root)/future[:,4,None];C=np.linalg.cholesky(np.eye(root.shape[1])+B.T@B)
    proj=np.linalg.solve(C,B.T@r);quad=float(r@r-proj@proj)
    logdet=float(2*np.log(np.diag(C)).sum())
    return {'records':len(future),'NLL_without_common_noise_constant':.5*(quad+logdet),
        'quadratic':quad,'logdet_ratio':logdet,'fixed_point_standardized_RMS':float(np.sqrt(np.mean(r*r))),
        'mean_residual_mV':float(1000*np.mean(v-future[:,3]))}
