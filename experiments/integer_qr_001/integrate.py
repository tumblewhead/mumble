"""Size/execution probe only: float response feeding Q16 integer history."""
import argparse,json
from pathlib import Path
from unittest.mock import patch
from experiments.capability_profiles_001 import measure
from experiments.capability_profiles_001.build import generate as base
HERE=Path(__file__).resolve().parent

def run(out,kind,execute=False,fraction_bits=12):
 def generate(d,variant,arithmetic):
  p=base(d,variant,'float');d=Path(d)
  (d/'integer_qr.h').write_text((HERE/'kernel.h').read_text())
  (d/'shared_history.h').write_text('''#define CORDIC_KIND @KIND@
#include "integer_qr.h"
#include <math.h>
typedef int32_t history_store;
static double history_get(const history_store*R,unsigned j){return (double)R[j]/@SCALE@;}
static int history_insert(history_store*R,int n,float*x){
 if(n<1||n>34)return -1;
 int32_t row[34];
 for(int j=0;j<n;j++){
  if(!isfinite(x[j])||fabsf(x[j])>@LIMIT@.f)return -1;
  float v=x[j]*@SCALE@.f;int32_t q=(int32_t)v;float f=v-(float)q;if(f>=.5f)q++;else if(f<=-.5f)q--;row[j]=q;
 }
 return iq_insert(R,(unsigned)n,row);
}
'''.replace('@KIND@',str(kind)).replace('@SCALE@',str(1<<fraction_bits)).replace('@LIMIT@',str(1<<(29-fraction_bits))))
  return p
 with patch.object(measure,'generate',side_effect=generate):measure.run(out,'collector',execute,'float','local')
 p=Path(out)/'measurement.json';r=json.loads(p.read_text());r['arithmetic']='float_response_fixed_integer_history';r['fraction_bits']=fraction_bits;r['kernel']='cordic' if kind else 'digit';r['qualification']='bounded size probe only; no complete campaign or rescaling';p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--kind',choices=('digit','cordic'),required=True);p.add_argument('--execute',action='store_true');p.add_argument('--fraction-bits',type=int,choices=(12,16),default=12);a=p.parse_args();run(a.out,int(a.kind=='cordic'),a.execute,a.fraction_bits)
