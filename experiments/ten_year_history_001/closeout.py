"""Bind the written foundation and its finite numerical witnesses."""
import json
from pathlib import Path
from experiments.region_compression_001 import compare as base

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PROOF=ROOT/'proofs/ten_year_history_001'


def main():
    reservation=json.loads((HERE/'attempt001/reservation.json').read_text())
    result=json.loads((HERE/'attempt001/result.json').read_text())
    for path,expected in reservation['identities'].items():
        assert base.identity(ROOT/path)==expected,path
    assert all(c['passed'] for c in result['checks'])
    claims=json.loads((PROOF/'claims.json').read_text())
    assert len(claims['claims'])==13
    assert not claims['current_ten_year_battery_claim']
    summary=dict(schema='ten_year_history_foundation_summary_v1',
        status='foundation_written_conditional_proofs_and_finite_witnesses_only',
        contract='proofs/ten_year_history_001/contract.json',lemmas='proofs/ten_year_history_001/lemmas.md',
        claims='proofs/ten_year_history_001/claims.json',error_model='proofs/ten_year_history_001/error_model.json',
        gallery='proofs/ten_year_history_001/gallery.md',roadmap='proofs/ten_year_history_001/roadmap.json',
        report='experiments/ten_year_history_001/README.md',
        result='experiments/ten_year_history_001/attempt001/result.json',
        figure='experiments/ten_year_history_001/attempt001/error_mechanisms.pdf',
        written_conditional_lemmas=13,finite_checks_passed=len(result['checks']),
        proof_status='Written derivations, not proof-assistant or independent-review certification',
        user_scope=dict(horizon_years=10,C='RC-branch capacitances tau_i/R_i',
            proposed_relative_envelope=[.5,1.5],likely_sensitivity_range=[.7,1.3],calibrated_envelope=False),
        principal_results=[
            'Exact finite-span repeated likelihoods can eliminate raw records while retaining summed coefficients and multiplicity',
            'Chronological Markov elimination is associative; event histograms generally lose order/state',
            'Aging changes current relevance through an admitted transition, not an arbitrary discount',
            'Lifetime error follows a local-defect/stability recurrence; storage size alone gives no error guarantee',
            'Envelope-only assumptions cannot guarantee useful health tracking under weak stimulus',
            'Recent short-prefix/horizon comparisons do not identify a calendar-time error growth law'],
        inherited_product_targets='plans/estimation_targets_001.json',
        nominal_record_ranges=result['evidence']['nominal_ten_year_ranges'],
        storage_B=result['evidence']['storage_B'],
        immediate_next='P1 incremental prior-free rolling token with explicit ownership/chronology, backed by P2 exact elimination reference; no further empirical model sweep before closure/error obligations',
        open_obligations=['Physical aging uncertainty/rate and RC state-transfer convention',
            'Useful physical query-error allocation and excitation/availability conditions',
            'Finite battery-gallery closure and local approximation defects',
            'Actual stability bounds, maximum delivery rate, finite arithmetic and complete SRAM'],
        new_battery_fits=0,rolling_solver_changed=False,ten_year_simulation=False,
        ten_year_battery_certificate=False,coverage_validated=False,deployment_qualified=False,
        primary_sources=[
            dict(title='Uniform observability of hidden Markov models and filter stability for unstable signals',url='https://arxiv.org/abs/0804.2885',role='Context only; battery hypotheses not established'),
            dict(title='Nonlinear Filtering and Systems Theory',url='https://web.math.princeton.edu/~rvan/mtns10.pdf',role='Context on finite representation and stability'),
            dict(title='Automated Scalable Bayesian Inference via Hilbert Coresets',url='https://jmlr.org/papers/v20/17-613.html',role='Context on function-space redundancy and weighted coresets'),
            dict(title='General bounds on the quality of Bayesian coresets',url='https://arxiv.org/abs/2405.11780',role='Context on assumptions and approximation limitations')])
    base.write(HERE/'summary.json',summary)
    files=[p for directory in [HERE,PROOF] for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='verification.json']
    base.write(HERE/'verification.json',dict(status='passed',finite_checks=len(result['checks']),
        preserved_source_count=len(reservation['identities']),
        artifacts={str(p.relative_to(ROOT)):base.identity(p) for p in sorted(files)},
        scope='Source hashes, claim status and finite witness checks; does not certify universal lemmas, physical aging premises or ten-year battery accuracy'))
    print(json.dumps(dict(lemmas=13,finite_checks=len(result['checks']),artifacts=len(files))))


if __name__=='__main__':main()
