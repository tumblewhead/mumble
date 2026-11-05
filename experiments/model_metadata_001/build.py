from experiments.config_size_001.build import generate as base
VARIANTS=('baseline','compact')
def generate(directory,variant='compact',history_bits=48):
 p=base(directory,'chart_finite',history_bits);s=p.read_text()
 if variant=='compact':
  old='const double *mean,*scale,*center,*map,*knots,*projected_map;\n double hu;'
  assert s.count(old)==1;s=s.replace(old,'const double *mean,*scale,*center,*projected_map;')
  for text in ('||!m->map','||!m->knots','||!(m->hu>0)'):
   assert s.count(text)==1;s=s.replace(text,'')
 elif variant!='baseline':raise ValueError(variant)
 p.write_text(s);return p
