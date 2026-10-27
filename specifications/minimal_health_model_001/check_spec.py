#!/usr/bin/env python3
"""Check specification identities and algebra, not an aging implementation."""
import hashlib
import json
import math
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def identity(p):
    return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def main():
    s=json.loads((HERE/'model.json').read_text())
    f=json.loads((HERE/'test_profiles.json').read_text())
    checks=[]
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    def close(a,b,name):check(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-14),name)
    mapping=s['state']['original_x_mapping']
    check(sorted(sum(mapping.values(),[]))==list(range(16)),'each original coordinate owned exactly once')
    check(len(s['state']['fast_order'])==5 and len(s['state']['health_order'])==2 and len(s['state']['static_order'])==9,'five fast/two health/nine static')
    for name,b in s['initial_prior']['source_bindings'].items():
        check(identity(ROOT/name)==b,'preserved source '+name)
    text=(ROOT/'experiments/live_anchor_integration_001/public_contract.c').read_text()
    limits={}
    for key in ('lower','upper'):
        values=re.search(r'const double ch_'+key+r'\[CH_DIM\] = \{([^}]+)\}',text).group(1)
        limits[key]=[float(v.strip()) for v in values.split(',') if v.strip()]
    for name,i in [('log_Q_Ah',5),('R0_ohm',6)]:
        check(s['state']['supports'][name]==[limits['lower'][i],limits['upper'][i]],'original health support '+name)
    for name,v in f['profiles'].items():
        check(len(v)==8 and all(math.isfinite(x) for x in v),'profile dimensions '+name)
        check(all(x>=0 for x in v[4:]),'nonnegative diffusion '+name)
    check(all(v==0 for v in f['profiles']['stationary']),'zero-drift identity profile')
    e=f['exposure_algebra_fixture'];D=e['calendar_days'];A=e['absolute_throughput_Ah']
    v=f['profiles']['assumed_trend_fixture']
    close(v[0]*D+v[1]*A,e['mean_logQ_increment'],'logQ mean exposure units')
    close(v[2]*D+v[3]*A,e['mean_R0_increment_ohm'],'R0 mean exposure units')
    close(v[4]**2*D+v[5]**2*A,e['variance_logQ'],'logQ variance exposure units')
    close(v[6]**2*D+v[7]**2*A,e['variance_R0_ohm2'],'R0 variance exposure units')
    for i,c in enumerate(f['charge_fixtures']):
        z=c['z_before'];Q=c['Q_before_Ah'];Qn=c['Q_next_Ah'];dq=c['current_A']*c['dt_s']/3600
        znew=z-dq/Qn;avail=z*(Qn-Q);qnew=z*Qn-dq
        close(znew,c['z_next'],f'SOC fixture{i}')
        close(qnew,c['q_next_Ah'],f'charge fixture{i}')
        close(avail,c['delta_q_availability_Ah'],f'availability fixture{i}')
        close(qnew-z*Q,avail-dq,f'explicit charge balance fixture{i}')
    check(s['inference_semantics']['selected']=='Bayesian current-state marginalization, not profile likelihood.','marginal target selected')
    check(s['deployment']['working_history']=='SRAM_only' and s['deployment']['complete_subsystem_target_bytes']==10240,'deployment contract')
    result={'status':'passed_specification_consistency_checks','checks':len(checks),'check_names':checks,
        'model':identity(HERE/'model.json'),'fixtures':identity(HERE/'test_profiles.json'),
        'checker':identity(Path(__file__)),'model_kernel_implemented':False,'aging_validation_executed':False,
        'canonical_data_reads':0,'optimizer_calls':0,'independent_reviewer':False,
        'scope':'Source bindings, coordinate ownership, dimensions, inherited supports, exposure units and selected charge convention arithmetic only. No validation of battery aging, posterior inference or compression.'}
    with (HERE/'specification_checks.json').open('x') as out:json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps({'status':result['status'],'checks':len(checks)}))

if __name__=='__main__':main()
