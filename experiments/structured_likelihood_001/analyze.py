"""Frozen storage experiment; approximation and retained uncertainty are separate."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import numpy as np
from storage import ProductPacked,RankHistory,envelopes,rank_memory
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
FORCED=HERE.parent/'forced_rc_kernel_001';FREE=HERE.parent/'free_rc_kernel_001'
PREV=HERE.parent/'response_symbolic_diagnostic_001';OLD=HERE.parent/'partitioned_history_001';FIXED=HERE.parent/'history_basis_comparison_001'
sys.path.insert(0,str(FORCED));from forced import JointRC
sys.path.insert(0,str(PREV));from response import ResponseBasis
sys.path.insert(0,str(OLD));from partition import Partition,dynamic_rows
sys.path.insert(0,str(HERE.parent/'history_provider_001'));from qualify import Harness,ptr,identity,save


def run(out):
    out.mkdir(parents=True,exist_ok=False);plan=json.loads((HERE/'plan.json').read_text());source=ROOT/plan['inputs'];binary=OLD/'comparison001/provider.so'
    paths=list(HERE.glob('*.py'))+[HERE/'plan.json',FORCED/'forced.py',FORCED/'attempt001/receipt.json',FREE/'kernel.py',PREV/'response.py',OLD/'partition.py',FIXED/'basis.py',HERE.parent/'history_provider_001/qualify.py',source,binary]
    bindings={str(p.relative_to(ROOT)):identity(p) for p in paths}
    for p in paths:
        dest=out/'sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    save(out/'reservation.json',dict(status='before_evaluation',plan=plan,sources=bindings,command=sys.argv,revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()))
    result=dict(status='failed',cases=[],optimizer_calls=0,truth_reads=0,solver_modified=False,aging_added=False,deployment_qualified=False)
    work={k:0 for k in plan['caps'] if k!='automatic_retries'};checks=0;flags=[];case='setup';start=time.monotonic()
    def check(v,label):
        nonlocal checks
        checks+=1
        if not v:raise AssertionError(case+': '+label)
    def reserve(key,n):
        check(work[key]+n<=plan['caps'][key],'pre-call '+key+' cap');work[key]+=n
    def close(a,b,label,atol=2e-8,rtol=2e-10):
        nonlocal checks
        a=np.asarray(a);b=np.asarray(b);check(np.all(np.isfinite(a)) and np.all(np.isfinite(b)),label+' finite')
        gap=abs(a-b);ratio=gap/(atol+rtol*abs(b));checks+=1
        if np.any(ratio>1):flags.append(dict(case=case,label=label,max_abs_gap=float(gap.max()),max_allowance_ratio=float(ratio.max()),failed_entries=int(np.sum(ratio>1))))
    def stream(a,rank,signature,begin=0):
        reserve('svd_calls',max(0,len(a)-rank));obj=RankHistory(rank,a.shape[1],signature,begin)
        for index,row in enumerate(a,begin):obj.append(row,index)
        return obj
    def assess(obj,psi,jpsi,fc,fg,fgn,ag,anorm):
        metrics=[obj.metrics(v,j,gn=i==0) for i,(v,j) in enumerate(zip(psi,jpsi))]
        costs=np.array([m[0] for m in metrics]);gradient=np.stack([m[1] for m in metrics]);gn=metrics[0][2]
        widths=np.array([obj.cost_width(v) for v in psi]);gw=np.array([obj.gradient_width(v,j) for v,j in zip(psi,jpsi)])
        close(np.maximum(np.maximum(costs-fc,fc-costs-widths),0),np.zeros(len(fc)),'cost envelope',atol=2e-8+2e-10*abs(fc),rtol=0)
        excess=np.maximum(abs(gradient-fg)-gw,0)/(2e-8+2e-10*abs(fg));close(excess,0,'gradient envelope scaled',atol=1.,rtol=0)
        rem=fgn-gn;upper=obj.delta*(jpsi[0].T@jpsi[0])-rem;tol=2e-8+2e-10*np.linalg.norm(fgn,2)
        minrem=float(np.linalg.eigvalsh((rem+rem.T)/2).min());minupper=float(np.linalg.eigvalsh((upper+upper.T)/2).min())
        close(max(0.,-minrem,-minupper),0,'GN envelope PSD',atol=tol,rtol=0)
        e=ag-obj.factor.T@obj.factor;ev=np.linalg.eigvalsh((e+e.T)/2);allow=128*np.finfo(float).eps*max(1.,anorm)
        close(max(0.,-float(ev.min()),float(ev.max())-obj.delta),0,'global scaled PSD envelope',atol=allow,rtol=0)
        gaps=costs-fc
        return dict(rank=obj.rank,delta=obj.delta,added_error_oscillation_NLL=float(np.ptp(gaps)),cost_gaps_NLL=gaps.tolist(),max_absolute_cost_gap_NLL=float(np.max(abs(gaps))),cost_width_range_NLL=[float(widths.min()),float(widths.max())],domain_wide_cost_width_bound_NLL=float(obj.delta*psi.shape[1]/2),raw_cost_interval_max_violation_NLL=float(max(0.,np.max(costs-fc),np.max(fc-costs-widths))),max_absolute_gradient_gap=float(np.max(abs(gradient-fg))),GN_error_spectral_norm=float(np.linalg.norm(rem,2)),global_PSD_remainder_eigen_range=[float(ev.min()),float(ev.max())],global_PSD_roundoff_allowance=allow,source_interval=[obj.start,obj.stop],finite_arithmetic_certificate=False)
    try:
        h=Harness(binary);inp=json.loads(source.read_text());lower=np.array(inp['lower']);upper=np.array(inp['upper']);points=np.array(inp['queries']);rows=[]
        for raw in inp['raw_cycle']:
            row=np.zeros(3);check(h.lib.hp_decode(*raw,ptr(row))==0,'source decode');rows.append(row)
        rows=np.tile(rows,(inp['repeat_count'],1));limits=[(upper[11]-1)*np.exp(lower[5]),lower[11]*np.exp(lower[5])]
        prior=json.loads((FORCED/'attempt001/receipt.json').read_text())
        g=np.eye(3);d=np.array([[0.,0.,1.],[0.,-2.,0.],[1.,0.,0.]]);g2=g+.1*d
        check(np.linalg.eigvalsh(g2).min()>0,'PSD cost-only counterexample')
        for z in [-.5,0.,.5]:
            v=np.array([1.,z,z*z]);j=np.array([0.,1.,2*z]);close(v@g@v,v@g2@v,'same cost polynomial');close(j@(g2-g)@j,-.2,'different GN despite same cost')
        result['cost_only_counterexample']=dict(Gram1=g.tolist(),Gram2=g2.tolist(),GN_difference=-.2)
        for n in plan['fixed']['prefixes']:
            obs=rows[:n];charges=np.cumsum(obs[:,0]*obs[:,1]/3600)
            for domain in plan['fixed']['domains']:
                basis=ResponseBasis(dict(physical_RC=False,physical_hysteresis=True,tensor_hysteresis=False),domain,h.mean,h.sd,lower,upper)
                reserve('model_node_steps',n*65);full=basis.rows(obs);p=Partition(basis,12,limits)
                old=np.column_stack((dynamic_rows(basis,full,obs),p.charge_rows(charges)[:,:p.k]))
                ids=[i for i,x in enumerate(points) if p.query(x) is not None];xx=points[ids]
                check(len(ids)==(97 if domain=='public_half_SD' else 129),'same query domain')
                for k in plan['fixed']['K']:
                    case=f'{n}/{domain}/K{k}';bank=JointRC(p,'time_kernel',k)
                    reserve('full_convolution_products',3*n*k*k);design=bank.rows(old,obs);queries=[bank.query(x) for x in xx]
                    v=np.stack([q[0] for q in queries]);jac=np.stack([q[1] for q in queries]);dr=v@design.T
                    fc=np.sum(dr*dr,axis=1)/2;fg=np.einsum('qf,qfj->qj',dr@design,jac);dj=design@jac[0];fgn=dj.T@dj
                    previous=next(e for e in prior['arms'] if (e['records'],e['domain'],e['family'],e['coefficients'])==(n,domain,'time_kernel',k))
                    close(fc,previous['score']['direct_approx_costs'],'predecessor represented cost')
                    qr=np.linalg.qr(design,mode='r');qv=v@qr.T;close(np.sum(qv*qv,axis=1)/2,fc,'full QR reference cost')
                    packed=ProductPacked(design,bank,charges);pm=[packed.metrics(x,q,gn=i==0) for i,(x,q) in enumerate(zip(xx,queries))]
                    pc=np.array([q[0] for q in pm]);pg=np.stack([q[1] for q in pm]);close(pc,fc,'exact product-packed cost');close(pg,fg,'exact product-packed gradient');close(pm[0][2],fgn,'exact product-packed GN')
                    w=envelopes(bank,lower,upper);psi=v/w;jpsi=jac/w[None,:,None];check(np.all(abs(psi)<=1+1e-12),'fixed public feature envelopes')
                    a=design*w;ag=a.T@a;anorm=float(np.sum(a*a));signature=(bindings[str(source.relative_to(ROOT))]['sha256'],domain,k)
                    reserve('svd_calls',1);_,sing,vt=np.linalg.svd(qr*w,full_matrices=False)
                    common=bank.memory()['QR_planned_subsystem_B']-bank.memory()['QR_numeric_B']
                    entry=dict(records=n,domain=domain,coefficients=k,query_count=len(ids),features=bank.dim,reference_memory=bank.memory(),represented_physical_error_oscillation_NLL=previous['score']['error_oscillation_NLL'],packing=dict(numeric_bytes=packed.numeric_bytes,complete_prospective_bytes=common+packed.numeric_bytes,payload_saving_bytes=bank.memory()['QR_numeric_B']-packed.numeric_bytes,added_error_oscillation_NLL=float(np.ptp(pc-fc)),max_absolute_cost_gap_NLL=float(np.max(abs(pc-fc))),max_absolute_gradient_gap=float(np.max(abs(pg-fg)))),ranks=[])
                    for rank in plan['rank_storage']['ranks']:
                        case=f'{n}/{domain}/K{k}/rank{rank}';batch=RankHistory(rank,bank.dim,signature);batch.stop=n
                        batch.factor=sing[:rank,None]*vt[:rank];batch.delta=float(sing[rank]**2) if rank<len(sing) else 0.
                        b=assess(batch,psi,jpsi,fc,fg,fgn,ag,anorm)
                        online=stream(a,rank,signature);s=assess(online,psi,jpsi,fc,fg,fgn,ag,anorm)
                        entry['ranks'].append(dict(rank=rank,batch=b,stream=s,memory=rank_memory(bank,rank)))
                    case=f'{n}/{domain}/K{k}/merge8';left=stream(a[:17],8,signature);right=stream(a[17:],8,signature,17)
                    reserve('svd_calls',1);merged=left.merge(right);entry['merge_rank8']=assess(merged,psi,jpsi,fc,fg,fgn,ag,anorm)
                    for bad in [left,RankHistory(8,bank.dim,signature,18),RankHistory(8,bank.dim,('wrong',domain,k),17)]:
                        try:left.merge(bad)
                        except ValueError:checks+=1
                        else:raise AssertionError('invalid source/config merge accepted')
                    if (n,domain,k)==(4096,'public_half_SD',9):
                        case='cancellation';synthetic=design.copy();constant=int(np.flatnonzero(bank.keep==p.m-1)[0]);vv,jj=queries[0]
                        synthetic[:,constant]=0;synthetic[:,constant]=-(synthetic@vv)
                        residual=synthetic@vv;ref=float(residual@residual/2);r0=np.linalg.qr(synthetic,mode='r')@vv
                        packed0=ProductPacked(synthetic,bank,charges);c0=packed0.metrics(h.mean,queries[0])[0]
                        check(np.isfinite(c0),'finite cancellation cost');close(c0,ref,'product-packed zero residual');close(r0@r0/2,ref,'QR zero residual')
                        online0=stream(synthetic*w,8,signature);rr=online0.factor@psi[0]
                        result['cancellation']=dict(direct_cost=ref,QR_cost=float(r0@r0/2),product_packed_cost=c0,rank8_cost=float(rr@rr/2),rank8_width=online0.cost_width(psi[0]),clipped=False)
                    result['cases'].append(entry)
                    print(json.dumps(dict(case=f'{n}/{domain}/K{k}',packed_B=packed.numeric_bytes,rank32_stream_gap=entry['ranks'][-1]['stream']['max_absolute_cost_gap_NLL'],rank32_stream_width=entry['ranks'][-1]['stream']['cost_width_range_NLL'])),flush=True)
        check(len(result['cases'])==plan['source_cases'],'all frozen source cases completed')
        check(all(identity(ROOT/name)==binding for name,binding in bindings.items()),'source hashes unchanged')
        result['status']='completed_with_numerical_mismatches' if flags else 'numerical_controls_passed'
    except Exception:result['error']=traceback.format_exc()
    result.update(checks=checks,work=work,numerical_mismatches=flags,wall_s=time.monotonic()-start)
    save(out/'receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['cases','numerical_mismatches']},indent=2),flush=True)
    print('numerical comparison flags:',len(flags),flush=True)
    return 0 if result['status']=='numerical_controls_passed' else 1


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: analyze.py EXCLUSIVE_OUTPUT_DIRECTORY')
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
