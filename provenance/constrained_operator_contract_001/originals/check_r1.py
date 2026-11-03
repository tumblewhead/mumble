"""Finite independent witnesses for paper contracts; not a firmware implementation."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np

BASE = Path(__file__).resolve().parents[2]


def nonnegative_halfline(A, B, C):
    return A >= 0 and C >= 0 and (B >= 0 or B*B <= 4*A*C)


def qr_pass(root, row, write=False, stop_after=None):
    """Scalar validation/replay witness; stop models a detected post-write fault."""
    x = row.copy()
    count = 0
    for k in range(len(x)):
        h = np.hypot(root[k, k], x[k])
        c, s = (1., 0.) if h == 0 else (root[k, k]/h, x[k]/h)
        for j in range(k, len(x)):
            old, incoming = root[k, j], x[j]
            new = c*old+s*incoming
            remaining = -s*old+c*incoming
            if not (np.isfinite(new) and np.isfinite(remaining)):
                raise ValueError('nonfinite candidate')
            x[j] = remaining
            if write:
                root[k, j] = new
                count += 1
                if stop_after == count:
                    raise InterruptedError('detected mutation failure; quarantine')
    return x


def memory():
    persistent = dict(factor=4760, response=312, centres=40, halfwidths=40,
        calibration=112, count=8, source_digest_assumption=32, normalizer=8,
        prior_mean=128, prior_scale_diagonal=128, projection_p1=72,
        projection_p2=432, nodes=24, rate_cache=120)
    scratch = {
        'stream': dict(staged_response=312, held_sample=40, row=272),
        'fit': dict(augmented_root=1224, features=272, derivative=128,
                    augmented_row=136, current_trial_step=384, scalars=64),
        'query': dict(augmented_root=1224, theta=128, state_sensitivity=680,
                      two_solves=256, result=8, scalars=56)}
    p = sum(persistent.values())
    totals = {k:p+sum(v.values()) for k,v in scratch.items()}
    assert p == 6216 and totals == dict(stream=6840, fit=8424, query=8568)
    return dict(persistent=persistent, scratch=scratch, named_phase_B=totals,
        serialized_named_peak_B=max(totals.values()), target_B=10240,
        unallocated_not_measured_free_B=10240-max(totals.values()),
        full_prior_increment_B=960, full_prior_named_peak_B=9528,
        full_prior_unallocated_B=712,
        exclusions='See P3: helpers, alignment, stack, metadata, queues/ISR, outputs, recovery, certificates. No full target qualification.')


def run():
    counts = {}
    # Exact rational sample identities, plus all-interval proof in P1.
    count = 0
    for numerator in range(-16,17):
        t=F(numerator,64);alpha=t-t*t/2;beta=t*t/2
        assert nonnegative_halfline(1-alpha,alpha-2*beta,beta)
        assert nonnegative_halfline(1,2-2*alpha-6*beta,1-2*alpha+2*beta)
        assert 4*(1-alpha)*beta-(alpha-2*beta)**2 == t*t*(1+t-5*t*t/4)
        count += 1
    counts['exact_local_feasibility_points']=count
    # Independent complex transfer evaluation against expanded real-part formula.
    rng=np.random.default_rng(20261102);largest=0.
    for _ in range(200):
        alpha,beta=rng.uniform(-2,2,2);w=rng.uniform(-8,8);v=1+1j*w
        G=(1-alpha)/v+(alpha-2*beta)/v**2+2*beta/v**3
        y=w*w;reference=(1+(2-2*alpha-6*beta)*y+(1-2*alpha+2*beta)*y*y)/(1+y)**3
        largest=max(largest,abs(G.real-reference));assert abs(G.real-reference)<4e-15
    counts['frequency_identity_points']=200
    s=-2*np.tanh(.5);alpha=s-s*s/2;beta=s*s/2
    assert not nonnegative_halfline(1-alpha,alpha-2*beta,beta)
    counts['preserved_Cayley_rejection']=1

    # Bitwise replay vs copied-factor scalar reference, plus independent Gram check.
    maxgram=0.;faults=0
    for size in [1,5,17,34]:
        A=rng.normal(size=(size+4,size));U=np.linalg.qr(A,mode='reduced')[1]
        x=rng.normal(size=size);saved=U.copy();oracle=U.copy()
        qr_pass(oracle,x,write=True);qr_pass(U,x)
        assert np.array_equal(U,saved)
        qr_pass(U,x,write=True);assert np.array_equal(U,oracle)
        error=np.linalg.norm(U.T@U-(saved.T@saved+np.outer(x,x)))
        maxgram=max(maxgram,float(error));assert error<2e-12
        for entry in [0,size-1]:
            invalid=x.copy();invalid[entry]=np.nan;old=saved.copy()
            try:qr_pass(old,invalid)
            except ValueError:pass
            else:raise AssertionError('must reject nonfinite')
            assert np.array_equal(old,saved)
        for stop in range(1,size*(size+1)//2+1):
            tentative=saved.copy();status='updating'
            try:qr_pass(tentative,x,write=True,stop_after=stop)
            except InterruptedError:status='quarantined'
            assert status=='quarantined' # Toy authority witness, not a runtime guard.
            faults+=1
    counts['QR_sizes']=4;counts['anticipated_nonfinite_rejections']=8
    counts['postwrite_fault_positions_quarantined_in_model']=faults

    # Joint row recomputation vs a dense augmented QR oracle with full prior.
    W,p=34,16;U=np.triu(rng.normal(size=(W,W)))
    phi=rng.normal(size=W);D=rng.normal(size=(W,p));prior=np.triu(rng.normal(size=(p,p)))+5*np.eye(p)
    pr=rng.normal(size=p);dense=np.c_[U@D,U@phi];stack=np.vstack([dense,np.c_[prior,pr]])
    S=np.zeros((p+1,p+1))
    for i in range(W):
        derivative=np.zeros(p);residual=0.
        for j in range(i,W):derivative+=U[i,j]*D[j];residual+=U[i,j]*phi[j]
        qr_pass(S,np.r_[derivative,residual],write=True)
    for row in np.c_[prior,pr]:qr_pass(S,row,write=True)
    Sd=np.linalg.qr(stack,mode='reduced')[1]
    np.testing.assert_allclose(S.T@S,Sd.T@Sd,atol=3e-12,rtol=3e-13)
    R=S[:p,:p];c=S[:p,p];step=np.linalg.solve(R,-c)
    reference=np.linalg.lstsq(stack[:,:p],-stack[:,p],rcond=None)[0]
    np.testing.assert_allclose(step,reference,atol=2e-13,rtol=2e-12)
    g1,g2=rng.normal(size=(2,p));y1=np.linalg.solve(R.T,g1);y2=np.linalg.solve(R.T,g2)
    cov=g1@np.linalg.solve(stack[:,:p].T@stack[:,:p],g2)
    assert abs(y1@y2-cov)<2e-14
    counts['dense_joint_step_and_covariance_controls']=1

    # Affine P2 controls, full cross terms, and the independent review counterexample.
    maxcovratio=0.
    for _ in range(100):
        J=rng.normal(size=(25,5));E=.015*rng.normal(size=J.shape);y=rng.normal(size=25);e0=.03*rng.normal(size=25)
        P=np.eye(5)+J.T@J;Ph=np.eye(5)+(J+E).T@(J+E)
        ev,V=np.linalg.eigh(P);isqrt=(V/np.sqrt(ev))@V.T;sqrt=(V*np.sqrt(ev))@V.T
        theta=np.linalg.solve(P,J.T@y);th=np.linalg.solve(Ph,(J+E).T@(y-e0))
        r=J@theta-y;e=E@theta+e0;dg=J.T@e+E.T@r+E.T@e
        b=isqrt@dg;A=isqrt@(Ph-P)@isqrt;eps=np.linalg.norm(A,2)
        assert eps<1 and np.linalg.norm(sqrt@(th-theta))<=np.linalg.norm(b)/(1-eps)+1e-13
        G=rng.normal(size=(2,5));dG=.01*rng.normal(size=G.shape);T=G@isqrt;Dq=dG@isqrt
        C=G@np.linalg.solve(P,G.T);Ch=(G+dG)@np.linalg.solve(Ph,(G+dG).T)
        bound=(eps*np.linalg.norm(T,2)**2+2*np.linalg.norm(T,2)*np.linalg.norm(Dq,2)+np.linalg.norm(Dq,2)**2)/(1-eps)
        actual=np.linalg.norm(Ch-C,2);assert actual<=bound+1e-13
        maxcovratio=max(maxcovratio,float(actual/bound))
    counts['affine_joint_controls']=100
    # r=3theta/4, rhat=theta/4-4; prior 7/16 theta^2/2; support disconnected.
    lam=F(7,16);P=lam+F(3,4)**2;Ph=lam+F(1,4)**2
    assert P==1 and Ph==F(1,2)
    bound=F(1)/(1-F(1,2));assert F(3)>bound
    cost=lambda t:lam*t*t/2+(t/4-4)**2/2
    assert cost(F(3))<cost(F(1,10))
    counts['nonstationary_support_counterexample']=1
    return dict(status='finite_contract_witnesses_passed_not_C_qualification',checks=counts,
        frequency_identity_max_abs=largest,QR_Gram_max_abs_norm=maxgram,
        covariance_bound_max_fraction=maxcovratio,memory=memory(),
        scope='No new battery fit, candidate selection, uniform numeric certificate, C port, or target timing. Fault tests model detected interruptions, not detection hardware.')


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if args.out.exists():raise ValueError('preserve original result')
    result=run()
    paths=[Path(__file__).relative_to(BASE)]+list(Path('specifications/constrained_operator_contract_001').glob('*.md'))
    result['sha256']={str(p):hashlib.sha256((BASE/p).read_bytes()).hexdigest() for p in sorted(paths)}
    result['base_revision']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ['status','checks']},indent=2))


if __name__=='__main__':main()
