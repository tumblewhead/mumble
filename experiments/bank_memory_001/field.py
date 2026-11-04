"""Fixed response projection; no moving centres, forgetting or evidence folding."""
import ctypes as C
from pathlib import Path
import subprocess
import numpy as np
from experiments.distinct_bank_integration_001.field import DistinctBankField

HERE=Path(__file__).resolve().parent

def projection(rank):
    if rank==13:return np.eye(13),np.eye(13),np.ones(13)
    # Kernel metric balances free and forced response in dimensionless time.
    # Fixed public grid, independent of observations/truth. Not a uniform certificate.
    from experiments.distinct_bank_integration_001.field import DistinctMap
    m=DistinctMap(HERE.parent/'distinct_bank_integration_001/map_n13e.json')
    sigma=np.exp(m.uj);G=(1+sigma[:,None]*sigma[None,:])/(sigma[:,None]+sigma[None,:])
    L=np.linalg.cholesky(G+np.eye(13)*1e-16)
    weights=m.weights(np.linspace(-1,1,2001)).T
    U,S,_=np.linalg.svd(L.T@weights,full_matrices=False)
    V=np.linalg.solve(L.T,U[:,:rank]);P=V.T@G
    return V,P,S

class Packed:
    def __init__(self,width,directory,precision='float64'):
        if precision not in ('float32','float64') or type(width) is not int or width<1:raise ValueError('packed precision/width')
        self.width=width;self.dtype=np.dtype(precision)
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        binary=directory/('qr_'+precision+'.so')
        if not binary.exists():subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC','-DSTORE_DOUBLE='+str(int(precision=='float64')),str(HERE/'qr.c'),'-lm','-o',str(binary)],check=True)
        self.lib=C.CDLL(str(binary.resolve()));self.lib.insert.argtypes=[C.c_void_p,C.c_int,C.POINTER(C.c_double)]
        self.values=np.zeros(width*(width+1)//2,dtype=self.dtype)
    def update(self,rows):
        rows=np.asarray(rows,dtype=float)
        if rows.ndim!=2 or rows.shape[1]!=self.width or not np.isfinite(rows).all():raise ValueError('finite full-width rows required')
        for row in rows:
            work=np.array(row,dtype=float,copy=True)
            if self.lib.insert(self.values.ctypes.data,self.width,work.ctypes.data_as(C.POINTER(C.c_double))):raise ValueError('packed QR nonfinite')
    def dense(self):
        r=np.zeros((self.width,self.width));r[np.triu_indices(self.width)]=self.values;return r

class SmallField:
    def __init__(self,config,center,rc,h,bank_map,source,directory,rank=5,precision='float64',center_chart=None):
        if rank not in (3,4,5,6,13):raise ValueError('supported rank')
        self.base=DistinctBankField(config,center,rc,h,bank_map,source)
        self.V,self.P,self.singular_values=projection(rank);self.rank=rank
        self.width=16+6*rank;self.hstart=3+6*rank
        self.packed=Packed(self.width,directory,precision)
        # These old roots are unused by the response-only base. Do not retain them.
        self.base.root=np.empty((0,0));self.base.legacy.root=np.empty((0,0))
        self.offset=np.zeros(self.width) if center_chart is None else self.coeff(self.base.features(center_chart))
        self.offset[-1]=0.
    @property
    def root(self):return self.packed.dense()
    @root.setter
    def root(self,r):
        if r.shape!=(self.width,self.width):raise ValueError('factor shape')
        self.packed.values[:]=r[np.triu_indices(self.width)]
    @property
    def state(self):return self.base.state
    @property
    def rc_free(self):return self.base.rc_free
    @property
    def rc_forced(self):return self.base.rc_forced
    @property
    def count(self):return self.base.count
    @property
    def noise(self):return self.base.noise
    @property
    def source(self):return self.base.source
    @property
    def center(self):return self.base.center
    @property
    def map(self):return self.base.map
    def _commit(self,*a):return self.base._commit(*a)
    def coeff(self,full):
        result=np.empty((self.width,)+full.shape[1:]);result[:3]=full[:3];result[self.hstart:]=full[81:]
        for j in range(6):result[3+j*self.rank:3+(j+1)*self.rank]=self.P@full[3+13*j:3+13*(j+1)]
        return result
    def features(self,x):return self.coeff(self.base.features(x))-self.offset
    def features_jacobian(self,x):return self.coeff(self.base.features_jacobian(x))
    def residual(self,x):return self.root@self.features(x)
    def transported(self,x):return self.base.transported(x)
    def update(self,first,observations,return_rows=False):
        old,state,free,forced,count,noise=self.base._stage_rows(first,observations)
        rows=np.empty((len(old),self.width));rows[:,:3]=old[:,:3];rows[:,self.hstart:]=old[:,81:]
        for j in range(6):rows[:,3+j*self.rank:3+(j+1)*self.rank]=old[:,3+13*j:3+13*(j+1)]@self.V
        rows[:,-1]+=rows@self.offset
        # Mutating failure quarantines at campaign level. No second history copy.
        self.packed.update(rows);self._commit(state,free,forced,count,noise)
        return rows if return_rows else None
    def storage(self):
        return dict(rank=self.rank,width=self.width,packed_factor_B=self.packed.values.nbytes,
            response_B=self.state.nbytes+self.rc_free.nbytes+self.rc_forced.nbytes,
            projection_ROM_B=self.V.nbytes+self.P.nbytes,precision=self.packed.dtype.name,
            query_dense_workspace_B=self.width*self.width*8,
            scope='Actual packed history; Python query workspace still exceeds target. No uniform error or lifetime rounding certificate.')
