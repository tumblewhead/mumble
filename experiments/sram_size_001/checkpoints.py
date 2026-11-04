"""Refit immutable retained evidence under four math/map controls. Not replay.
Uses recorded priors/centres and starting anchor; no simulator truth in objectives.
"""
import argparse,json,hashlib,tempfile
from pathlib import Path
import numpy as np
from experiments.bank_memory_001.field import SmallField
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.distinct_backend import prepare_distinct
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from .native import Native

def run(campaign,out,stride=6):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 campaign=Path(campaign).resolve();config=json.loads((campaign/'calibration.json').read_text());mean,root=prior(config);center=partition(mean)[1]
 rc,h,m=prepare_distinct(out);results=[]
 for case in sorted(campaign.glob('case_[0-9][0-9][0-9][0-9]')):
  entries=json.loads((case/'checkpoints/index.json').read_text())['checkpoints'];entries=entries[::stride]+([entries[-1]] if entries[-1] not in entries[::stride] else [])
  for entry in entries:
   path=case/'checkpoints'/entry['file'];sha=hashlib.sha256(path.read_bytes()).hexdigest();assert sha==entry['sha256']
   with np.load(path,allow_pickle=False) as a:
    key='rowwise_bank__';md=json.loads(a[key+'metadata'].tobytes());common={k:a[key+k].copy() for k in ('root','state','free','forced','projection')}
   controls={}
   for math,map in [('libm','spline'),('tiny','spline'),('libm','cardinal'),('tiny','cardinal')]:
    f=SmallField(config,center,rc.resolve(),h.resolve(),m,'common-retained-evidence',out/'qr',3,'float64')
    f.root=common['root'];f._commit(common['state'].copy(),common['free'].copy(),common['forced'].copy(),md['count'],md['noise'])
    n=Native(f,mean,root,out/'native',math,map,True)
    fit=n.fit(common['projection'][:16]);n.initialize(fit['w']);q=n.query()
    controls[math+'_'+map]=dict(w=fit['w'].tolist(),end=q['end'].tolist(),sd=np.linalg.norm(q['endpoint_root'],axis=1).tolist(),fit=fit['diagnostic'])
   ref=controls['libm_spline'];base=np.array(ref['end']);sd=np.array(ref['sd'])
   for control in controls.values():
    delta=np.array(control['end'])-base
    control['max_chart_shift']=float(max(abs(delta)));control['max_shift_reference_sd']=float(max(abs(delta)/sd))
    control['Q_relative_shift']=float(np.expm1(delta[5]));control['SOC_shift_pp']=float(100*delta[0]);control['max_relative_sd_shift']=float(max(abs(np.array(control['sd'])/sd-1)))
   record=dict(case=case.name,sequence=entry['sequence'],sha256=sha,controls=controls);results.append(record)
   (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
   print(case.name,entry['sequence'],controls['tiny_cardinal']['max_shift_reference_sd'],flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);p.add_argument('--out',required=True);p.add_argument('--stride',type=int,default=6);a=p.parse_args();run(a.campaign,a.out,a.stride)
