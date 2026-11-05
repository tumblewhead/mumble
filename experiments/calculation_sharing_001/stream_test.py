"""Paired causal stream control; truth goes only to error metrics, never fit."""
import argparse,json,math
from pathlib import Path
import numpy as np
from .build import build
from .qualify import make
from experiments.bank_memory_001.field import SmallField
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.distinct_backend import prepare_distinct
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_uncertainty_audit_001.conditional_packet import partition

def run(campaign,out,hours):
 campaign=Path(campaign).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 config=json.loads((campaign/'calibration.json').read_text());settings=json.loads((campaign/'campaign_plan.json').read_text())['configuration'];mean,L=prior(config);center=partition(mean)[1]
 rc,h,m=prepare_distinct(out);bins={v:build(out/'host',v,48)for v in ('baseline','rc_tau_support')};result=[]
 (out/'source.json').write_text(json.dumps(dict(campaign=str(campaign),history_bits=48,hours=hours),indent=2)+'\n')
 for case in sorted(campaign.glob('case_[0-9][0-9][0-9][0-9]')):
  scenario=json.loads((case/'scenario.json').read_text());report=json.loads((case/'result.json').read_text());stream=StimulusStream(config,scenario['cell_definition'],report['scenario'],settings)
  arms={};stats={};last={}
  for v in bins:
   f=SmallField(config,center,rc.resolve(),h.resolve(),m,'paired-stream',out/'qr',3,'float64');n=make(f,mean,L,bins[v]);n.initialize(np.zeros(16));arms[v]=n;last[v]=n.query()
   stats[v]=dict(accepted=0,rejected=0,Q_3sd_misses=0,SOC_3sd_misses=0,max_chart_delta=0.,max_relative_sd_delta=0.)
  interval=math.ceil(settings['field_refresh_seconds']*stream.rate/16)*16;total=int(hours*3600*stream.rate)//16*16
  zero_sd_mismatches=0
  for first in range(0,total,16):
   obs,truth,_=stream.read(16)
   if len(obs)!=16:raise ValueError('plant stream stopped')
   for v,n in arms.items():
    n.advance(first,obs)
    if n.count%interval==0:
     fit=n.fit(last[v]['w']);accepted=fit['diagnostic']['stop'] in ('gradient','GN_decrement_at_cost_roundoff');stats[v]['accepted' if accepted else 'rejected']+=1
     n.initialize(fit['w'] if accepted else n.anchor.copy())
    last[v]=n.query();q=last[v];sd=np.linalg.norm(q['endpoint_root'],axis=1)
    stats[v]['Q_3sd_misses']+=int(abs(q['end'][5]-np.log(truth[-1,5]))>3*sd[5]);stats[v]['SOC_3sd_misses']+=int(abs(q['end'][0]-truth[-1,0])>3*sd[0])
   a=last['baseline'];b=last['rc_tau_support'];s=stats['rc_tau_support']
   sa=np.linalg.norm(a['endpoint_root'],axis=1);sb=np.linalg.norm(b['endpoint_root'],axis=1)
   zero_sd_mismatches+=int(np.any((sa==0)!=(sb==0)))
   ratio=np.divide(sb,sa,out=np.ones_like(sa),where=sa!=0)
   if not np.isfinite(ratio).all():raise ValueError('nonfinite uncertainty ratio')
   s['max_chart_delta']=max(s['max_chart_delta'],float(max(abs(a['end']-b['end']))))
   s['max_relative_sd_delta']=max(s['max_relative_sd_delta'],float(max(abs(ratio-1))))
  stats['rc_tau_support']['zero_sd_mismatches']=zero_sd_mismatches
  result.append(dict(case=case.name,records=total,hours=total/stream.rate/3600,stats=stats,final={v:dict(end=q['end'].tolist(),sd=np.linalg.norm(q['endpoint_root'],axis=1).tolist())for v,q in last.items()}));(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(case.name,stats,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);p.add_argument('--out',required=True);p.add_argument('--hours',type=float,default=4);a=p.parse_args();run(a.campaign,a.out,a.hours)
