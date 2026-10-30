"""Desktop adapters only. The compiled estimator receives V/I/T, sigma and public prior."""
import ctypes as C
import json
from pathlib import Path
import numpy as np
from experiments.foster_feedback_001.estimator import prior
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DP=C.POINTER(C.c_double)
UP=C.POINTER(C.c_ubyte)
class Message(C.Structure):
    _fields_=[('mean',C.c_double*16),('root',C.c_double*256),('logZ',C.c_double)]
class Config(C.Structure):
    _fields_=[('cal',C.c_double*14),('rounds',C.c_int),('fractions',C.c_int),('encoding',C.c_int),('gradient_tol',C.c_double),('step_tol',C.c_double)]
class Physical(C.Structure):
    _fields_=[('v',C.c_double*16),('J',C.c_double*256),('end',C.c_double*16),('F',C.c_double*256)]
class Profile(C.Structure):
    _fields_=[(n,C.c_uint64) for n in ('model_calls','model_success','fit_evaluations','rounds','trials','tokens')]+[('stops',C.c_uint64*4)]+[(n,C.c_double) for n in ('model_s','before_s','fit_s','token_s','history_s','domain_s')]
def ptr(a):return a.ctypes.data_as(DP)
def message(m,L,z=0):return Message((C.c_double*16)(*m),(C.c_double*256)(*np.asarray(L).ravel()),z)
def config(encoding=8):
    cfg=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());num=cfg['numerical']
    c=Config((C.c_double*14)(cfg['reference_temperature_K'],cfg['ocv_intercept_V'],cfg['ocv_slope_V_per_SOC'],*cfg['arrhenius_A_K']),num['max_rounds'],num['fractions'],encoding,num['gradient_inf_tolerance'],num['latent_step_tolerance'])
    return cfg,c,message(*prior(cfg))
def library(path=None):
    lib=C.CDLL(str(path or HERE/'build/baseline.so'))
    lib.fb_context_bytes.restype=C.c_size_t;lib.fb_profile_bytes.restype=C.c_size_t
    lib.fb_init.argtypes=[C.c_void_p,C.POINTER(Config),C.POINTER(Message),C.c_uint64]
    lib.fb_offer.argtypes=[C.c_void_p,C.c_uint64,DP];lib.fb_flush.argtypes=[C.c_void_p]
    lib.fb_get_message.argtypes=[C.c_void_p,DP];lib.fb_get_profile.argtypes=[C.c_void_p,C.POINTER(Profile)]
    lib.fb_replay.argtypes=[C.c_void_p,DP,C.c_size_t,DP,C.c_size_t,C.POINTER(C.c_size_t)]
    lib.fb_history.argtypes=[C.POINTER(Message),UP,C.c_size_t,C.POINTER(Message)]
    lib.fb_token.argtypes=[DP,C.POINTER(Physical),DP,C.c_int,C.c_int,UP]
    lib.fb_solve.argtypes=[DP,DP];lib.fb_cholesky.argtypes=[DP];lib.fb_qr.argtypes=[DP]
    return lib
class Baseline:
    def __init__(self,lib=None,encoding=8,initial=None,settings=None):
        self.lib=lib or library();self.cfg,self.c,self.m=config(encoding)
        if initial is not None:self.m=message(*initial)
        if settings:
            for k,v in settings.items():setattr(self.c,k,v)
        self.context=C.create_string_buffer(self.lib.fb_context_bytes())
        r=self.lib.fb_init(self.context,C.byref(self.c),C.byref(self.m),123)
        if r:raise ValueError(('init',r))
    def snapshot(self):
        a=np.empty(273);self.lib.fb_get_message(self.context,ptr(a));return a
    def offer(self,index,row):return self.lib.fb_offer(self.context,index,ptr(np.asarray(row,dtype=float)))
    def flush(self):return self.lib.fb_flush(self.context)
    def replay(self,obs):
        obs=np.ascontiguousarray(obs,dtype=float);out=np.empty(((len(obs)+15)//16+1,36));written=C.c_size_t()
        r=self.lib.fb_replay(self.context,ptr(obs),len(obs),ptr(out),len(out),C.byref(written))
        return r,out[:written.value]
    def profile(self):
        p=Profile();self.lib.fb_get_profile(self.context,C.byref(p))
        return {k:list(getattr(p,k)) if k=='stops' else getattr(p,k) for k,_ in p._fields_}
