"""Desktop coefficient feasibility candidate. No truth/prior or firmware claims."""
import ctypes as C
import itertools
import math
import numpy as np
from numpy.polynomial.chebyshev import chebvander, chebval, chebder
from experiments.joint_rate_history_001.field import pointer, DP
from experiments.foster_uncertainty_audit_001.conditional_packet import transport

DEPS = [(), (0,), (1,), (2,), (), (), (0,), (1,), (2,), (3,4), (3,4), ()]
PAIRS = list(itertools.combinations_with_replacement(range(12), 2))


def project(values, inverse):
    out = values.copy()
    for axis in range(out.ndim):
        out = np.moveaxis(np.tensordot(inverse, out, axes=(1,axis)), 0, axis)
    return out


def polynomial(coeff, coords):
    out = coeff
    for x in coords:
        out = chebval(x, out)
    return float(out)


class Coefficients:
    def __init__(self, config, center, binary, degree=2, sparse=False, source='fixture'):
        if degree not in (1,2) or sparse and degree != 2:
            raise ValueError('study degree')
        if config.get('hysteresis_chart') != 'bounded':raise ValueError('bounded chart required')
        self.source=source;self.degree=degree;self.n=degree+1;self.sparse=sparse
        self.center=np.array(center,dtype=float,copy=True);self.halfwidth=np.ones(5)
        if self.center.shape!=(5,) or not np.isfinite(self.center).all() or np.any(self.center<=0):raise ValueError('shape center')
        if np.any(self.center[:2]*np.e >= self.center[1:3]/np.e):raise ValueError('ordered public box required')
        self.cal=np.array([config['reference_temperature_K'],config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'],*config['arrhenius_A_K']],dtype=float)
        if self.cal.shape!=(14,) or not np.isfinite(self.cal).all() or self.cal[0]!=298.15 or self.cal[2]<=0:raise ValueError('reference calibration')
        self.nodes=np.cos(np.pi*(np.arange(self.n)+.5)/self.n)
        self.inverse=np.linalg.inv(chebvander(self.nodes,degree))
        self.rates=(self.center[:,None]*np.exp(self.nodes)).ravel().copy()
        self.p1=np.eye(self.n);self.p2=np.eye(self.n*self.n)
        self.width=4+6*self.n+2*self.n*self.n
        self.state=np.zeros(6*self.n+2*self.n*self.n+3)
        self.state[:3*self.n]=1.;self.state[6*self.n:6*self.n+self.n*self.n]=1.
        self.count=0;self.noise=0.
        self.entries=[]
        # Native lifted order: z,q,R0, three E/u groups,uh,Eh,constant.
        bases=[0,3,3+2*self.n,3+4*self.n,1,2,3+self.n,3+3*self.n,3+5*self.n,3+6*self.n,3+6*self.n+self.n*self.n,self.width-1]
        for i,j in PAIRS:
            deps=tuple(sorted(set(DEPS[i])|set(DEPS[j])))
            indices=list(itertools.product(range(self.n),repeat=len(deps)))
            left=[];right=[]
            for ix in indices:
                lookup=dict(zip(deps,ix))
                def index(col):
                    local=tuple(lookup[d] for d in DEPS[col])
                    return bases[col]+(np.ravel_multi_index(local,(self.n,)*len(local)) if local else 0)
                left.append(index(i));right.append(index(j))
            mask=np.array([sum(ix)<=degree or not sparse for ix in indices])
            self.entries.append(dict(pair=(i,j),deps=deps,left=np.array(left,dtype=np.intp),right=np.array(right,dtype=np.intp),mask=mask,coeff=np.zeros(int(mask.sum()))))
        self.lib=C.CDLL(str(binary));self.fn=self.lib.response_rows
        self.fn.argtypes=[DP,C.c_size_t,DP,C.c_int,C.c_int,C.c_int,DP,DP,DP,DP,DP];self.fn.restype=C.c_int

    def advance(self, first, observations, source):
        obs=np.asarray(observations,dtype=float)
        if type(first) is not int or first!=self.count or source!=self.source:raise ValueError('source/order mismatch')
        if obs.ndim!=2 or obs.shape[1]!=5 or not 1<=len(obs)<=1024 or not np.isfinite(obs).all():raise ValueError('bounded finite input')
        if np.any(obs[:,2]!=25.) or np.any(obs[:,0]<0) or np.any(obs[:,0]>1) or np.any(abs(obs[:,1])>.25) or np.any(obs[:,4]<=0):raise ValueError('stationary reference input support')
        obs=np.ascontiguousarray(obs);state=self.state.copy();rows=np.empty((len(obs),self.width))
        if self.fn(pointer(obs),len(obs),pointer(self.cal),self.n,self.n,self.n*self.n,pointer(self.rates),pointer(self.p1),pointer(self.p2),pointer(state),pointer(rows)):
            raise ValueError('response failure')
        gram=rows.T@rows;trial=[]
        for entry in self.entries:
            values=gram[entry['left'],entry['right']].reshape((self.n,)*len(entry['deps']))
            trial.append(entry['coeff']+project(values,self.inverse).ravel()[entry['mask']])
        noise=self.noise+float(np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi))
        if not np.isfinite(state).all() or not np.isfinite(noise) or not all(np.isfinite(c).all() for c in trial):raise ValueError('nonfinite candidate')
        self.state=state;self.noise=noise;self.count+=len(obs)
        for e,c in zip(self.entries,trial):e['coeff']=c

    def evaluate(self, amplitude, shape):
        a=np.asarray(amplitude,dtype=float);shape=np.asarray(shape,dtype=float)
        if a.shape!=(11,) or shape.shape!=(5,) or not np.isfinite(a).all() or not np.isfinite(shape).all() or np.any(shape<=0):raise ValueError('query shape/finite')
        t=np.log(shape/self.center)
        if np.any(abs(t)>1+1e-12):raise ValueError('outside computational domain; unresolved not excluded')
        A,lo,hi=self.state[-3:]
        if min(a[4:10])<=0 or abs(a[10])>a[9] or a[0]-a[4]*hi<0 or a[0]-a[4]*lo>1:raise ValueError('physical path unsupported')
        G=np.zeros((12,12));dG=np.zeros((5,12,12))
        for entry in self.entries:
            deps=entry['deps'];c=np.zeros(self.n**len(deps));c[entry['mask']]=entry['coeff'];c=c.reshape((self.n,)*len(deps))
            i,j=entry['pair'];G[i,j]=G[j,i]=polynomial(c,t[list(deps)])
            for axis,d in enumerate(deps):dG[d,i,j]=dG[d,j,i]=polynomial(chebder(c,axis=axis),t[list(deps)])
        b=np.r_[a,1.];nll=.5*float(b@G@b)+self.noise
        g=G[:11]@b;gs=.5*np.einsum('i,kij,j->k',b,dG,b)
        n=self.n;E=self.state[:3*n].reshape(3,n);u=self.state[3*n:6*n].reshape(3,n)
        h=self.state[6*n:6*n+2*n*n].reshape(2,n,n)
        coeff=np.r_[A,[polynomial(project(E[j],self.inverse),[t[j]]) for j in range(3)],
                    [polynomial(project(u[j],self.inverse),[t[j]]) for j in range(3)],
                    [polynomial(project(v,self.inverse),t[3:]) for v in h]]
        end=transport(coeff)@a
        return dict(nll=nll,gradient_amplitude=g,gradient_shape=gs,precision_amplitude=G[:11,:11],gram=G,end=end)

    def storage(self, chunk=1024):
        coeff=sum(e['coeff'].nbytes for e in self.entries)
        arrays=sum(v.nbytes for v in vars(self).values() if isinstance(v,np.ndarray))
        indices=sum(e['left'].nbytes+e['right'].nbytes+e['mask'].nbytes for e in self.entries)
        return dict(coefficients_B=coeff,response_state_B=self.state.nbytes,domain_and_tables_arrays_B=arrays-self.state.nbytes,
            index_mask_arrays_B=indices,retained_numpy_arrays_B=coeff+arrays+indices,
            numeric_coefficients_response_domain_scalars_B=coeff+self.state.nbytes+80+16,
            chunk_rows_B=8*chunk*self.width,chunk_observations_B=8*chunk*5,gram_scratch_B=8*self.width**2,
            transaction_coefficients_B=coeff,transaction_state_B=self.state.nbytes,
            max_entry_projection_values_B=8*self.n**3,query_gram_and_derivative_B=8*6*12*12,
            lifted_width=self.width,gram_multiply_terms_per_sample=self.width**2,
            scope='Array payloads and main scratch categories, not peak RSS or complete target RAM. Python objects, BLAS temporaries, original prior, solver, full query scratch, stacks/ISR, registry, metadata and allocation overhead additional. No hypothetical scratch aliasing credited.')
