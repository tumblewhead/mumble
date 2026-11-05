"""Four build profiles; precision/placement trials are explicit, never defaults."""
from pathlib import Path
import re
import numpy as np
from experiments.two_processor_size_001.build import generate as split_generate, VARIANTS
from experiments.bank_memory_001.test_memory import Tests as Fixture
from experiments.sram_size_001.native import projected_coefficients

# Convert C floating literals (including hexadecimal configuration constants),
# skipping comments and strings. Unsuffixed literals would pull in double helpers.
TOKENS = re.compile(r'("(?:\\.|[^"\\])*"|/\*[\s\S]*?\*/|//[^\n]*|\b0[xX][0-9a-fA-F.]+[pP][+-]?\d+[fFlL]?|(?<![\w.])(?:\d+\.\d*|\.\d+|\d+[eE][+-]?\d+)(?:[eE][+-]?\d+)?[fFlL]?)')
def convert_float(source):
 source=re.sub(r'\bdouble\b','float',source)
 def token(m):
  t=m[0]
  return t if t.startswith(('"','/*','//')) or t[-1:] in 'fFlL' else t+'f'
 return TOKENS.sub(token,source)

def configuration(out):
 Fixture.setUpClass()
 try:
  f=Fixture();field=f.make(rank=3)
  arrays=dict(mean=f.mean,scale=np.diag(f.L),center=field.center,P=projected_coefficients(field),V=field.V,ocv=np.array([field.base.config['ocv_intercept_V'],field.base.config['ocv_slope_V_per_SOC']]))
 finally:Fixture.tearDownClass()
 (out/'config.h').write_text('\n'.join('static const double config_'+n+'['+str(a.size)+']={'+','.join(float(v).hex() for v in a.flat)+'};' for n,a in arrays.items())+'\n')

def generate(out,variant,arithmetic='double'):
 p=split_generate(out,variant)
 if arithmetic=='double':return p
 if variant not in ('collector','soc'):raise ValueError('binary32 trial supports collector and SOC only')
 p.write_text(convert_float(p.read_text()))
 h=Path(out)/'shared_history.h';s=h.read_text()
 start=s.index('typedef struct');end=s.index('/* Shared Givens')
 s='''/* Experimental binary32 factor, rounded on every update.
   This changes accumulation precision; no lifetime certificate. */
#include <stdint.h>
#include <string.h>
#include <math.h>
'''+'''typedef float history_store;
static float history_get(const history_store*p,unsigned i){return p[i];}
static void history_put(history_store*p,unsigned i,float x){p[i]=x;}
'''+s[end:]
 s=s.replace('six-byte IEEE high bits, rounded on every write','binary32, rounded on every write').replace('native double factor','native scalar factor')
 h.write_text(convert_float(s))
 (Path(out)/'shared_math.h').write_text((Path(__file__).with_name('math32.h')).read_text())
 return p
