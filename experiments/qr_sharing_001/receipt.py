"""Small source-bound receipt; generated build and campaign data stay ignored."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;OUT=ROOT/'provenance/qr_sharing_001'
def artifact(p):return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def run():
 variants={};artifacts=[]
 for p in sorted(HERE.glob('target*/measurement.json')):
  m=json.loads(p.read_text());r=m['results'][0];variants[m['qr_variant']]=dict(static_B=r['allocated_sections_B'],text_B=r['sections']['.text'],with_provisional_1024_stack_B=r['with_1024_stack_B'],elf_sha256=r['sha256'],measurement=artifact(p))
  artifacts.extend(artifact(x) for x in (p.parent/'tiny_cardinal').iterdir() if x.suffix in ('.c','.h','.ld'))
 stacks={}
 for n in ('stack_baseline001','stack_loop001'):
  p=HERE/n/'measurement.json';m=json.loads(p.read_text());stacks[m['qr_variant']]=dict(measurement=artifact(p),output=m['output'],returncode=m['returncode']);artifacts.extend(artifact(x) for x in p.parent.iterdir() if x.suffix in ('.c','.h','.ld','.elf'))
 q=HERE/'qualification003/results.json';s=HERE/'stream1h001/results.json';artifacts.extend((artifact(q),artifact(s),artifact(HERE/'stream1h001/source.json')))
 d=dict(schema='qr_sharing_receipt_v1',baseline_revision='1f2f04c',branch='experiment/qr-sharing-001',selected='shared_loop',status='isolated_measured_candidate_not_promoted',static_saving_B=352,observed_stack_saving_B=32,static_plus_observed_stack_saving_B=384,static_plus_provisional_1024_stack_B=25704,variants=variants,stack_witnesses=stacks,direct_controls=json.loads(q.read_text()),paired_streams=json.loads(s.read_text()),source={p.name:artifact(p) for p in sorted(HERE.iterdir()) if p.suffix in ('.py','.h','.md')},artifacts=artifacts,reviews=['provenance/qr_sharing_001/review_r1.json'],limits=['Observed stack is not a worst-case bound','Mainline and campaign defaults unchanged','M23 instructions on M33 emulator are not target timing','Five independently tested rejected exceptional cases differ only in NaN sign/payload; finite components and status agree','One-hour50Hz controls do not qualify lifetime uncertainty or other sample rates'])
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'receipt.json').write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':run()
