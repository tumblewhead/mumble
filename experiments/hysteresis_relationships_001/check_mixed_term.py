"""Check the H4 omitted-term identity; tensor rows are a diagnostic, not a repair."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from experiments.foster_campaign_001.backend import ROOT,identity,prepare_c
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.hysteresis_refinement_001.field import build
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources


def projection_check():
    a=np.sqrt(3)/2;nodes=np.array([a,0.,-a]);V=chebvander(nodes,2);pairs=[(i,j) for i in range(3) for j in range(3) if i+j<=2]
    M=np.column_stack([np.outer(V[:,i],V[:,j]).ravel() for i,j in pairs]);P=np.linalg.pinv(M);center=np.array([chebvander(0.,2)[0,i]*chebvander(0.,2)[0,j] for i,j in pairs]);mx=0.
    w=np.array([1.,-2.,1.])/3;rng=np.random.default_rng(20261103)
    for _ in range(100):
        values=rng.normal(size=(3,3));c22=w@values@w
        gap=center@(P@values.ravel())-values[1,1]
        mx=max(mx,float(abs(gap+c22)))
    if mx>1e-12:raise ValueError('central omitted-term identity')
    return dict(grids=100,max_absolute_identity_error=mx)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',required=True,type=Path);p.add_argument('--baseline',type=Path,default=Path('experiments/partitioned_coefficients_001/followup002'));args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);algebra=projection_check();reg=json.loads((args.baseline/'registration.json').read_text());config=reg['config'];q=next(q for q in reg['queries'] if q['id']=='t0_a0');a=np.array(q['a']);shape=np.array(q['s'])
    binary=build(args.out/'response');cbinary=prepare_c(args.out,35,config)[0];model=Model(cbinary,config);sources=source_receipt()
    write(args.out/'registration.json',dict(source=sources,proof=identity(ROOT/'specifications/hysteresis_relationships_001/H4.md'),baseline_registration=identity(args.baseline/'registration.json'),query=q,response_binary=identity(binary),direct_binary=identity(cbinary)))
    cases=[]
    for path in sorted(args.baseline.glob('case_*/result.json')):
        old=json.loads(path.read_text());recipe=old['recipe'];source=old['source_id'];stream=StimulusStream(config,recipe['cell'],recipe['case'],recipe['settings']);digest=hashlib.sha256()
        td=BasisField(config,reg['center'],binary,2,'log',source);full=BasisField(config,reg['center'],binary,2,'log',source)
        full.pairs=[(i,j) for i in range(3) for j in range(3)];full.b=9;full.p2=np.ascontiguousarray(np.kron(full.p1,full.p1));full.width=40;full.root=np.zeros((40,40))
        _,tdD,_=td.basis_query(a,shape);_,fullD,_=full.basis_query(a,shape);start=3+6*td.n;idx=full.pairs.index((2,2));colu=start+idx;colE=start+full.b+idx
        x=chart_from(a,shape);D=chart_amplitude_jacobian(a);largest=0.;fullgap=0.;responsegap=np.zeros(2);ss=0.;maximum=0.;count=0;up=um=0.;runs=[];prefixes=[]
        for prefix in old['prefixes']:
            while stream.index<prefix['records']:
                first=stream.index;obs,_,_=stream.read(min(1024,prefix['records']-first))
                if stream.failure or not len(obs):raise ValueError('fixture stopped')
                digest.update(obs.astype('<f8',copy=False).tobytes());rtd=td.rows(first,obs,source);rfull=full.rows(first,obs,source)
                _,J,end,F=model.evaluate(x,obs);exact=(J@D)[:,[9,10]];x=end;D=F@D
                approx=(rtd@tdD[:,[9,10]])*obs[:,4,None];tensor=(rfull@fullD[:,[9,10]])*obs[:,4,None]
                omitted=rfull[:,[colu,colE]]*obs[:,4,None]
                responsegap=np.maximum(responsegap,np.max(abs(approx-exact+omitted),axis=0))
                actual=(approx-exact)@a[[9,10]];predicted=-omitted@a[[9,10]]
                largest=max(largest,float(np.max(abs(actual-predicted))));fullgap=max(fullgap,float(np.max(abs(tensor-exact))))
                ss+=float(actual@actual);maximum=max(maximum,float(np.max(abs(actual))));count+=len(obs)
                for dt,I in obs[:,:2]:
                    if I==0:continue
                    sign=1 if I>0 else -1;U=float(abs(I)*dt/3600)
                    if sign>0:up+=U
                    else:um+=U
                    if runs and runs[-1][0]==sign:runs[-1][1]+=U
                    else:runs.append([sign,U])
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('stream mismatch')
            if max(largest,fullgap,float(responsegap.max()))>1e-9:raise ValueError('mixed-term identity versus C')
            two_run=None
            if len(runs)==2:
                nodes=td.nodes;pvalues=np.exp(-shape[3]*np.exp(nodes)*up);mvalues=np.exp(-shape[4]*np.exp(nodes)*um);weights=np.array([1.,-2.,1.])/3
                formula=(a[9]*runs[0][0]-a[10])*(weights@pvalues)*(weights@mvalues)
                two_run=dict(first_sign=runs[0][0],observed_endpoint_voltage_defect_V=float(actual[-1]),factorized_prediction_V=float(formula),absolute_gap_V=float(abs(actual[-1]-formula)))
                if two_run['absolute_gap_V']>1e-9:raise ValueError('two-run mixed product')
            prefixes.append(dict(records=count,observation_sha256=digest.hexdigest(),maximum_voltage_defect_V=maximum,RMS_voltage_defect_V=float(np.sqrt(ss/count)),
                maximum_c22_prediction_gap_V=largest,maximum_full_tensor_central_coefficient_gap_vs_C=fullgap,
                maximum_forced_free_c22_identity_gap=responsegap,sign_runs=len(runs),two_run_factorization=two_run))
        cases.append(dict(load=old['load'],baseline_result=dict(path=str(path),identity=identity(path)),prefixes=prefixes))
    verify_sources(sources);write(args.out/'result.json',dict(status='finite_central_mixed_term_identity_checks_pass',scope='Public centre only, values not true derivatives, no fitted/whole-domain or deployment qualification',algebra_check=algebra,cases=cases))

if __name__=='__main__':main()
