"""Extract small source-bound receipts; never rewrite campaign evidence."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.telemetry import PARAMETERS,physical

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def summarize(root):
 p=root/'summary.json';d=json.loads(p.read_text());plan=json.loads((root/'campaign_plan.json').read_text())
 config=json.loads((root/'calibration.json').read_text());out=dict(directory=str(root),summary_sha256=sha(p),status=d['status'],cases=[])
 out['configuration']={k:v for k,v in plan['configuration'].items() if k in ['hours','seeds','load_seeds','noise_v','cells','loads','sample_rate_hz','bank_rank','bank_precision','bank_center','recording','history']}
 for name in ['manifest.json','campaign_plan.json']:
  if (root/name).exists():out[name+'_sha256']=sha(root/name)
 for c in d['cases']:
  case=root/c['directory'];truth=json.loads((case/'scenario.json').read_text())['cell_definition']['parameters']
  row=dict(directory=c['directory'],scenario=c['scenario'],result_sha256=sha(case/'result.json'),arms={})
  for k,v in c['arms'].items():
   info=dict(status=v['status'],metrics=v['all'],refresh=v.get('field_history'),storage=v.get('storage'))
   message=case/(k+'_message.npy')
   if message.exists():
    ref,_=physical(np.load(message)[:16],config,25)
    info['final_parameter_error_percent']={n:float(100*(ref[i]/truth[n]-1)) for i,n in enumerate(PARAMETERS)}
   row['arms'][k]=info
  out['cases'].append(row)
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.exists():raise FileExistsError(a.out)
 a.out.write_text(json.dumps(dict(scope='Paired synthetic stationary desktop evidence; correlated outputs are not independent coverage trials. No lifetime/MCU acceptance.',runs=[summarize(r) for r in a.runs]),indent=2)+'\n')
