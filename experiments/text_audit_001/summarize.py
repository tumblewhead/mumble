"""Group the reviewed census; persist only small evidence, never the build tree."""
from pathlib import Path
import json, argparse, hashlib

GROUPS = {
 'Model coefficients, support and endpoint transport': 'transported feature supported chart spline cardinal cheb dcheb emit',
 'Joint refit and scalar uncertainty': 'br_rebuild evaluate cost_at fit br_step br_variance estimate scalar append initialize',
 'Sample propagation': 'stream_row',
 'History and local QR storage/update': 'qr_insert history_insert history_put history_get index_of',
 'Ownership and interface checks': 'bind br_acquire br_release ingest stream_ingest',
 'Memory runtime': 'memmove memcpy memset',
 'Entry and integer runtime': 'reset fault __clzsi2 __gnu_thumb1_case_uqi',
}

def run(census, measurement, out):
 c=json.loads(Path(census).read_text()); m=json.loads(Path(measurement).read_text())['results'][0]
 # This report contains reviewed baseline-specific reconciliation and prose.
 expected_elf='c288374972a0308991fea97795345e24e8331439f21a1ac57265e2908725f1d8'
 if c['elf_sha256']!=expected_elf or m['sha256']!=expected_elf:
  raise ValueError('Summary is specific to the reviewed c2cb9fc baseline; audit and review new images separately.')
 groups={}; assigned=set()
 for name, words in GROUPS.items():
  names=words.split(); groups[name]={n:c['inline_leaf_bytes'][n] for n in names}; assigned.update(names)
 for n,b in c['inline_leaf_bytes'].items():
  if n in assigned:continue
  if n.startswith(('tm_', 'sm_')):g='Shared elementary math'
  elif n.startswith('__aeabi_') or n in ('__gedf2','__ledf2','__eqdf2','__wrap___aeabi_dsub'):g='Binary64 arithmetic runtime'
  else:raise ValueError('Unclassified '+n)
  groups.setdefault(g,{})[n]=b;assigned.add(n)
 assert assigned==set(c['inline_leaf_bytes'])
 rows=sorted((dict(group=g,bytes=sum(v.values()),functions=v) for g,v in groups.items()),key=lambda x:x['bytes'],reverse=True)
 assert sum(r['bytes'] for r in rows)==c['text_B']
 out=Path(out);out.mkdir(exist_ok=True,parents=True)
 evidence=dict(schema='text_audit_groups_v1',source_revision='c2cb9fc79181a8242af9b9a3b27e1a92c4650924',text_B=c['text_B'],groups=rows,allocated=m['allocated'],static_B=m['allocated_sections_B'],with_provisional_1024_stack_B=m['with_1024_stack_B'],compiler_binary64_physical_union_B=4746,compiler_binary64_plus_project_subtraction_wrapper_union_B=4762,limits=c['limits'],inputs={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (census,measurement)})
 (out/'groups.json').write_text(json.dumps(evidence,indent=2)+'\n')
 (out/'census.json').write_text(json.dumps(c,indent=2)+'\n')
 lines=['# Linked text census','', 'Source: `c2cb9fc`, Cortex-M23, procedural Horner math, 48-bit history storage. Arithmetic remains binary64.','', 'These are disjoint DWARF leaf attributions in a byte-identical diagnostic build. They include nearby literal pools/padding; they are not marginal removable costs.','', '| Functional group | Attributed bytes | Share of .text |','|---|---:|---:|']
 lines += [f"| {r['group']} | {r['bytes']:,} | {100*r['bytes']/c['text_B']:.1f}% |" for r in rows]
 lines += ['| **Total** | **17,100** | **100%** |','','The compiler-helper physical union is 4,746 B, or 4,762 B with the project subtraction wrapper. This differs from DWARF attribution because padding and symbol boundaries differ. Do not add the two views.','','## Individual functions','','| Innermost source function | Attributed bytes | Group |','|---|---:|---|']
 byname={n:r['group'] for r in rows for n in r['functions']}
 lines += [f'| `{n}` | {b:,} | {byname[n]} |' for n,b in c['inline_leaf_bytes'].items()]
 lines += ['','## Physical symbols','','`reset` occupies 3,856 B, but only 182 B is attributed to its own source body; most is inlined estimator work. Symbol size alone would misdirect the optimization.','','| Symbol / same-extent aliases | Nominal extent bytes |','|---|---:|---|'.replace('|---|---:|---|','|---|---:|')]
 lines += [f"| {' / '.join('`'+n+'`' for n in s['names'])} | {s['bytes']:,} |" for s in sorted(c['symbols'],key=lambda s:s['bytes'],reverse=True)]
 lines += ['','The symbol table has 16 B of overlapping extents and 20 B outside named function extents. Individual overlap ownership is conventional. The byte union, not the sum of extents, is authoritative.','','## Reconciliation','','17,608 B raw symbol-name extents − 512 B same-extent aliases − 16 B overlapping tail + 20 B unowned = **17,100 B**.','','Static total: 17,100 text + 1,016 constants + 6,928 BSS + 28 vectors = **25,072 B**. Adding the provisional 1,024 B stack allowance gives **26,096 B**. Platform integration and a worst-case stack bound remain open.','']
 (out/'CENSUS.md').write_text('\n'.join(lines))
 print([(r['group'],r['bytes']) for r in rows])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--census',required=True);p.add_argument('--measurement',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.census,a.measurement,a.out)
