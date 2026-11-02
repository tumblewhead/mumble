"""Finite examples guarding reviewed premises; not universal program proofs."""
from fractions import Fraction as F
from math import copysign
import json


def sub(a, b):
    return [[x-y for x, y in zip(ar, br)] for ar, br in zip(a, b)]


def scale(c, a):
    return [[c*x for x in row] for row in a]


def mul(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(2)) for j in range(2)] for i in range(2)]


def det(a):
    return a[0][0]*a[1][1]-a[0][1]*a[1][0]


def psd(a):
    # Exact 2x2 symmetric principal-minor criterion.
    return a[0][1] == a[1][0] and a[0][0] >= 0 and a[1][1] >= 0 and det(a) >= 0


def inverse(a):
    d = det(a)
    assert d > 0
    return scale(1/d, [[a[1][1], -a[0][1]], [-a[1][0], a[0][0]]])


def run():
    out = {}
    # K0: a transition relation can satisfy a universal condition vacuously.
    candidate_transitions = []
    assert all(t == 'reference_step' for t in candidate_transitions)
    assert not candidate_transitions
    out['K0_enabledness_counterexample'] = 'Vacuous all-steps condition does not imply an enabled step.'

    # K3: local numeric equality is not a congruence for every downstream observer.
    assert 0.0 == -0.0
    assert copysign(1.0, 0.0) != copysign(1.0, -0.0)
    representative, stored, actual = F(2), F(11, 5), F(1, 2)
    assert abs(stored-actual) == F(17, 10)
    assert abs(stored-actual) == abs(stored-representative)+abs(representative-actual)
    out['K3_congruence_and_stored_error'] = 'Signed-zero observer distinguishes equality; reuse includes stored-value error.'

    # K2: exact checks on noncommuting SPD matrices, including inverse order.
    p0 = [[F(2), F(1)], [F(1), F(2)]]
    p1 = [[F(21, 10), F(1)], [F(1), F(19, 10)]]
    p2 = [[F(21, 10), F(21, 20)], [F(21, 20), F(19, 10)]]
    lo, hi = F(9, 10), F(11, 10)
    for a, b in ((p0, p1), (p1, p2)):
        assert psd(sub(b, scale(lo, a)))
        assert psd(sub(scale(hi, a), b))
    assert mul(p1, p2) != mul(p2, p1)
    assert psd(sub(p2, scale(lo**2, p0)))
    assert psd(sub(scale(hi**2, p0), p2))
    c0, c2 = inverse(p0), inverse(p2)
    assert psd(sub(c2, scale(1/hi**2, c0)))
    assert psd(sub(scale(1/lo**2, c0), c2))
    out['K2_noncommuting_precision'] = 'Exact forward and reciprocal covariance inequalities pass.'

    # K5/D4: average capacity and an enclosure-completion deadline omit latency.
    job, service_in_window, later_service = 5, 0, 20
    assert (service_in_window+later_service)/2 > job
    assert service_in_window < job
    build, publication, deadline = 10, 1, 10
    assert build <= deadline and build+publication > deadline
    assert 9+publication <= deadline
    out['K5_D4_deadline_counterexamples'] = 'Average service and build-only deadline both fail; total budget catches them.'

    # D5: global support can preserve useful narrowness without a drift rate.
    low, high = F(999, 1000), F(1)
    tol, midpoint = F(1, 1000), (low+high)/2
    assert max(abs(midpoint-low), abs(midpoint-high)) <= tol
    out['D5_endpoint_narrowness'] = 'Monotone increase plus [0,1] support preserves [0.999,1].'

    # D7: retaining the bytes of an invalid object does not authorize exit.
    invalid_object = ('partial_count', 'old_factor')
    after = invalid_object
    assert after == invalid_object
    validity, quarantine = False, True
    assert not validity and quarantine
    # Clearing quarantine with no verified valid commit breaks the invariant.
    assert not (validity or False)
    out['D7_quarantine_persistence'] = 'Preserve-object transition must also preserve disabled authorization.'

    # K7: minimizing over bounded support is not the unconstrained profile.
    # F(y)=(y+1)^2/2 increases on [0,1], so its constrained minimum is F(0).
    objective = lambda y: (y+1)**2/F(2)
    assert objective(F(-1)) == 0
    assert objective(F(0)) == F(1, 2)
    for i in range(11):
        assert objective(F(i, 10)) >= objective(F(0))
    out['K7_constrained_profile'] = 'Constrained minimum1/2 differs from unconstrained minimum0.'

    # D2/D4: selecting only errors can inflate conditional failure probability.
    alpha, selected_mass, error_and_selected = F(1, 100), F(1, 100), F(1, 100)
    assert error_and_selected <= alpha
    assert error_and_selected/selected_mass == 1
    out['D2_selection_scope'] = 'Unconditional risk1/100 does not imply conditional-on-selection risk1/100.'

    # D6: a downward-rounded monitor bound can understate its own exact defect.
    exact, rounded_down, rounded_up = F(1, 3), F(3, 10), F(4, 10)
    assert rounded_down < exact <= rounded_up
    out['D6_bound_arithmetic'] = 'The bound engine also needs outward arithmetic.'
    return {'status': 'finite_review_examples_pass', 'groups': out,
            'scope': 'Exact finite examples except explicit binary64 signed-zero witness; not full implementation proof.'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
