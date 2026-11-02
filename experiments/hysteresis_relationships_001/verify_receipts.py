"""Recompute identities from serialized records; catches mutable-prefix aliasing."""
import argparse
import json
from pathlib import Path
import numpy as np


def verify_moments(report):
    failures=[];count=0
    for case in report['cases']:
        for record in case['prefixes']:
            count+=1;g=np.array(record['C_jacobian_gradient_difference']);prediction=np.array(record['charge_moment_gradient_prediction'])
            actual=float(np.linalg.norm(g-prediction)/max(1,np.linalg.norm(prediction)))
            if actual>1e-7 or abs(actual-record['relative_gradient_identity_error'])>1e-12:
                failures.append(dict(load=case['load'],records=record['records'],error='serialized_gradient_identity_mismatch',recomputed_relative_error=actual))
            fit=record['conditional_two_parameter_fit']
            if record['weighted_signed_charge_variance_Ah2']==0:
                if fit['status']!='unresolved_zero_charge_variation':failures.append(dict(error='rank_failure_not_reported'))
            else:
                shift=np.array(fit['observed_delta_z0_q']);pred=np.array(fit['predicted_delta_z0_q'])
                fromfits=np.array(fit['approximate_z0_q'])-np.array(fit['reference_z0_q'])
                if not np.allclose(shift,pred,rtol=1e-7,atol=1e-10) or not np.allclose(shift,fromfits,rtol=1e-7,atol=1e-10):
                    failures.append(dict(load=case['load'],records=record['records'],error='serialized_fit_displacement_mismatch'))
    return dict(status='pass' if not failures else 'fail',prefix_records=count,failures=failures)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('receipt',type=Path);args=p.parse_args()
    result=verify_moments(json.loads(args.receipt.read_text()));print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='pass' else 1)

if __name__=='__main__':main()
