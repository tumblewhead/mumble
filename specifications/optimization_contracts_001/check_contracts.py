"""Exact examples and failure witnesses for optimization proof contracts.

These checks do not run or certify an optimized estimator.
"""
from fractions import Fraction as F
from itertools import product
from math import isqrt
import json


def run():
    groups = {}

    # K1: extremal additive defects attain the propagated bound, so replacing
    # it with the largest single defect would be unsound.
    propagation_cases = 0
    for gains in product((F(1, 2), F(1), F(2)), repeat=3):
        for signs in product((-1, 1), repeat=3):
            reference, candidate, bound = F(1), F(1), F(0)
            for gain, sign in zip(gains, signs):
                reference = gain*reference+1
                candidate = gain*candidate+1+sign*F(1, 10)
                bound = gain*bound+F(1, 10)
                assert abs(candidate-reference) <= bound
            if signs == (1, 1, 1):
                assert candidate-reference == bound
            propagation_cases += 1
    delta = F(1, 10)
    decision_cases = 0
    for margin in (F(n, 20) for n in range(-6, 7)):
        for error in (-delta, F(0), delta):
            candidate = margin+error
            if candidate >= delta:
                assert margin >= 0
            if margin >= 2*delta:
                assert candidate >= delta
            decision_cases += 1
    assert F(1, 100) > 0 > F(-1, 100)  # arbitrarily small decision-flip pair
    groups['K1_propagation_and_margins'] = dict(propagation_cases=propagation_cases, decision_cases=decision_cases)

    # K2: multiplying allowable precision distortions is necessary even in 1D.
    epsilon = F(1, 10)
    precision = (1+epsilon)**2
    assert precision == F(121, 100)
    assert precision > 1+2*epsilon
    points = [F(i, 1000) for i in range(101)]
    assert all(abs(b-a) == F(1, 1000) for a, b in zip(points, points[1:]))
    assert points[-1]-points[0] == F(1, 10)
    groups['K2_composition'] = dict(precision_upper='121/100', incorrect_additive_upper='6/5', parent_step='1/1000', anchor_drift='1/10')

    # K3: a deliberately incomplete key returns a wrong value after temperature
    # changes, although the observed current and parameter version are unchanged.
    def kernel(current, temperature, parameter):
        return parameter*temperature+current
    first, second = (F(1), F(2), F(3)), (F(1), F(4), F(3))
    incomplete = lambda x: (x[0], x[2])
    assert incomplete(first) == incomplete(second)
    assert kernel(*first) != kernel(*second)
    cache = {first: kernel(*first)}
    assert second not in cache
    # L=3 in temperature, reuse within a half-unit bucket incurs <=3/2.
    assert abs(kernel(F(1), F(5, 2), F(3))-kernel(*first)) == F(3, 2)
    groups['K3_cache_dependency'] = dict(missing_temperature_counterexample=True, bounded_bucket_error='3/2')

    # K4: including the failure reader changes whether reuse is legal.
    def overlap(a, b):
        return max(a[0], b[0]) <= min(a[1], b[1])
    old_normal, old_with_rollback, new = (0, 2), (0, 5), (3, 6)
    assert not overlap(old_normal, new)
    assert overlap(old_with_rollback, new)
    old_value, new_value = F(7), F(11)
    aliased_slot = new_value
    assert aliased_slot != old_value  # rollback reader observes corrupted backup
    groups['K4_lifetime'] = dict(ordinary_reuse_legal=True, rollback_reuse_legal=False)

    # K5: illustrative costs only, not measured processor cycles.
    compute, lookup, fill, hit = 10, 1, 2, 1
    miss = compute+lookup+fill
    assert hit < compute < miss
    block_costs = [16]*9+[96]
    average = F(sum(block_costs), len(block_costs))
    assert average < 32 < max(block_costs)
    groups['K5_resource_counterexamples'] = dict(cache_hit=hit, uncached=compute, cache_miss=miss, average_block=str(average), worst_block=max(block_costs), illustrative_deadline=32)

    # K6: exact same final nonlinear objective; one GN step versus an earlier
    # prefix refresh followed by another step at the new anchor.
    def gn(x, data):
        return x+(sum(data)/len(data)-x*x)/(2*x)
    data = (F(4), F(9))
    final_only = gn(F(1), data)
    refreshed = gn(gn(F(1), data[:1]), data)
    assert final_only == F(15, 4)
    assert refreshed == F(51, 20)
    assert final_only != refreshed
    groups['K6_refresh_cadence'] = dict(final_only=str(final_only), prefix_then_final=str(refreshed), same_final_data=True)

    # K7: exact invertible feature change; retained precision is a Schur
    # complement, not the diagonal block. Conditional normalizers also differ.
    cases = 0
    for x, y in product((F(-1), F(0), F(1, 3), F(2)), repeat=2):
        original = 3*x-y
        changed = 2*(2*x)-(x+y)
        assert original == changed
        cases += 1
    A, B, D = F(2), F(1), F(2)
    retained = A-B*B/D
    assert retained == F(3, 2) and retained != A
    for x in (F(-2), F(0), F(1, 3), F(3)):
        y = -B*x/D
        original = A*x*x/2+B*x*y+D*y*y/2
        assert original == retained*x*x/2
    # Integral exp(-D*y*y/2) is proportional to D^-1/2; D=1 versus4.
    mass_ratio = F(isqrt(1), isqrt(4))
    assert mass_ratio == F(1, 2)
    groups['K7_representation'] = dict(basis_cases=cases, exact_retained_precision=str(retained), wrong_diagonal_precision=str(A), marginal_mass_ratio_for_D4_vs_D1='1/2')
    return dict(status='exact_finite_examples_pass', groups=groups,
                scope='Supporting finite examples only; no optimized estimator, target resource or universal program proof.')


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
