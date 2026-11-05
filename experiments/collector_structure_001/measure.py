"""Separate runtime sharing, scratch reuse and lazy free-response trials."""
import argparse,json,hashlib
from pathlib import Path
from unittest.mock import patch
from experiments.integer_qr_001 import integrate
from experiments.capability_profiles_001 import measure as parent
HERE=Path(__file__).resolve().parent
VARIANTS=('baseline','sub','scratch','combined','lazy','lazy_limb')

def run(out,variant,execute=False):
 original=parent.subprocess.run;commands=[]
 def invoke(cmd,*args,**kw):
  if cmd[0]=='arm-none-eabi-gcc':
   d=Path(out).resolve();p=d/'core.c';s=p.read_text()
   if variant in ('scratch','combined','lazy','lazy_limb'):
    h=d/'shared_history.h';text=h.read_text().replace('static int history_insert(history_store*R,int n,float*x){','typedef union {float f[34];int32_t i[34];} row_scratch;\nstatic int history_insert(history_store*R,int n,row_scratch*w){\n float*x=w->f;')
    text=text.replace(' int32_t row[34];','')
    text=text.replace('row[j]=q;','w->i[j]=q;').replace('iq_insert(R,(unsigned)n,row)','iq_insert(R,(unsigned)n,w->i)');h.write_text(text)
    s=s.replace('float phi[34]','row_scratch row').replace('c->phi','c->row.f').replace('history_insert(history,34,c->row.f)','history_insert(history,34,&c->row)')
   if variant in ('lazy','lazy_limb'):
    # Clock in exact 2^-32 second ticks; reject unrepresentable input intervals.
    s=s.replace('unsigned valid;','unsigned valid;uint64_t ticks;')
    old='float *s=(float*)(c->m.response),*free=(float*)(c->m.response+15),*forced=(float*)(c->m.response+54);'
    assert old in s;s=s.replace(old,'float *s=c->m.response,*forced=c->m.response+15;')
    marker=' s[12]+=I*dt/3600;'
    s=s.replace(marker,''' float raw_ticks=dt*4294967296.f;
 uint64_t tick=(uint64_t)raw_ticks;
 if((float)tick!=raw_ticks||c->ticks>UINT64_MAX-tick)goto fail;
 c->ticks+=tick;
 float elapsed=(float)c->ticks/4294967296.f;
'''+marker)
    s=s.replace('free[ix]*=a;','float free_value=exp(-elapsed/(c->m.config->center[b]*exp(((int)j-6)*.25f)));')
    s=s.replace('free[ix]*V[','free_value*V[')
    if variant=='lazy_limb':
     s=s.replace('uint64_t ticks;','uint32_t seconds,fraction;')
     start=s.index(' float raw_ticks=');end=s.index(' s[12]+=',start)
     s=s[:start]+""" float raw_ticks=dt*4294967296.f;
 uint32_t whole=dt==1.f,part=whole?0:(uint32_t)raw_ticks;
 if(!whole&&(float)part!=raw_ticks)goto fail;
 uint32_t fraction=c->fraction+part,carry=whole+(fraction<c->fraction);
 if(c->seconds>UINT32_MAX-carry)goto fail;
 c->seconds+=carry;c->fraction=fraction;
 float elapsed=(float)c->seconds+(float)c->fraction/4294967296.f;
"""+s[end:]

    probe=d/'probe.c';t=probe.read_text().replace('response[93]','response[54]').replace('for(unsigned j=15;j<54;j++)bank.response[j]=1;','');probe.write_text(t)
   p.write_text(s)
   if variant in ('sub','combined','lazy','lazy_limb'):cmd=cmd+[str(HERE/'soft_sub32.c'),'-Wl,--wrap=__aeabi_fsub']
   commands.append(cmd)
  return original(cmd,*args,**kw)
 with patch.object(parent.subprocess,'run',side_effect=invoke):integrate.run(out,1,execute,12)
 p=Path(out)/'measurement.json';r=json.loads(p.read_text());r['variant']=variant;r['command']=commands[0];r['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.suffix in ('.py','.c')};p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--variant',choices=VARIANTS,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();run(a.out,a.variant,a.execute)
