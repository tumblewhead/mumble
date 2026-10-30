"""Bounded, source-bound representation comparison; no optimizer or plant truth."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import ctypes as C
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
import numpy as np
from basis import Basis, independent

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'history_provider_001'))
from qualify import Harness,Result,DP,ptr,identity,save,SOURCES


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    plan=json.loads((HERE/'plan.json').read_text())
    source_fixture=ROOT/plan['inputs']['source']
    # Bind all transitive project headers, not only compilation units.
    tracked=list(SOURCES)+[HERE/'qr.c',HERE/'basis.py',HERE/'compare.py',HERE/'plan.json',
                          HERE.parent/'history_provider_001/qualify.py',source_fixture]
    for directory in [ROOT/'include',HERE.parent/'history_provider_001',
                      HERE.parent/'live_anchor_integration_001',HERE.parent/'live_anchor_bootstrap_001',
                      HERE.parent/'compact_nonlinear_history_001']:
        tracked.extend(sorted(directory.glob('*.h')))
    sources={str(p.relative_to(ROOT)):identity(p) for p in tracked}
    save(out/'reservation.json',dict(sources=sources,plan=plan,
        command=sys.argv,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
        worktree_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
        status='reserved_before_build_or_evaluation'))
    started=time.monotonic();checks=0;steps=0;arms=[]
    result=dict(status='qualification_failed',arms=arms,optimizer_calls=0,truth_reads=0,
                canonical_reads=0,solver_modified=False,aging_added=False)
    def check(value,label):
        nonlocal checks
        checks+=1
        if not value:raise AssertionError(label)
    def close(a,b,label):check(np.allclose(a,b,rtol=2e-10,atol=2e-8),label)
    def work(n):
        nonlocal steps
        if steps+n>plan['qualification']['cap_model_steps']:raise RuntimeError('pre-call work cap')
        steps+=n
    try:
        command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
                 '-fno-fast-math','-ffp-contract=off','-shared','-fPIC','-I'+str(ROOT/'include'),
                 *map(str,SOURCES),str(HERE/'qr.c'),'-lm','-o',str(out/'provider.so')]
        build=subprocess.run(command,capture_output=True,text=True)
        save(out/'build.json',dict(command=command,returncode=build.returncode,stdout=build.stdout,stderr=build.stderr))
        check(build.returncode==0,'C build')
        h=Harness(out/'provider.so');lib=h.lib
        lib.hb_qr_append.argtypes=[DP,DP,C.c_size_t,C.c_uint]
        lower=np.array((C.c_double*16).in_dll(lib,'ch_lower'))
        upper=np.array((C.c_double*16).in_dll(lib,'ch_upper'))
        fixture=json.loads(source_fixture.read_text());rng=np.random.default_rng(plan['queries']['seed'])
        points=np.vstack((fixture['nodes'],rng.uniform(np.maximum(lower,h.mean-.4*h.sd),
                        np.minimum(upper,h.mean+.4*h.sd),size=(64,16)),rng.uniform(lower,upper,size=(32,16))))
        rows=[]
        for raw in fixture['raw']:
            row=np.zeros(3);check(lib.hp_decode(*raw,ptr(row))==0,'decode');rows.append(row)
        rows=np.tile(np.asarray(rows),(64,1))
        save(out/'frozen_inputs.json',dict(raw_cycle=fixture['raw'],repeat_count=64,
            chronology='new ordered fabricated records; states carry across repetitions',
            queries=points.tolist(),groups={'original_axis':[0,33],'joint_local':[33,97],'global':[97,129]},
            mean=h.mean.tolist(),sd=h.sd.tolist(),lower=lower.tolist(),upper=upper.tolist()))

        def factor(design,partitions=None):
            n,dim=design.shape;packed=np.zeros(dim*(dim+1)//2);first=0
            for end in partitions or [n]:
                block=np.ascontiguousarray(design[first:end])
                check(lib.hb_qr_append(ptr(packed),ptr(block),len(block),dim)==0,'QR append')
                first=end
            check(first==n,'QR partitions cover rows once')
            matrix=np.zeros((dim,dim));matrix[np.triu_indices(dim)]=packed
            return matrix

        references=[]
        for n in plan['inputs']['prefixes']:
            observations=np.ascontiguousarray(rows[:n]);costs=[];gradients=[];endpoints=[]
            began=time.monotonic()
            for x in points:
                work(n);r=Result()
                check(lib.hp_exact_query(ptr(observations),n,ptr(x),C.byref(r))==0,'exact C available')
                costs.append(r.likelihood);gradients.append(list(r.gradient));endpoints.append(list(r.endpoint))
            exact_wall=time.monotonic()-began
            costs=np.array(costs);gradients=np.array(gradients);endpoints=np.array(endpoints)
            work(n*len(points));ic,ie=independent(observations,points)
            close(ic,costs,'independent cost');close(ie,endpoints,'independent endpoint')
            references.append(dict(records=n,elapsed_s=float(observations[:,0].sum()),
                                   exact_query_wall_s=exact_wall,queries=len(points),
                                   max_independent_cost_gap=float(np.max(abs(ic-costs))),
                                   max_independent_endpoint_gap=float(np.max(abs(ie-endpoints)))))
            save(out/f'reference_{n}.json',dict(costs=costs.tolist(),gradients=gradients.tolist(),endpoints=endpoints.tolist()))
            for family in plan['arms']['families']:
                for degree in plan['arms']['degrees']:
                    for domain in plan['arms']['domains']:
                        basis=Basis(family,degree,domain,h.mean,h.sd,lower,upper)
                        phi,jac=basis.features(h.mean)
                        for j in range(16):
                            delta=1e-5*h.sd[j];xp=h.mean.copy();xm=h.mean.copy();xp[j]+=delta;xm[j]-=delta
                            fd=(basis.features(xp)[0]-basis.features(xm)[0])/(2*delta)
                            check(np.all(abs(fd-jac[:,j])*h.sd[j]<=1e-5*np.maximum(1,abs(jac[:,j])*h.sd[j])),
                                  'feature derivative '+family+str(degree)+domain+str(j))
                        began=time.monotonic();work(n*(3*basis.m+2*basis.m*basis.m))
                        design=basis.rows(observations);matrix=factor(design)
                        build_wall=time.monotonic()-began
                        partitioned=factor(design,[17,n])
                        close(matrix,partitioned,'identical global rows partitioned append')
                        numpy_r=np.linalg.qr(design,mode='r')
                        evaluated=[(i,basis.features(x)) for i,x in enumerate(points)]
                        valid=[i for i,v in evaluated if v is not None]
                        features=np.stack([v[0] for i,v in evaluated if v is not None])
                        derivatives=np.stack([v[1] for i,v in evaluated if v is not None])
                        began=time.monotonic();projected=features@matrix.T
                        bc=.5*np.sum(projected**2,axis=1)
                        bg=np.einsum('nf,nfj->nj',projected@matrix,derivatives)
                        be=np.stack([basis.endpoint(points[i]) for i in valid])
                        query_wall=time.monotonic()-began
                        direct=features@design.T
                        close(bc,.5*np.sum(direct**2,axis=1),'factor versus direct residual')
                        close(bc,.5*np.sum((features@numpy_r.T)**2,axis=1),'factor versus numpy QR')
                        close(bg,np.einsum('nf,nfj->nj',direct@design,derivatives),'factor gradient versus rows')
                        # Lossless paired coordinates: D'=D U; phi'=U^T phi.
                        rotation=np.eye(basis.dim)
                        for k in range(0,basis.dim-1,2):
                            rotation[k:k+2,k:k+2]=np.array([[1.,-1.],[1.,1.]])/np.sqrt(2.)
                        rotated=factor(np.ascontiguousarray(design@rotation))
                        paired=.5*np.sum(((features@rotation)@rotated.T)**2,axis=1)
                        close(paired,bc,'orthogonal pairing invariant')
                        gap=bc-costs[valid];egap=be-endpoints[valid];ggap=(bg-gradients[valid])*h.sd
                        groups={}
                        for name,lo,hi in [('axis',0,33),('joint_local',33,97),('global',97,129),('all_available',0,129)]:
                            selected=[k for k,i in enumerate(valid) if lo<=i<hi]
                            groups[name]=dict(available=len(selected),requested=hi-lo)
                            if selected:
                                g=gap[selected]
                                groups[name].update(error_oscillation_NLL=float(np.ptp(g)),
                                    max_absolute_cost_gap_NLL=float(np.max(abs(g))),
                                    max_scaled_gradient_gap=float(np.max(abs(ggap[selected]))),
                                    max_endpoint_gap_by_coordinate=np.max(abs(egap[selected]),axis=0).tolist(),
                                    finite_cost_gate_pass=bool(np.ptp(g)<=.1))
                        factor_bytes=basis.dim*(basis.dim+1)//2*8
                        # This is retained numeric data ONLY: excludes configuration, sources,
                        # solver, raw queue, scratch, stack and runtime needs.
                        boundary_bytes=(6*basis.m+2*basis.m*basis.m+1)*8
                        arm=dict(records=n,family=family,degree=degree,domain=domain,features=basis.dim,
                            factor_bytes=factor_bytes,boundary_bytes=boundary_bytes,
                            retained_numeric_lower_bound_bytes=factor_bytes+boundary_bytes,
                            factor_alone_exceeds_entire_10240B_target=factor_bytes>10240,
                            groups=groups,construction_wall_s=build_wall,query_batch_wall_s=query_wall,
                            max_orthogonal_cost_change_NLL=float(np.max(abs(paired-bc))),
                            available_indices=valid,cost_gaps=gap.tolist(),
                            unavailable_indices=[i for i,v in evaluated if v is None])
                        check((domain=='full_public' and len(valid)==129) or
                              (domain=='public_half_SD' and all(i in valid for i in range(97)) and len(valid)<129),
                              'declared domain availability')
                        arms.append(arm)
                        print(json.dumps({k:arm[k] for k in ['records','family','degree','domain','retained_numeric_lower_bound_bytes']}
                                         | {'oscillation':groups['all_available']['error_oscillation_NLL']}),flush=True)
        check(all(identity(ROOT/name)==value for name,value in sources.items()),'bound sources unchanged')
        result.update(status='numerical_controls_passed',references=references,
            compressor_qualified=False,coverage_qualified=False,complete_SRAM_qualified=False,
            interpretation='Finite representation diagnostic. Approximation failures are measurements, not numerical qualification failures.')
    except Exception:
        result['error']=traceback.format_exc()
    result.update(checks=checks,model_steps_upper=steps,wall_s=time.monotonic()-started)
    save(out/'receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='arms'},indent=2),flush=True)
    return 0 if result['status']=='numerical_controls_passed' else 1


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: python3 -B compare.py EXCLUSIVE_OUTPUT_DIRECTORY')
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
