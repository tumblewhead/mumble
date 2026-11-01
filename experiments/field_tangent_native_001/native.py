"""Explicit-workspace C tangent kernel; original prior and field remain borrowed."""
import ctypes as C
import hashlib
from pathlib import Path
import shutil
import subprocess
import numpy as np

HERE=Path(__file__).resolve().parent
DP=C.POINTER(C.c_double)
def ptr(a):return a.ctypes.data_as(DP)
def array(a,shape):
    a=np.ascontiguousarray(a,dtype=np.float64)
    if a.shape!=shape or not np.isfinite(a).all():raise ValueError('finite array shape '+str(shape))
    return a

def build(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for name in ('kernel.c','kernel.h'):shutil.copy2(HERE/name,destination/name)
    shutil.copy2(HERE.parent/'joint_rate_history_001/probe.c',destination/'response.c')
    binary=destination/'tangent.so'
    subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror',
                    '-pedantic','-fPIC','-fstack-usage','-shared',str(destination/'kernel.c'),str(destination/'response.c'),'-lm','-o',str(binary)],check=True)
    return binary

class Native:
    def __init__(self,binary,field,mean,L):
        if field.degree!=5 or field.width!=82:raise ValueError('native tangent requires degree5 width82')
        self.field=field;self.mean=array(mean,(16,));self.L=array(L,(16,16))
        self.source=int.from_bytes(hashlib.sha256(str(field.source).encode()).digest()[:8],'little')
        self.lib=C.CDLL(str(Path(binary).resolve()))
        self.lib.ft_context_bytes.restype=C.c_size_t;self.lib.ft_work_bytes.restype=C.c_size_t
        self.context=C.create_string_buffer(self.lib.ft_context_bytes());self.work=C.create_string_buffer(self.lib.ft_work_bytes())
        self.lib.ft_init.argtypes=[C.c_void_p,C.c_void_p,C.c_uint64,C.c_uint64]+[DP]*6
        self.lib.ft_update.argtypes=[C.c_void_p,C.c_void_p,C.c_uint64,C.c_uint64,DP,C.c_size_t]+[DP]*4
        self.lib.ft_query.argtypes=[C.c_void_p,C.c_void_p,C.c_uint64]+[DP]*8
        self.lib.ft_projection.argtypes=[C.c_void_p]+[DP]*5
        self.lib.ft_info.argtypes=[C.c_void_p,C.POINTER(C.c_uint64),C.POINTER(C.c_uint64)]
        # Fused scratch is lazy: projection/reference-only users need none.
        self._step_work=None;self._step_cache=None
    def check(self,status):
        if status:raise ValueError('native tangent status '+str(status))
    def initialize(self,w):
        self._step_cache=None
        w=array(w,(16,));f=self.field
        self.check(self.lib.ft_init(self.context,self.work,self.source,f.count,ptr(self.mean),ptr(self.L),ptr(w),
                                   ptr(array(f.root,(82,82))),ptr(f.center),ptr(f.halfwidth)))
    @property
    def count(self):
        source=C.c_uint64();count=C.c_uint64()
        self.check(self.lib.ft_info(self.context,C.byref(source),C.byref(count)))
        if source.value!=self.source:raise ValueError('native tangent source mismatch')
        return count.value
    def update(self,first,rows,source=None):
        self._step_cache=None
        if source is not None and source!=self.field.source:raise ValueError('native tangent source mismatch')
        if not isinstance(first,(int,np.integer)) or first<0:raise ValueError('native tangent chronology')
        rows=np.asarray(rows);rows=array(rows,(len(rows),82));f=self.field
        self.check(self.lib.ft_update(self.context,self.work,self.source,first,ptr(rows),len(rows),ptr(self.mean),ptr(self.L),ptr(f.center),ptr(f.halfwidth)))
    def query(self,state=None,count=None,reuse=False):
        if reuse and self._step_cache is not None:
            cached_state,cached_count,status=self._step_cache
            if state is cached_state and count==cached_count:
                self._step_cache=None
                self.check(status)
                out=self._step_output if reuse else self._step_output.copy()
                return self._decode(out,copy_arrays=False)
        f=self.field;state=array(f.state if state is None else state,(111,));out=np.empty(307)
        self.check(self.lib.ft_query(self.context,self.work,f.count if count is None else count,ptr(self.mean),ptr(self.L),
                                    ptr(f.center),ptr(f.halfwidth),ptr(state),ptr(f.p1),ptr(f.p2),ptr(out)))
        return self._decode(out)
    @staticmethod
    def _decode(out,copy_arrays=True):
        def owned(a):return a.copy() if copy_arrays else a
        return dict(w=owned(out[:16]),x=owned(out[16:32]),end=owned(out[32:48]),endpoint_root=owned(out[48:304].reshape(16,16)),
                    linearized_cost=float(out[304]),logdet_precision=float(out[305]),anchor_displacement_GN=float(out[306]))
    def step(self,first,rows,state,hz,query=True):
        """Commit response/QR once; cache joint readout, including domain failure.

        rows and state are checked by C. Published query results own their arrays
        by default; reuse=True is private to immediate backend publication.
        """
        self._step_cache=None
        if not isinstance(first,(int,np.integer)) or first<0 or first>2**64-1:
            raise ValueError('native tangent chronology')
        rows=np.ascontiguousarray(rows,dtype=np.float64)
        if rows.ndim!=2 or rows.shape[1]!=5 or not 1<=len(rows)<=16:
            raise ValueError('finite observation block required')
        if state.shape!=(111,) or state.dtype!=np.float64 or not state.flags.c_contiguous or not state.flags.writeable:
            raise ValueError('owned contiguous live state required')
        if not isinstance(hz,int) or not 1<=hz<=2**31-1:raise ValueError('invalid clock')
        self.prepare_step()
        status=self.lib.ft_step(self.context,self.work,C.byref(self._step_work),self.source,first,
            ptr(rows),len(rows),hz,int(query),*self._step_arguments,ptr(state))
        self.check(status)
        if query:self._step_cache=(state,first+len(rows),self._step_work.query_status)
        return int(self._step_work.ticks)
    def prepare_step(self):
        """Allocate before campaign storage accounting and timed advances."""
        if self._step_work is None:
            class StepWork(C.Structure):
                _fields_=[('state',C.c_double*111),('out',C.c_double*307),('ticks',C.c_uint64),('query_status',C.c_int)]
            self.lib.ft_step_work_bytes.restype=C.c_size_t
            if C.sizeof(StepWork)!=self.lib.ft_step_work_bytes():raise ValueError('fused workspace ABI mismatch')
            self._step_work=StepWork();self._step_output=np.ctypeslib.as_array(self._step_work.out)
            self.lib.ft_step.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint64,C.c_uint64,DP,C.c_size_t,C.c_uint64,C.c_int]+[DP]*9
            f=self.field
            # Only immutable per-instance calibration/prior/projection arrays.
            self._step_arguments=tuple(ptr(a) for a in (self.mean,self.L,f.center,f.halfwidth,f.cal,f.rates,f.p1,f.p2))
    def projection(self,x,row):
        x=array(x,(16,));row=array(row,(82,));out=np.empty(17);f=self.field
        self.check(self.lib.ft_projection(self.work,ptr(x),ptr(row),ptr(f.center),ptr(f.halfwidth),ptr(out)))
        return out[16],out[:16]
    def snapshot(self):return np.frombuffer(bytes(self.context),dtype=np.uint8).copy()
    def restore(self,data,count):
        self._step_cache=None
        data=np.asarray(data)
        if data.dtype!=np.uint8 or data.shape!=(C.sizeof(self.context),):raise ValueError('native checkpoint shape')
        old=bytes(self.context);C.memmove(self.context,data.tobytes(),len(data))
        try:
            if self.count!=count:raise ValueError('native checkpoint chronology')
        except ValueError:
            C.memmove(self.context,old,len(old));raise
    def storage(self):return dict(native_context_B=C.sizeof(self.context),native_explicit_workspace_B=C.sizeof(self.work),
                                  native_fused_workspace_B=C.sizeof(self._step_work) if self._step_work is not None else 0,
                                  dense_derivative_cache_B=0,scope='C tangent only; borrowed prior/field, caller rows/output and stack excluded')
