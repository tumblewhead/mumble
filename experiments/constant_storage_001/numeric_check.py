from pathlib import Path
import argparse,json,subprocess,re,hashlib
import numpy as np

def run(out):
 root=Path(__file__).resolve().parent;out=Path(out);out.mkdir(parents=True,exist_ok=False);arrays={}
 for v in ('byte_indices','f32_coefficients'):
  d=root/v/'tiny_cardinal';s=(root/'numeric.c.in').read_text().replace('@CORE@',str(d/'core.c')).replace('@CONFIG@',str(d/'config.h'));p=out/(v+'.c');p.write_text(s);exe=p.with_suffix('')
  subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(p),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe.resolve())],capture_output=True,timeout=120);assert r.returncode==0 and not r.stderr,(v,r.returncode,r.stderr)
  arrays[v]=np.frombuffer(r.stdout,dtype='<f8');assert np.isfinite(arrays[v]).all();np.save(out/(v+'.npy'),arrays[v])
 a,b=arrays.values();assert a.shape==b.shape;ns=257*3*2;nf=64*34*17
 sa,sb=a[:ns].reshape(257,3,2),b[:ns].reshape(257,3,2)
 fa,fb=a[ns:ns+nf].reshape(64,34,17),b[ns:ns+nf].reshape(64,34,17)
 ta,tb=a[ns+nf:-93].reshape(32,53),b[ns+nf:-93].reshape(32,53)
 qa,qb=ta[:,2:50].reshape(32,16,3),tb[:,2:50].reshape(32,16,3)
 status_equal=np.array_equal(ta[:,:2],tb[:,:2]) and np.array_equal(qa[:,:,0],qb[:,:,0]);good=(qa[:,:,0]==0)&(qb[:,:,0]==0)
 value_delta=np.where(good,abs(qa[:,:,1]-qb[:,:,1]),0);variance_delta=np.where(good,abs(qa[:,:,2]-qb[:,:,2]),0)
 # Mathematical rounding-only bounds for fixed-coefficient readouts, not total numerical/estimator error.
 text=(root/'byte_indices/tiny_cardinal/config.h').read_text()
 def values(name):return np.array([float.fromhex(x) for x in re.search(r'config_'+name+r'\[39\]=\{([^}]+)',text)[1].split(',')])
 P=values('P').reshape(3,13);V=values('V').reshape(13,3);dp=abs(P.astype('f4').astype('f8')-P);dv=abs(V.astype('f4').astype('f8')-V)
 B=dv@abs(P)+abs(V)@dp+dv@dp
 gamma=float(B.sum());gamma_u=float((B*np.arange(13)**2).sum())
 bounds={'composed_VP_abs_bound_per_sum_amplitude':gamma,'composed_VP_du_bound_per_sum_amplitude':gamma_u,'P_map_abs_per_coordinate':dp.sum(1).tolist(),'P_du_abs_per_coordinate':(dp*np.arange(13)**2).sum(1).tolist(),'V_abs_per_coordinate_per_max_state':dv.sum(0).tolist(),'assumptions':'|u|<=1;Chebyshev |T_j|<=1,|Tprime_j|<=j^2;fixed-coefficient rounding in exact arithmetic;not runtime roundoff or accumulated history bias'}
 result={'status':'measured_not_long_run_qualified','all_statuses_equal':bool(status_equal),'accepted_refits':{v:int(np.isin(t[:,0],[1,2]).sum())for v,t in zip(arrays,[ta,tb])},'successful_scalar_queries':int(good.sum()),'max_map_abs_delta':abs(sa-sb).max((0,1)).tolist(),'max_feature_value_delta':float(abs(fa[:,:,0]-fb[:,:,0]).max()),'max_feature_derivative_delta':float(abs(fa[:,:,1:]-fb[:,:,1:]).max()),'max_scalar_value_delta_per_coordinate':value_delta.max(0).tolist(),'max_scalar_variance_delta_per_coordinate':variance_delta.max(0).tolist(),'carried_response_exact':bool(np.array_equal(a[-93:],b[-93:])),'rounding_only_bounds':bounds,'stream_seconds':4096*.02,'scope':'synthetic numerical control at50Hz,not plant accuracy or calibrated coverage;32refits;P/Vbothrounded once;history48unchanged'}
 assert good.sum()>0
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
