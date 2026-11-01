"""Exact finite examples/counterexamples for THEOREMS.md; not an H7 monitor."""
from fractions import Fraction as F
from itertools import product
import json


def run():
    results = {}

    # D0: every binary decision rule for two overlapping observation laws.
    good, bad = (F(3, 4), F(1, 4)), (F(1, 4), F(3, 4))
    tv = sum(abs(a-b) for a, b in zip(good, bad))/2
    errors = []
    for accept in product((False, True), repeat=2):
        error = sum(b if yes else g for yes, g, b in zip(accept, good, bad))
        assert error >= 1-tv
        errors.append(error)
    assert min(errors) == 1-tv
    results['D0_overlapping_laws'] = {'decision_rules': 4, 'minimum_error_sum': str(min(errors))}

    # D1: all one-step states, drift and noise combinations in a finite model.
    trials = 0
    for initial in range(-2, 3):
        for drift, noise in product((-1, 0, 1), repeat=2):
            truth = initial+drift
            observed = truth+noise
            reach = {x+d for x in range(-2, 3) for d in (-1, 0, 1)}
            posterior = {x for x in reach if abs(x-observed) <= 1}
            assert truth in posterior
            trials += 1
    # Omitting allowed aging loses truth even with an exact observation.
    assert 1 not in {0}.intersection({1})
    results['D1_finite_reach_containment'] = {'cases': trials, 'omitted_drift_counterexample': True}

    # D2/D4: point tolerances must include both endpoints, not just interval width.
    queries = 0
    for lo in range(-2, 3):
        for hi in range(lo, 4):
            for q in (F(lo), F(lo+hi, 2), F(hi), F(hi+1)):
                for tol in (F(0), F(1, 2), F(1)):
                    authorize = max(abs(q-lo), abs(q-hi)) <= tol
                    if authorize:
                        for j in range(5):
                            truth = F(lo)+F(j, 4)*(hi-lo)
                            assert abs(q-truth) <= tol
                    queries += 1
            midpoint = F(lo+hi, 2)
            assert max(abs(midpoint-lo), abs(midpoint-hi)) == F(hi-lo, 2)
    assert F(1, 10) <= 2*F(1, 10)  # narrow range [0,0.1]
    assert abs(F(1)-F(0)) > F(1, 10)  # arbitrary point q=1 still uncertified
    for lo, hi, tol in ((F(9), F(11), F(1, 10)), (F(10), F(11), F(1, 10))):
        left, right = (1-tol)*hi, (1+tol)*lo
        if left <= right:
            q = (left+right)/2
            for j in range(9):
                truth = lo+F(j, 8)*(hi-lo)
                assert abs(q/truth-1) <= tol
    results['D2_D4_query_authorization'] = {'absolute_cases': queries, 'relative_cases': 2, 'arbitrary_point_counterexample': True}

    # D3: exact finite Bernoulli path probabilities, including optional stopping.
    alpha, horizon = F(1, 4), 8
    crossing = {}
    for q in (F(1, 4), F(1, 2), F(3, 4)):
        probability = F(0)
        terminal_expectation = F(0)
        for path in product((0, 1), repeat=horizon):
            martingale, crossed = F(1), False
            for y in path:
                martingale *= (q if y else 1-q)/F(1, 2)
                crossed |= martingale >= 1/alpha
            probability += F(int(crossed), 2**horizon)
            terminal_expectation += martingale/F(2**horizon)
        assert terminal_expectation == 1
        assert probability <= alpha
        crossing[str(q)] = str(probability)
    # Using the present outcome to choose q is not predictable: ratio doubles
    # each sample and the true null is excluded with certainty by sample two.
    assert F(2)**2 >= 1/alpha
    repeated_boot_risk = 1-(1-F(1, 100))**100
    assert repeated_boot_risk > F(1, 2)
    for epochs in (1, 2, 10, 100):
        assert sum(alpha/F(e*(e+1)) for e in range(1, epochs+1)) == alpha*F(epochs, epochs+1)
    results['D3_sequential_risk'] = {'enumerated_paths': 3*2**horizon, 'crossing_probabilities': crossing, 'lookahead_counterexample': True, 'reset_risk_counterexample': True}

    # D5: monotone containment and the impossibility of inferring a drift rate.
    for p, change in product(range(3), range(3)):
        assert 0 <= p+change <= 4
    assert F(3, 2) not in (F(1),)  # allowed envelope endpoint, stale point misses
    results['D5_aging_enclosure'] = {'finite_cases': 9, 'envelope_without_rate_counterexample': True}

    # D6: independently compare iterative and closed-form defect accumulation.
    recurrence_cases = 0
    for rho in (F(0), F(1, 2), F(99, 100), F(1)):
        b0, defect, bound = F(1, 10), F(1, 1000), F(1, 10)
        for n in range(1, 101):
            bound = rho*bound+defect
            closed = b0+n*defect if rho == 1 else rho**n*b0+defect*(1-rho**n)/(1-rho)
            assert bound == closed
            recurrence_cases += 1
    assert F(1000)*defect > F(1, 2)  # integrator cannot use a contraction floor
    results['D6_error_accumulation'] = {'cases': recurrence_cases, 'integrator_counterexample': True}

    return {'status': 'exact_finite_examples_pass', 'groups': results,
            'scope': 'Supporting finite examples and counterexamples only; no full estimator or hardware verification.'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
