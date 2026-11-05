from experiments.config_reference_001.build import generate as base, adapt_probe as base_probe
VARIANTS=('baseline','contiguous')
def generate(directory,variant='contiguous',history_bits=48):
 assert variant in VARIANTS
 p=base(directory,'pointer_block',history_bits);s=p.read_text()
 if variant=='contiguous':
  old='const double *legacy,*free_rc,*forced_rc;'
  assert s.count(old)==1;s=s.replace(old,'double *response;')
  old='!m->legacy||!m->free_rc||!m->forced_rc';assert s.count(old)==1;s=s.replace(old,'!m->response')
  for prefix in ('m->','c->m.'):
   for field,offset in [('legacy',0),('free_rc',15),('forced_rc',54)]:
    s=s.replace(prefix+field,'('+prefix+'response'+('+'+str(offset) if offset else '')+')')
 p.write_text(s);return p

def adapt_probe(path,variant,prefix):
 base_probe(path,'pointer_block',prefix)
 if variant=='contiguous':
  s=path.read_text();old='bank.response,bank.response+15,bank.response+54';assert s.count(old)==1
  path.write_text(s.replace(old,'bank.response'))
