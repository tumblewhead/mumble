"""Paired M23 linked footprint, or target execution and observed stack."""
import argparse,json
from pathlib import Path
from unittest.mock import patch
from .build import generate,VARIANTS
from experiments.sram_size_001 import measure,stack

def run(out,variant,bits,execution=False):
 def gen(directory,*args,**kwargs):return generate(directory,variant,bits)
 module=stack if execution else measure
 with patch.object(module,'generate',side_effect=gen):module.run(out,bits)
 p=Path(out)/'measurement.json';d=json.loads(p.read_text());d.update(sharing_variant=variant,history_bits=bits);p.write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--variant',choices=VARIANTS,required=True);p.add_argument('--history-bits',type=int,choices=[48,64],default=48);p.add_argument('--execute',action='store_true');a=p.parse_args();run(a.out,a.variant,a.history_bits,a.execute)
