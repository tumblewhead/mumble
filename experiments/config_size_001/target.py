"""Separate physical-input lane. Historical harness is preserved unchanged."""
import argparse,json
from pathlib import Path
from unittest.mock import patch
from .build import generate,VARIANTS
from experiments.sram_size_001 import measure

def run(out,variant,lane):
 original=measure.subprocess.run
 def invoke(cmd,*args,**kwargs):
  if cmd[0]=='arm-none-eabi-gcc' and lane=='physical':
   path=next(Path(x) for x in cmd if x.endswith('/probe.c'))
   s=path.read_text().replace('volatile double sample;','volatile double samples[5];\nvolatile double readout[2];')
   old='bank.input[0]=.02;bank.input[1]=sample;bank.input[2]=25;bank.input[3]=3.8;bank.input[4]=.002;'
   assert s.count(old)==1;s=s.replace(old,'for(unsigned k=0;k<5;k++)bank.input[k]=samples[k];')
   old='for(unsigned j=0;j<16;j++)status|=scalar(&bank.solver,j,bank.result,bank.result+1);'
   assert s.count(old)==1;s=s.replace(old,'for(unsigned j=0;j<16;j++){status|=scalar(&bank.solver,j,bank.result,bank.result+1);readout[0]=bank.result[0];readout[1]=bank.result[1];}')
   path.write_text(s)
  return original(cmd,*args,**kwargs)
 def gen(d,*args,**kw):return generate(d,variant,48)
 with patch.object(measure,'generate',side_effect=gen),patch.object(measure.subprocess,'run',side_effect=invoke):measure.run(out,48)
 p=Path(out)/'measurement.json';d=json.loads(p.read_text());d.update(variant=variant,lane=lane);p.write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--variant',choices=VARIANTS,default='baseline');p.add_argument('--lane',choices=('legacy','physical'),default='physical');a=p.parse_args();run(a.out,a.variant,a.lane)
