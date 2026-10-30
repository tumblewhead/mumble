"""Avoid subnormal erfc differences; preserve the inherited density exactly."""
import math
import numpy as np
from experiments.voltage_coordinates_001 import coordinates as v


def log_mass(a, b):
    a, b = np.broadcast_arrays(a, b)
    v.require(np.isfinite(a).all() and np.isfinite(b).all() and np.all(a < b), 'normalizer interval')
    shape = a.shape
    af, bf = a.ravel(), b.ravel()
    out = np.empty(len(af))
    for i, (left, right) in enumerate(zip(af, bf)):
        if left >= 0:
            large, small = .5*math.erfc(left/math.sqrt(2)), .5*math.erfc(right/math.sqrt(2))
        elif right <= 0:
            large, small = .5*math.erfc(-right/math.sqrt(2)), .5*math.erfc(-left/math.sqrt(2))
        else:
            large, small = 1., .5*math.erfc(-left/math.sqrt(2))+.5*math.erfc(right/math.sqrt(2))
        # The predecessor accepted any positive large value. Subnormal values
        # can have very few relative bits even when their subtraction is wide.
        if large >= np.finfo(float).tiny and large-small > 1e-8*large:
            out[i] = math.log(large)+math.log1p(-small/large)
        else:
            center = min(right, max(left, 0.))
            try:
                out[i] = v.old.kernel.normalizer(-center, 1., left-center, right-center).log_Z
            except (v.old.kernel.ModelError, OverflowError) as error:
                raise v.old.Unavailable('scaled normalizer unresolved: '+str(error)) from error
    v.require(np.isfinite(out).all() and np.all(out <= 1e-12), 'normalizer result')
    return out.reshape(shape)
