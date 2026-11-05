from pathlib import Path
import re
from experiments.model_metadata_001.build import generate as base
VARIANTS=('baseline','pointer_block','inline_block')
def generate(directory,variant='pointer_block',history_bits=48):
 p=base(directory,'compact',history_bits);s=p.read_text()
 if variant!='baseline':
  assert variant in VARIANTS
  decl='const double *mean,*scale,*center,*projected_map;'
  config=('const double *mean,*scale,*center,*projected_map;' if variant=='pointer_block' else 'double mean[16],scale[16],center[5],projected_map[39];')
  old='typedef struct {\n '+decl
  assert s.count(old)==1;s=s.replace(old,'typedef struct { '+config+' } fixed_config;\ntypedef struct {\n const fixed_config *config;')
  stream_path=Path(__file__).resolve().parents[2]/'experiments/sram_size_001/stream.c'
  token='#include \"'+str(stream_path)+'\"';assert s.count(token)==1;s=s.replace(token,stream_path.read_text())
  for name in ('mean','scale','center','projected_map'):
   s=s.replace('m->'+name,'m->config->'+name).replace('c->m.'+name,'c->m.config->'+name)
  old='if(!c||!m||';assert s.count(old)==1;s=s.replace(old,'if(!c||!m||!m->config||')
  if variant=='inline_block':
   for name in ('mean','scale','center','projected_map'):s=s.replace('!m->config->'+name+'||','')
 p.write_text(s);return p

def adapt_probe(path,variant,prefix):
 s=path.read_text();old=','.join(prefix+'_'+n for n in ('mean','scale','center','P','P','P'))+',1.,'
 assert s.count(old)==1
 if variant=='baseline':s=s.replace(old,','.join(prefix+'_'+n for n in ('mean','scale','center','P'))+',')
 else:
  if variant=='pointer_block':values=','.join(prefix+'_'+n for n in ('mean','scale','center','P'))
  else:
   h=(path.parent/('config.h' if prefix=='config' else 'fixture.h')).read_text()
   values=','.join(re.search(r'\b'+prefix+'_'+n+r'\[\d+\]=({[^}]*})',h)[1] for n in ('mean','scale','center','P'))
  marker='#include "'+('config.h' if prefix=='config' else 'fixture.h')+'"'
  assert s.count(marker)==1;s=s.replace(marker,marker+'\nstatic const fixed_config configuration={'+values+'};')
  s=s.replace(old,'&configuration,')
 path.write_text(s)
