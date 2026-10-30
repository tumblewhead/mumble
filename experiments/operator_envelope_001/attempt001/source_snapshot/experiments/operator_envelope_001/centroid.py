"""Fixed four-knot natural-cubic basis and independent-observation control.

This is not a fitted battery-aging law or an adapter for rolling posteriors.
"""
import numpy as np


def basis(times, knots):
    t = np.atleast_1d(np.array(times, dtype=float)); k = np.asarray(knots, dtype=float)
    if k.shape != (4,) or not np.isfinite(k).all() or np.any(np.diff(k) <= 0):
        raise ValueError('four strictly ordered finite knots required')
    if not np.isfinite(t).all() or np.any(t < k[0]) or np.any(t > k[-1]):
        raise ValueError('no spline extrapolation')
    h = np.diff(k); values = np.eye(4)
    matrix = np.array([[2*(h[0]+h[1]), h[1]], [h[1], 2*(h[1]+h[2])]])
    rhs = np.stack([6*((values[i+1]-values[i])/h[i]-(values[i]-values[i-1])/h[i-1]) for i in (1,2)])
    second = np.zeros((4,4)); second[1:3] = np.linalg.solve(matrix, rhs)
    index = np.minimum(np.searchsorted(k, t, side='right')-1, 2)
    a = (k[index+1]-t)/h[index]; b = (t-k[index])/h[index]
    return (a[:,None]*values[index]+b[:,None]*values[index+1]
            +((a**3-a)[:,None]*second[index]+(b**3-b)[:,None]*second[index+1])*(h[index]**2)[:,None]/6)


class Statistics:
    """One scalar independent-observation family, with a fixed basis forever."""
    def __init__(self, knots):
        self.knots = np.asarray(knots, dtype=float).copy()
        basis(self.knots, self.knots)
        self.A = np.zeros((4,4)); self.h = np.zeros(4); self.c = 0.; self.count = 0

    def append(self, t, y, variance, index):
        if type(index) is not int or index != self.count or not np.isfinite(y) or not np.isfinite(variance) or variance <= 0:
            raise ValueError('new unique observation and positive variance required')
        b = basis([t], self.knots)[0]; w = 1/variance
        A = self.A+w*np.outer(b,b); h = self.h+w*b*y; c = self.c+w*y*y
        if not np.isfinite(np.r_[A.ravel(), h, c]).all():
            raise ValueError('numeric_unresolved')
        self.A, self.h, self.c = A, h, float(c); self.count += 1

    def centered(self, center):
        center = np.asarray(center, dtype=float)
        if center.shape != (4,) or not np.isfinite(center).all():
            raise ValueError('invalid center')
        return self.A.copy(), self.h-self.A@center, float(self.c-2*self.h@center+center@self.A@center)

    def quadratic(self, coefficients):
        c = np.asarray(coefficients)
        return float(.5*(c@self.A@c-2*self.h@c+self.c))
