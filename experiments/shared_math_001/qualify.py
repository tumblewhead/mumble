"""Common retained-history controls and target execution; no campaign promotion."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from unittest.mock import patch
import numpy as np
from .build import build,generate,ROOT
from experiments.sram_size_001 import native,stack
from experiments.bank_memory_001.field import SmallField
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.distinct_backend import prepare_distinct
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
KINDS=('baseline','bernstein','bernstein_small','procedural_horner')

def make(f,mean,L,d):
 with patch.object(native,'prepare',return_value=d):return native.Native(f,mean,L,d,'tiny','cardinal',True,64)

def run(campaign,out):
 campaign=Path(campaign).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 binaries={v:build(out/'host',v) for v in KINDS};config=json.loads((campaign/'calibration.json').read_text());mean,L=prior(config);center=partition(mean)[1]
 rc,h,m=prepare_distinct(out);results=[]
 for case in sorted(campaign.glob('case_[0-9][0-9][0-9][0-9]')):
  entries=json.loads((case/'checkpoints/index.json').read_text())['checkpoints'];selected=entries[::6]
  if entries[-1] not in selected:selected.append(entries[-1])
  for entry in selected:
   path=case/'checkpoints'/entry['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
   with np.load(path,allow_pickle=False) as a:
    key='rowwise_bank__';md=json.loads(a[key+'metadata'].tobytes());common={k:a[key+k].copy() for k in ('root','state','free','forced','projection')}
   controls={}
   for variant,d in binaries.items():
    f=SmallField(config,center,rc.resolve(),h.resolve(),m,'common-evidence',out/'qr',3,'float64');f.root=common['root'];f._commit(common['state'].copy(),common['free'].copy(),common['forced'].copy(),md['count'],md['noise'])
    n=make(f,mean,L,d);fit=n.fit(common['projection'][:16]);n.initialize(fit['w']);q=n.query()
    controls[variant]=dict(fit=fit['diagnostic'],end=q['end'].tolist(),sd=np.linalg.norm(q['endpoint_root'],axis=1).tolist())
   ref=controls['baseline'];end=np.array(ref['end']);sd=np.array(ref['sd'])
   for v in controls.values():v['max_shift_reference_sd']=float(max(abs(np.array(v['end'])-end)/sd));v['max_relative_sd_change']=float(max(abs(np.array(v['sd'])/sd-1)))
   results.append(dict(case=case.name,sequence=entry['sequence'],source_sha256=entry['sha256'],controls=controls))
   (out/'checkpoints.json').write_text(json.dumps(results,indent=2)+'\n');print(case.name,entry['sequence'],[(k,v['fit']['stop'],v['max_shift_reference_sd'])for k,v in controls.items()],flush=True)
 for variant in ('baseline','bernstein','procedural_horner'):
  def gen(directory,*args,**kwargs):return generate(directory,variant,args[3] if len(args)>3 else 64)
  with patch.object(stack,'generate',side_effect=gen):stack.run(out/'target'/variant,64)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.campaign,a.out)
