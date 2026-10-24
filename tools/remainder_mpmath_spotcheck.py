#!/usr/bin/env python3
"""Independent arbitrary-precision replay of fixed B002 diagnostic candidates.

This is a diagnostic of real-valued Taylor error, not a replacement for the
preserved binary64 audit or any changed acceptance tolerance. It performs no
optimization. Physical states and their anchor derivatives are propagated
directly, independently of the C affine design-row implementation.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import time

import mpmath as mp


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(value):
    numerator, denominator = float(value).as_integer_ratio()
    return mp.mpf(numerator) / denominator


def parse_anchor(path):
    tokens = path.read_text().split()
    modes = int(tokens[0]); nt = modes + 4; na = 2*modes + 3
    return modes, float(tokens[1]), list(map(float, tokens[3:3+nt])), \
        list(map(float, tokens[3+nt:3+nt+na])), \
        list(map(float, tokens[3+nt+na:3+nt+na+nt+na]))


def run(repo, run_name, checkpoint_name, candidate_name, dps):
    mp.mp.dps = dps
    folder = repo / 'experiments/bounded_event_002/receipt'
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    record_path = folder / (run_name + '.json')
    record = json.loads(record_path.read_text())
    checkpoint = next(x for x in record['checkpoints'] if x['label'] == checkpoint_name)
    candidate = next(x for x in checkpoint['candidates'] if x['probe_name'] == candidate_name)
    anchor_path = folder / (run_name + '_anchor.txt')
    modes, sigma_f, theta_f, alpha_f, scales_f = parse_anchor(anchor_path)
    nt = modes+4; na = 2*modes+3
    theta = list(map(exact, theta_f)); alpha = list(map(exact, alpha_f))
    scales = list(map(exact, scales_f)); delta = list(map(exact, candidate['delta_scaled']))
    displacement = [a*b for a,b in zip(scales,delta)]
    candidate_theta = [a+b for a,b in zip(theta,displacement[:nt])]
    candidate_alpha = [a+b for a,b in zip(alpha,displacement[nt:])]
    sigma = exact(sigma_f)
    taus = [mp.exp(t) for t in theta[:modes]]
    ctaus = [mp.exp(t) for t in candidate_theta[:modes]]
    gammas = [mp.exp(t) for t in theta[modes:modes+2]]
    cgammas = [mp.exp(t) for t in candidate_theta[modes:modes+2]]
    Q = mp.exp(theta[modes+3]); cQ = mp.exp(candidate_theta[modes+3])
    z0 = theta[modes+2]; cz0 = candidate_theta[modes+2]
    v = alpha[modes+2:modes+2+modes].copy()
    cv = candidate_alpha[modes+2:modes+2+modes].copy()
    v_tau = [mp.mpf(0) for _ in range(modes)]
    v_R = [mp.mpf(0) for _ in range(modes)]
    v_initial = [mp.mpf(1) for _ in range(modes)]
    u = alpha[-1]; cu = candidate_alpha[-1]
    u_gamma = [mp.mpf(0),mp.mpf(0)]; u_H = mp.mpf(0); u_initial = mp.mpf(1)
    H = alpha[1+modes]; cH = candidate_alpha[1+modes]
    charge = mp.mpf(0); elapsed = mp.mpf(0)
    E2 = mp.mpf(0); nll_difference = mp.mpf(0)
    affine_nll = mp.mpf(0); nonlinear_nll = mp.mpf(0); max_error = mp.mpf(0)
    # These are the exact binary64 constants used by the C illustrative model,
    # treated as real coefficients before high-precision evaluation.
    ocv_linear = exact(1.15); ocv_tanh = exact(.08)
    coefficients = {}
    data_path = repo / 'data' / (receipt['case_id']+'.csv')
    started = time.monotonic()
    count = checkpoint['samples']
    print(json.dumps({'started':run_name, 'checkpoint':checkpoint_name,
                      'candidate':candidate_name, 'samples':count, 'dps':dps}),flush=True)
    with data_path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        for index, row in enumerate(reader):
            if index >= count: break
            if int(row['sample_index']) != index: raise ValueError('Nonconsecutive index')
            dt_f = float(row['dt_s']); I_f = float(row['current_A'])
            key = (dt_f, I_f)
            if key not in coefficients:
                dt = exact(dt_f); I = exact(I_f)
                pole=[]
                for tau,ctau in zip(taus,ctaus):
                    p=dt/tau; cp=dt/ctau
                    pole.append((mp.exp(-p),-mp.expm1(-p),p*mp.exp(-p),
                                 mp.exp(-cp),-mp.expm1(-cp)))
                active=0 if I>0 else 1
                amount=abs(I)*dt/3600
                p=gammas[active]*amount; cp=cgammas[active]*amount
                he=mp.exp(-p); hdelta=-mp.expm1(-p)
                hysteresis=(he,hdelta,-p*he,mp.exp(-cp),-mp.expm1(-cp))
                coefficients[key]=(dt,I,pole,active,hysteresis)
            dt,I,pole,active,hysteresis=coefficients[key]
            charge += I*dt/3600; elapsed += dt
            for i,(e,om,de,ce,com) in enumerate(pole):
                old = v[i]
                v_tau[i] = e*v_tau[i]+de*(old-alpha[i+1]*I)
                v_R[i] = e*v_R[i]+om*I
                v_initial[i] *= e
                v[i] = e*old+om*alpha[i+1]*I
                cv[i] = ce*cv[i]+com*candidate_alpha[i+1]*I
            if I != 0 and dt != 0:
                sign=1 if I>0 else -1
                he,hom,hde,hce,hcom=hysteresis; old=u
                for i in range(2):
                    u_gamma[i]=he*u_gamma[i]+(hde*(old-H*sign) if i==active else 0)
                u_H=he*u_H+hom*sign; u_initial*=he
                u=he*old+hom*H*sign; cu=hce*cu+hcom*cH*sign
            z=z0-charge/Q; cz=cz0-charge/cQ
            if z<0 or z>1 or cz<0 or cz>1: raise ValueError('SOC domain')
            t=mp.tanh(8*(z-mp.mpf('0.5')))
            ct=mp.tanh(8*(cz-mp.mpf('0.5')))
            ocv=3+ocv_linear*z+ocv_tanh*t
            cocv=3+ocv_linear*cz+ocv_tanh*ct
            slope=ocv_linear+8*ocv_tanh*(1-t*t)
            mu=ocv-alpha[0]*I-sum(v)-u
            cmu=cocv-candidate_alpha[0]*I-sum(cv)-cu
            jac=[-x for x in v_tau]+[-u_gamma[0],-u_gamma[1],slope,slope*charge/Q]
            jac += [-I]+[-x for x in v_R]+[-u_H]+[-x for x in v_initial]+[-u_initial]
            linear=mu+sum(a*b for a,b in zip(jac,displacement))
            error=(cmu-linear)/sigma
            observed=exact(float(row['voltage_V']))
            ra=(linear-observed)/sigma; rn=(cmu-observed)/sigma
            E2+=error*error; nll_difference+=error*ra+error*error/2
            affine_nll+=ra*ra/2; nonlinear_nll+=rn*rn/2
            max_error=max(max_error,abs(cmu-linear))
            if (index+1)%15000==0:
                print(json.dumps({'progress':index+1,'dps':dps,
                                  'elapsed_wall_s':time.monotonic()-started}),flush=True)
    if index+1 < count: raise ValueError('Trace ended early')
    E=mp.sqrt(E2); bound=exact(candidate['remainder']['E_bound'])
    nll_bound=exact(candidate['remainder']['B_bound'])
    candidate_payload=json.dumps({'theta':theta_f,'alpha':alpha_f,'scales':scales_f,
                                 'delta':candidate['delta_scaled']},sort_keys=True,separators=(',',':'))
    return {
        'run':run_name,'checkpoint':checkpoint_name,'candidate':candidate_name,
        'samples':count,'dps':dps,'wall_s':time.monotonic()-started,
        'source_revision':receipt['source_revision'],'source_sha256':receipt['source_sha256'],
        'original_receipt_sha256':sha(receipt_path),'input_csv_sha256':sha(data_path),
        'anchor_sha256':sha(anchor_path),'original_run_sha256':sha(record_path),
        'candidate_payload_sha256':hashlib.sha256(candidate_payload.encode()).hexdigest(),
        'candidate_binary64':{'theta':theta_f,'alpha':alpha_f,'scales':scales_f,
                             'delta':candidate['delta_scaled']},
        'interpretation':'High-precision real-model diagnostic only; original C audit gates remain unchanged',
        'input_conversion':'float.as_integer_ratio, exact binary64 inputs and C OCV literal coefficients',
        'derivatives':'Independent direct polarization/hysteresis-voltage first-derivative recurrences',
        'parameter_construction':'Exact binary64 anchor + exact binary64 scale * exact binary64 delta in high precision',
        'actual_whitened_remainder_norm':mp.nstr(E,dps),
        'actual_signed_NLL_difference':mp.nstr(nll_difference,dps),
        'actual_affine_NLL':mp.nstr(affine_nll,dps),
        'actual_nonlinear_NLL':mp.nstr(nonlinear_nll,dps),
        'prediction_error_RMS_V':mp.nstr(mp.sqrt(E2/count)*sigma,dps),
        'prediction_error_max_V':mp.nstr(max_error,dps),
        'original_double_actual_norm':candidate['actual_whitened_remainder_norm'],
        'original_double_E_bound':candidate['remainder']['E_bound'],
        'original_double_B_bound':candidate['remainder']['B_bound'],
        'real_model_norm_below_recorded_bound':bool(E<=bound),
        'real_model_NLL_difference_below_recorded_bound':bool(abs(nll_difference)<=nll_bound),
        'norm_to_bound_ratio':mp.nstr(E/bound,dps),
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--run',required=True)
    parser.add_argument('--checkpoint',required=True)
    parser.add_argument('--candidate',required=True)
    parser.add_argument('--dps',type=int,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    result=run(args.repo,args.run,args.checkpoint,args.candidate,args.dps)
    result['diagnostic_script_sha256']=sha(Path(__file__))
    result['mpmath_version']=mp.__version__
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ['run','checkpoint','candidate','dps','wall_s',
          'actual_whitened_remainder_norm','actual_signed_NLL_difference',
          'original_double_E_bound','norm_to_bound_ratio',
          'real_model_norm_below_recorded_bound']}),flush=True)


if __name__=='__main__': main()
