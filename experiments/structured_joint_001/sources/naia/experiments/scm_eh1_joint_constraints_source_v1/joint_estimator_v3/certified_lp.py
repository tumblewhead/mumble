"""Certified projections of a finite, represented floating-point polytope.

The input doubles denote exact rational numbers.  This module does NOT certify
the model-to-row construction.  SciPy is only a multiplier proposer: no primal
solution, optimum, success flag, or infeasibility status is a proof here.

For A x <= b, x in [lo, hi], and any lambda >= 0,
  c x <= lambda b + support_box(c - A.T lambda).
Every operation in this certificate is evaluated with fractions.Fraction.
"""
from fractions import Fraction
import math
import numpy as np
from scipy.optimize import linprog


def _f(x):
    return Fraction.from_float(float(x))


def _inputs(A, b, lo, hi):
    A = np.asarray(A, dtype=float)
    b = np.asarray(b, dtype=float)
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    if lo.ndim != 1 or not len(lo) or hi.shape != lo.shape:
        raise ValueError('invalid box shape')
    if A.size == 0:
        A = np.empty((0, len(lo)), dtype=float)
    if A.ndim != 2 or A.shape[1] != len(lo) or b.shape != (A.shape[0],):
        raise ValueError('invalid row shape')
    if not all(np.all(np.isfinite(v)) for v in (A, b, lo, hi)):
        raise ValueError('nonfinite represented polytope')
    if np.any(lo > hi):
        raise ValueError('input box is inverted')
    return A, b, lo, hi


def _support(c, lo, hi):
    return sum((a * (h if a >= 0 else l) for a, l, h in zip(c, lo, hi)), Fraction(0))


def _certificate(A, b, lo, hi, c, multipliers):
    residual = list(c)
    rhs = Fraction(0)
    for row, bound, weight in zip(A, b, multipliers):
        if weight < 0:
            raise ValueError('negative certificate multiplier')
        if weight == 0:
            continue
        rhs += weight * bound
        for j, a in enumerate(row):
            residual[j] -= weight * a
    return rhs + _support(residual, lo, hi)


def certified_upper(A, b, lo, hi, c, multipliers):
    """Return an exact Fraction upper bound for supplied nonnegative multipliers.

    Arbitrary (even useless or adversarial) nonnegative multipliers are sound;
    residual correction is never omitted.  Invalid/nonfinite inputs reject.
    """
    A, b, lo, hi = _inputs(A, b, lo, hi)
    c = np.asarray(c, dtype=float)
    multipliers = np.asarray(multipliers, dtype=float)
    if c.shape != lo.shape or multipliers.shape != b.shape:
        raise ValueError('invalid objective/multiplier shape')
    if not np.all(np.isfinite(c)) or not np.all(np.isfinite(multipliers)):
        raise ValueError('nonfinite objective/multiplier')
    return _certificate(
        [[_f(a) for a in row] for row in A], [_f(v) for v in b],
        [_f(v) for v in lo], [_f(v) for v in hi],
        [_f(v) for v in c], [_f(v) for v in multipliers])


def _up(r):
    v = float(r)
    if not math.isfinite(v):
        raise OverflowError('certificate conversion overflow')
    if _f(v) < r:
        v = np.nextafter(v, np.inf)
    return float(v)


def _down(r):
    v = float(r)
    if not math.isfinite(v):
        raise OverflowError('certificate conversion overflow')
    if _f(v) > r:
        v = np.nextafter(v, -np.inf)
    return float(v)


def project(A, b, lo, hi, indices=None, *, proposer=None):
    """Return (new_lo, new_hi, report) using exact certified coordinate bounds.

    report['empty'] is true ONLY for an exact row/box contradiction or a verified
    dual coordinate bound contradicting the retained box.  In that case bounds
    are left finite and unchanged at the point of detection; the caller must
    act on the explicit flag rather than interpreting them as a feasible set.
    A failed/infeasible optimizer merely leaves that query at its box bound.
    """
    A, b, lo, hi = _inputs(A, b, lo, hi)
    lower, upper = lo.copy(), hi.copy()
    n = len(lower)
    ids = list(range(n)) if indices is None else list(indices)
    if any(type(i) is not int or not 0 <= i < n for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid projection indices')
    solver = linprog if proposer is None else proposer
    report = {'empty': False, 'status': 'CERTIFIED_OUTER', 'queries': 0,
              'solver_proposals': 0, 'fallbacks': 0, 'tightened_bounds': 0,
              'certified_bounds': 0, 'failed_lp': 0,
              'certificate_arithmetic': 'exact_binary64_rational_fraction'}
    ar = [[_f(a) for a in row] for row in A]
    br = [_f(v) for v in b]
    lr, ur = [_f(v) for v in lower], [_f(v) for v in upper]
    # This check is independent of all optimizer statuses.
    for row, bound in zip(ar, br):
        minimum = -_support([-a for a in row], lr, ur)
        if minimum > bound:
            report.update(empty=True, status='CERTIFIED_EMPTY_ROW_BOX')
            return lower, upper, report
    if not len(A):
        return lower, upper, report
    for j in ids:
        for sign in (1, -1):
            report['queries'] += 1
            c = np.zeros(n); c[j] = sign
            cr = [Fraction(0)] * n; cr[j] = Fraction(sign)
            box = _support(cr, lr, ur)
            bound = box
            try:
                # These rounded transformations ONLY help propose multipliers.
                # Certificate verification below always uses original A,b,X,c.
                # Hence an imperfect transformed LP cannot make a false bound.
                origin = .5*lower + .5*upper
                scale = .5*upper - .5*lower
                scale = np.where(scale > 0., scale, 1.)
                As = A * scale[None, :]
                bs = b - A @ origin
                row_scale = np.maximum(np.max(np.abs(As), axis=1), np.abs(bs))
                row_scale = np.where(row_scale > 0., row_scale, 1.)
                transformed = (As / row_scale[:, None], bs / row_scale,
                               (lower-origin)/scale, (upper-origin)/scale)
                if not all(np.all(np.isfinite(v)) for v in transformed):
                    raise ValueError('nonfinite multiplier proposal scaling')
                result = solver(-c, A_ub=transformed[0], b_ub=transformed[1],
                                bounds=list(zip(transformed[2], transformed[3])),
                                method='highs')
                if not result.success:
                    raise ValueError('optimizer gave no multiplier proposal')
                # Maximize normalized coordinate y_j, then map proposal back
                # to the original x_j objective and original row normalization.
                raw = -np.asarray(result.ineqlin.marginals, dtype=float) * scale[j] / row_scale
                if raw.shape != b.shape or not np.all(np.isfinite(raw)):
                    raise ValueError('invalid multiplier proposal')
                # Clipping changes the proposal, not the verification theorem.
                multipliers = [_f(max(0., float(v))) for v in raw]
                cert = _certificate(ar, br, lr, ur, cr, multipliers)
                bound = min(box, cert)
                report['solver_proposals'] += 1
                report['certified_bounds'] += 1
            except (ValueError, TypeError, AttributeError, RuntimeError, OverflowError):
                report['fallbacks'] += 1
                report['failed_lp'] += 1
            if sign == 1:
                if bound < lr[j]:
                    report.update(empty=True, status='CERTIFIED_EMPTY_DUAL_BOX')
                    return lower, upper, report
                v = _up(bound)
                if v < upper[j]:
                    upper[j] = v; ur[j] = _f(v); report['tightened_bounds'] += 1
            else:
                bound = -bound
                if bound > ur[j]:
                    report.update(empty=True, status='CERTIFIED_EMPTY_DUAL_BOX')
                    return lower, upper, report
                v = _down(bound)
                if v > lower[j]:
                    lower[j] = v; lr[j] = _f(v); report['tightened_bounds'] += 1
    return lower, upper, report
