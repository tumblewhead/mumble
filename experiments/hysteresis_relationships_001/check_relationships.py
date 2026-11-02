"""Finite checks of H1/H3 on existing streams; not a new battery accuracy study."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import ROOT,identity,prepare_c
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.hysteresis_refinement_001.field import build
from experiments.h7_history_quality_001.history import write,source_receipt,verify_sources


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--out',required=True,type=Path);parser.add_argument('--baseline',type=Path,default=Path('experiments/partitioned_coefficients_001/followup002'));args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    reg=json.loads((args.baseline/'registration.json').read_text());config=reg['config'];query=next(q for q in reg['queries'] if q['id']=='t0_a0')
    a=np.array(query['a']);shape=np.array(query['s']);m=config['ocv_slope_V_per_SOC'];center=reg['center']
    binary=build(args.out/'response');cbinary=prepare_c(args.out,35,config)[0];model=Model(cbinary,config);sources=source_receipt()
    write(args.out/'registration.json',dict(source=sources,query=query,query_selection='Unchanged public prior center, first public query t0_a0; no fitted/plant parameter used',
        proof_bindings={str(p.relative_to(ROOT)):identity(p) for p in sorted((ROOT/'specifications/hysteresis_relationships_001').glob('H*.md'))},baseline_registration=identity(args.baseline/'registration.json'),response_binary=identity(binary),direct_binary=identity(cbinary)))
    cases=[]
    for path in sorted(args.baseline.glob('case_*/result.json')):
        prior=json.loads(path.read_text());recipe=prior['recipe'];source=prior['source_id'];stream=StimulusStream(config,recipe['cell'],recipe['case'],recipe['settings']);digest=hashlib.sha256()
        f=BasisField(config,center,binary,2,'log',source);W,DW,_=f.basis_query(a,shape);x=chart_from(a,shape);D=chart_amplitude_jacobian(a)
        qr=np.zeros((4,4));moment=np.zeros(6);g=np.zeros(2);charge=0.;lo=hi=0.;up=um=0.;runs=[];prefixes=[]
        # moments: sum w, wA, wA2, we, wAe, we2. All e is H-only defect.
        for prefix in prior['prefixes']:
            target=prefix['records']
            while stream.index<target:
                first=stream.index;obs,_,_=stream.read(min(1024,target-first))
                if stream.failure or not len(obs):raise ValueError('fixture stopped')
                digest.update(obs.astype('<f8',copy=False).tobytes())
                rows=f.rows(first,obs,source);approxJ=rows@DW
                v,J,end,F=model.evaluate(x,obs);exactJ=J@D;x=end;D=F@D
                sigma=obs[:,4];weights=1/sigma**2
                e=(approxJ[:,[9,10]]*sigma[:,None]-exactJ[:,[9,10]])@a[[9,10]]
                A=charge+np.cumsum(obs[:,0]*obs[:,1]/3600);charge=float(A[-1]);lo=min(lo,float(A.min()));hi=max(hi,float(A.max()))
                g+=exactJ[:,[0,4]].T@(weights*e)
                moment+=np.array([np.sum(weights),weights@A,weights@(A*A),weights@e,weights@(A*e),weights@(e*e)])
                block=np.column_stack((np.full(len(obs),m),-m*A,v-obs[:,3],e))/sigma[:,None]
                qr=np.linalg.qr(np.vstack((qr,block)),mode='r')
                for dt,I in obs[:,:2]:
                    if I==0:continue
                    U=float(abs(I)*dt/3600);sign=1 if I>0 else -1
                    if sign>0:up+=U
                    else:um+=U
                    if runs and runs[-1][0]==sign:runs[-1][1]+=U
                    else:runs.append([sign,U])
            if digest.hexdigest()!=prefix['observation_sha256']:raise ValueError('frozen observation stream mismatch')
            sw,sa,saa,se,sae,see=moment;meanA=sa/sw;meanE=se/sw;varianceA=saa/sw-meanA*meanA;cov=sae/sw-meanA*meanE
            expected=np.array([m*se,-m*sae]);closed=float(np.linalg.norm(g-expected)/max(1,np.linalg.norm(expected)))
            if closed>1e-7:raise ValueError('charge moment gradient check')
            totaldose=shape[3]*up+shape[4]*um
            record=dict(records=target,observation_sha256=digest.hexdigest(),directional_throughput_Ah=[up,um],total_dose_at_public_center=float(totaldose),
                sign_runs=len(runs),sign_reversals=max(0,len(runs)-1),last_run_dose_at_public_center=float(shape[3 if runs[-1][0]>0 else 4]*runs[-1][1]) if runs else 0.,
                hysteresis_error_mean_V=float(meanE),hysteresis_error_RMS_V=float(np.sqrt(see/sw)),weighted_signed_charge_variance_Ah2=float(varianceA),weighted_charge_error_covariance_Ah_V=float(cov),
                C_jacobian_gradient_difference=g.copy(),charge_moment_gradient_prediction=expected,relative_gradient_identity_error=closed)
            # Independent H1 evaluation: chronological affine versus tail-switch expression.
            Eh=1.;uh=0.
            for sign,U in runs:
                E=np.exp(-shape[3 if sign>0 else 4]*U);Eh*=E;uh=E*uh-sign*np.expm1(-shape[3 if sign>0 else 4]*U)
            free=np.exp(-totaldose);forced=0.
            if runs:
                forced=runs[-1][0]-runs[0][0]*free;tailplus=tailminus=0.
                for j in range(len(runs)-1,0,-1):
                    sign,U=runs[j]
                    if sign>0:tailplus+=U
                    else:tailminus+=U
                    forced+=(runs[j-1][0]-sign)*np.exp(-shape[3]*tailplus-shape[4]*tailminus)
            h_ref=np.tanh(x[4]);h_affine=Eh*(a[10]/a[9])+uh;h_switch=free*(a[10]/a[9])+forced
            record['endpoint_checks']=dict(free_exponential_vs_recurrence=float(abs(free-Eh)),affine_vs_direct_C_h=float(abs(h_affine-h_ref)),switch_vs_affine_h=float(abs(h_switch-h_affine)))
            if max(record['endpoint_checks'].values())>1e-8:raise ValueError('chronological endpoint identity')
            if varianceA>0:
                predicted_dq=cov/(m*varianceA);predicted_dz=-meanE/m+meanA*predicted_dq
                ref=np.linalg.lstsq(qr[:,:2],-qr[:,2],rcond=None)[0];approx=np.linalg.lstsq(qr[:,:2],-qr[:,2]-qr[:,3],rcond=None)[0];shift=approx-ref
                expectedshift=np.array([predicted_dz,predicted_dq]);err=float(np.max(abs(shift-expectedshift)))
                if err>1e-6*max(1,float(np.max(abs(expectedshift)))):raise ValueError('conditional fit-displacement identity')
                qref=a[4]+ref[1];qapprox=a[4]+approx[1];zref=a[0]+ref[0];zapprox=a[0]+approx[0]
                sdE=float(np.sqrt(max(0,see/sw-meanE**2)));bound=sdE/(m*np.sqrt(varianceA))
                record['conditional_two_parameter_fit']=dict(status='unconstrained_diagnostic_not_a_battery_estimate',observed_delta_z0_q=shift,predicted_delta_z0_q=expectedshift,max_abs_identity_error=err,
                    absolute_inverse_capacity_shift_bound=float(bound),bound_holds_with_roundoff=bool(abs(predicted_dq)<=bound+1e-10),
                    reference_z0_q=[float(zref),float(qref)],approximate_z0_q=[float(zapprox),float(qapprox)],
                    reference_SOC_Q_support=bool(qref>0 and zref-qref*hi<=1 and zref-qref*lo<=1 and zref-qref*hi>=0 and zref-qref*lo>=0),
                    approximate_SOC_Q_support=bool(qapprox>0 and zapprox-qapprox*hi<=1 and zapprox-qapprox*lo<=1 and zapprox-qapprox*hi>=0 and zapprox-qapprox*lo>=0),
                    relative_capacity_shift=float(-shift[1]/qapprox) if qref>0 and qapprox>0 else None)
            else:record['conditional_two_parameter_fit']=dict(status='unresolved_zero_charge_variation')
            prefixes.append(record)
        cases.append(dict(load=prior['load'],baseline_result=dict(path=str(path),identity=identity(path)),prefixes=prefixes))
    verify_sources(sources)
    write(args.out/'result.json',dict(status='finite_symbolic_identity_checks_pass',scope='Public center, fixed nuisance parameters and two unconstrained conditional fits only; no fitted accuracy, full-posterior, physical coverage or compression qualification',cases=cases))

if __name__=='__main__':main()
