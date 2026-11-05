import argparse,json
from pathlib import Path
from unittest.mock import patch
from experiments.sram_size_001 import stack
from .build import generate,VARIANTS,adapt_probe

def run(out,variant):
 original=stack.subprocess.run
 def invoke(cmd,*args,**kwargs):
  if cmd[0]=='arm-none-eabi-gcc':
   p=next(Path(x) for x in cmd if x.endswith('/probe.c'));adapt_probe(p,variant,'fixture')
  return original(cmd,*args,**kwargs)
 def gen(d,*args,**kwargs):return generate(d,variant,48)
 with patch.object(stack,'generate',side_effect=gen),patch.object(stack.subprocess,'run',side_effect=invoke):stack.run(out,48)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--variant',choices=VARIANTS,required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.out,a.variant)
