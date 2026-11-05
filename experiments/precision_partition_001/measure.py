"""Measure mixed collector/SOC with local or conditional shared history."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from unittest.mock import patch
from experiments.capability_profiles_001 import measure as parent
from .build import generate,generate_gram,generate_storage

def run(out,profile,execute=False,history='local',kind='mixed'):
 if execute and history=='shared':raise ValueError('shared memory not mapped by execution witness')
 original=parent.subprocess.run;effective_command=[]
 def invoke(cmd,*args,**kw):
  if cmd[0]=='arm-none-eabi-gcc' and kind!='paired_gram':
   cmd=cmd+[str(parent.ROOT/'experiments/sram_size_001/soft_sub.c'),'-Wl,--wrap=__aeabi_dsub']
  if cmd[0]=='arm-none-eabi-gcc':effective_command[:]=cmd
  return original(cmd,*args,**kw)
 # Probe/config/input use float; generated history helpers retain double.
 with patch.object(parent,'generate',side_effect={'mixed':generate,'paired_gram':generate_gram,'storage_only':generate_storage}[kind]),patch.object(parent.subprocess,'run',side_effect=invoke):
  parent.run(out,profile,execute,'float',history)
 p=Path(out)/'measurement.json';s=json.loads(p.read_text());s['command']=effective_command;s['arithmetic']={'mixed':'float_response_double_QR_history48','paired_gram':'float_response_paired_Gram','storage_only':'double_arithmetic_float_response_storage_history48'}[kind];s['history_representation']='normal_matrix_float_pairs' if kind=='paired_gram' else 'sqrt48';s['source_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.h')};s['source_revision']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();p.write_text(json.dumps(s,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--profile',choices=('collector','soc'),default='collector');p.add_argument('--history',choices=('local','shared'),default='local');p.add_argument('--execute',action='store_true');p.add_argument('--kind',choices=('mixed','paired_gram','storage_only'),default='mixed');a=p.parse_args()
 if a.execute and a.history=='shared':p.error('shared memory not mapped by execution witness')
 run(a.out,a.profile,a.execute,a.history,a.kind)
