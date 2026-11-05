"""Collect compact evidence; raw builds remain ignored."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'provenance/calculation_sharing_001'
def record(p):
 p=Path(p);return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def run():
 measurements={};artifacts=[]
 for p in sorted(HERE.glob('target*/measurement.json')):
  d=json.loads(p.read_text());r=d['results'][0];measurements[d['sharing_variant']]=dict(static_B=r['allocated_sections_B'],text_B=r['sections']['.text'],alignment_B=r['alignment_gaps_B'],with_1024_stack_B=r['with_1024_stack_B'],measurement=record(p),elf_sha256=r['sha256']);artifacts.append(record(p.parent/'tiny_cardinal/core.c'));artifacts.append(record(p.parent/'tiny_cardinal/shared_math.h'))
 stacks={}
 for name in ('stack_baseline001','stack_candidate001','stack_tau001','stack_tau_support001'):
  p=HERE/name/'measurement.json';r=json.loads(p.read_text());stacks[r['sharing_variant']]=dict(measurement=record(p),output=r['output'],returncode=r['returncode']);artifacts.append(record(p.parent/'core.c'));artifacts.append(record(p.parent/'probe.elf'))
 q=HERE/'qualification_tau001/results.json';stream=HERE/'stream_tau1h001/results.json';artifacts.extend((record(q),record(stream),record(HERE/'stream_tau1h001/source.json')))
 d=dict(schema='calculation_sharing_receipt_v1',baseline_revision='6c750cf',branch='experiment/calculation-sharing-001',selected='rc_tau_support',status='isolated_measured_candidate_not_promoted',static_saving_B=40,observed_stack_increase_B=24,static_plus_observed_stack_saving_B=16,static_plus_provisional_1024_stack_B=26056,variants=measurements,stack_witnesses=stacks,direct_controls=json.loads(q.read_text()),paired_streams=json.loads(stream.read_text()),source={p.name:record(p) for p in sorted(HERE.glob('*.py'))},documentation=record(HERE/'README.md'),artifacts=artifacts,reviews=['provenance/calculation_sharing_001/review_r1.json','provenance/calculation_sharing_001/review_r2.json','provenance/calculation_sharing_001/review_r3.json'],limits=['Stack is observed, not worst-case bounded.','Mainline and campaign defaults unchanged.','M23 code on M33 emulator is not a target timing benchmark.','Three additional exp evaluations per support check.','One-hour tests do not establish long-duration coverage or precision.','Prior failed variants and initial overly strict lifecycle test preserved.'])
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'receipt.json').write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':run()
