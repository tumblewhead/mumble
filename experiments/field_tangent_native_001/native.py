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
    binary=destination/'tangent.so'
    subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror',
                    '-pedantic','-fPIC','-fstack-usage','-shared',str(destination/'kernel.c'),'-lm','-o',str(binary)],check=True)
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
    def check(self,status):
        if status:raise ValueError('native tangent status '+str(status))
    def initialize(self,w):
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
        if source is not None and source!=self.field.source:raise ValueError('native tangent source mismatch')
        if not isinstance(first,(int,np.integer)) or first<0:raise ValueError('native tangent chronology')
        rows=np.asarray(rows);rows=array(rows,(len(rows),82));f=self.field
        self.check(self.lib.ft_update(self.context,self.work,self.source,first,ptr(rows),len(rows),ptr(self.mean),ptr(self.L),ptr(f.center),ptr(f.halfwidth)))
    def query(self,state=None,count=None):
        f=self.field;state=array(f.state if state is None else state,(111,));out=np.empty(307)
        self.check(self.lib.ft_query(self.context,self.work,f.count if count is None else count,ptr(self.mean),ptr(self.L),
                                    ptr(f.center),ptr(f.halfwidth),ptr(state),ptr(f.p1),ptr(f.p2),ptr(out)))
        return dict(w=out[:16].copy(),x=out[16:32].copy(),end=out[32:48].copy(),endpoint_root=out[48:304].reshape(16,16).copy(),
                    linearized_cost=float(out[304]),logdet_precision=float(out[305]),anchor_displacement_GN=float(out[306]))
    def projection(self,x,row):
        x=array(x,(16,));row=array(row,(82,));out=np.empty(17);f=self.field
        self.check(self.lib.ft_projection(self.work,ptr(x),ptr(row),ptr(f.center),ptr(f.halfwidth),ptr(out)))
        return out[16],out[:16]
    def snapshot(self):return np.frombuffer(bytes(self.context),dtype=np.uint8).copy()
    def restore(self,data,count):
        data=np.asarray(data)
        if data.dtype!=np.uint8 or data.shape!=(C.sizeof(self.context),):raise ValueError('native checkpoint shape')
        old=bytes(self.context);C.memmove(self.context,data.tobytes(),len(data))
        try:
            if self.count!=count:raise ValueError('native checkpoint chronology')
        except ValueError:
            C.memmove(self.context,old,len(old));raise
    def storage(self):return dict(native_context_B=C.sizeof(self.context),native_explicit_workspace_B=C.sizeof(self.work),
                                  dense_derivative_cache_B=0,scope='C tangent only; borrowed prior/field, caller rows/output and stack excluded')
