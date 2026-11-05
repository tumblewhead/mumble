"""Build full, collector, soc, or predictor Cortex-M23 capability images."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from . import measure
from experiments.coordinate_sharing_001.target import run as full
PROFILES=('full','collector','soc','predictor')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--profile',choices=(*PROFILES,'all'),required=True)
 p.add_argument('--out',type=Path,required=True)
 p.add_argument('--arithmetic',choices=('double','float'),default='double')
 p.add_argument('--history',choices=('local','shared'),default='local')
 p.add_argument('--execute',action='store_true')
 a=p.parse_args();profiles=PROFILES if a.profile=='all' else (a.profile,)
 if a.arithmetic=='float' and any(x not in ('collector','soc') for x in profiles):p.error('float trial supports collector and soc only')
 if 'full' in profiles and (a.history!='local' or a.execute):p.error('full supports local static build; use existing full stack qualification harness')
 if a.execute and a.history=='shared':p.error('shared address is a hardware contract, not mapped by this QEMU machine; use local execution')
 if a.arithmetic=='float':print('EXPERIMENTAL: direct binary32 history stalls under repeated evidence; not approved for sustained use.')
 a.out.mkdir(parents=True,exist_ok=False);records={}
 for profile in profiles:
  dest=a.out/profile
  if profile=='full':full(dest,'combined_scalar','physical')
  else:measure.run(dest,profile,a.execute,a.arithmetic,a.history)
  records[profile]=json.loads((dest/'measurement.json').read_text())
 (a.out/'profiles.json').write_text(json.dumps({'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=Path(__file__).resolve().parents[2]).strip(),'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.iterdir() if p.is_file() and p.suffix in ('.py','.h')},'profiles':records,'scope':'numerical capability builds; shared placement conditional; binary32 experimental'},indent=2)+'\n')
if __name__=='__main__':main()
