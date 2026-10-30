"""Targeted causal observability control for a fixed four-knot natural spline.

The first piece has only constant, linear and cubic terms because its left
second derivative is zero. Four knot values therefore include at least one
direction unobservable from that piece alone. The Gaussian prior is a declared
dimensionless toy control, not the battery prior.
"""
import json
from pathlib import Path
import shutil
import numpy as np
from .centroid import basis
from .qualify import HERE, ROOT, Census, ident, write


def main():
    dest=HERE/'causal001';dest.mkdir(exist_ok=False)
    sources=[HERE/'centroid.py',Path(__file__),HERE/'qualify.py']
    identities={str(p.relative_to(ROOT)):ident(p) for p in sources}
    write(dest/'reservation.json',dict(scope='First-piece unobservability and retained uncertainty',
          hypotheses=dict(knots=[0.,1/3,2/3,1.],observations=12,observed_time_end=.25,
                          coefficient_prior_covariance='identity4',noise_variance=.04),
          source_identities=identities,command='python3 -B -m experiments.operator_envelope_001.centroid_prefix'))
    for p in sources:
        target=dest/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    c=Census();knots=np.linspace(0,1,4);B=basis(np.linspace(0,.25,12),knots)
    _,singular,V=np.linalg.svd(B,full_matrices=False);null=V[-1]
    c.close('first_piece/null_observation_direction',B@null,np.zeros(12),atol=2e-12,rtol=0)
    c.check('first_piece/three_resolved_basis_directions',singular[-2]>.001 and singular[-1]<2e-12)
    future=basis([.7,1.],knots)@null
    c.check('future/null_direction_changes_prediction',np.max(abs(future))>.1)
    covariance=np.linalg.solve(np.eye(4)+B.T@B/.04,np.eye(4))
    c.close('uncertainty/unobserved_direction_retains_prior',null@covariance@null,1.)
    c.check('uncertainty/observed_directions_gain_information',np.trace(covariance)<4)
    for p,expected in identities.items():c.check('source/'+p,ident(ROOT/p)==expected)
    result=dict(status='passed' if all(q['passed'] for q in c.checks) else 'failed',checks=c.checks,
                singular_values=singular.tolist(),unobserved_direction=null.tolist(),future_response=future.tolist(),
                unobserved_direction_variance=float(null@covariance@null),
                implication='Do not treat all future trajectory coefficients as identified from early-prefix data',
                actual_battery_inference=False)
    write(dest/'result.json',result)
    print(json.dumps(dict(status=result['status'],checks=len(c.checks))))
    return result['status']!='passed'


if __name__=='__main__':raise SystemExit(main())
