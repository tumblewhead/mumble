"""Versioned physical RC scale semantics; unchanged full16 transport."""
import math
import numpy as np
from experiments.partition_coordinate_fit_001 import coordinates as c
from experiments.partition_coordinate_fit_001.stable_normalizer import log_mass
from experiments.natural_hysteresis_001 import natural

NATURAL = (3, 4)


class Message(c.Message):
    def __init__(self, chart, edges, frame, regions, diagnostics, scaled=()):
        super().__init__(chart, edges, frame, regions, diagnostics)
        self.scaled = tuple(scaled)

    @classmethod
    def from_parent(cls, parent, scaled=()):
        return cls(parent.chart, parent.edges.copy(), parent.frame.copy(),
                   [{k: v.copy() for k, v in reg.items()} for reg in parent.regions], [], scaled)

    def export(self):
        return dict(schema='physical_rc_scale_message_v1', natural_coordinates=list(NATURAL),
                    physical_scale_coordinates=list(self.scaled),
                    shape_semantics='precision at3/4; physical-v logsd at selected9:12; coordinate logsd elsewhere',
                    **super().export())

    @classmethod
    def restore(cls, data):
        c.old.require(data.get('schema') == 'physical_rc_scale_message_v1'
                      and data.get('natural_coordinates') == list(NATURAL)
                      and data.get('chart') == 'specialized', 'wrong physical-scale schema')
        scaled = tuple(data['physical_scale_coordinates'])
        c.old.require(scaled in [(), (11,), (9,10,11)], 'unsupported physical-scale layout')
        obj = super().restore(data)
        obj.scaled = scaled
        for reg in obj.regions:
            c.old.require(set(reg) == {'coefficients','shape','logweight'}
                          and reg['coefficients'].shape == (136,) and reg['shape'].shape == (16,)
                          and all(np.isfinite(v).all() for v in reg.values())
                          and np.all(reg['shape'][list(NATURAL)] >= 0), 'invalid physical-scale region')
        return obj

    def logpdf_details(self, x):
        y, a, jacobian = c.encode(x, self.chart, self.frame)
        components, partitions = [], []
        for reg in self.regions:
            values = np.full(len(x), float(reg['logweight']))
            logz = np.empty_like(y)
            for j in range(16):
                beta = c.coefficients(reg, j)
                predictor = beta[0]+y[:, :j] @ beta[1:]
                if j in NATURAL:
                    k = float(reg['shape'][j])
                    logz[:, j] = natural.log_partition(predictor, k)
                    values += predictor*y[:, j]-.5*k*y[:, j]**2-logz[:, j]
                else:
                    sd = math.exp(float(reg['shape'][j]))
                    if j in self.scaled:
                        sd = sd*a[:, j-9]
                    lo, hi = c.bounds(x, a, j, self.chart)
                    logz[:, j] = log_mass((lo-predictor)/sd, (hi-predictor)/sd)
                    values += -.5*((y[:, j]-predictor)/sd)**2-np.log(sd)-.5*c.old.LOG2PI-logz[:, j]
            components.append(values)
            partitions.append(logz)
        return np.logaddexp.reduce(components)+jacobian, np.concatenate(partitions)

    def draw(self, n, seed):
        rng = np.random.default_rng(seed)
        labels = rng.choice(len(self.regions), size=n, p=np.exp([reg['logweight'] for reg in self.regions]))
        x, count = np.full((n, 16), np.nan), 0
        for region_index, reg in enumerate(self.regions):
            take = np.flatnonzero(labels == region_index)
            local = np.full((len(take), 16), np.nan)
            y = np.empty_like(local)
            for j in range(16):
                beta = c.coefficients(reg, j)
                predictor = beta[0]+y[:, :j] @ beta[1:]
                if j in NATURAL:
                    y[:, j], proposals = natural.draw(predictor, float(reg['shape'][j]), rng)
                else:
                    sd = math.exp(float(reg['shape'][j]))
                    a = c.rc.attenuation(local, self.frame) if j >= 9 else None
                    if j in self.scaled:
                        sd = sd*a[:, j-9]
                    lo, hi = c.bounds(local, a, j, self.chart)
                    z, proposals = c.v.truncated_standard_draw((lo-predictor)/sd, (hi-predictor)/sd, rng)
                    y[:, j] = predictor+sd*z
                count += proposals
                c.set_coordinate(local, y[:, j], j, self.chart, self.frame)
            c.old.to_unit(local)
            x[take] = local
        return x, dict(sampler_proposals=count)


def unchanged(parent, child):
    np.testing.assert_array_equal(parent.edges, child.edges)
    np.testing.assert_array_equal(parent.frame, child.frame)
    for before, after in zip(parent.regions, child.regions):
        np.testing.assert_array_equal(before['logweight'], after['logweight'])
        for j in range(16):
            if j not in child.scaled:
                np.testing.assert_array_equal(c.coefficients(before,j), c.coefficients(after,j))
                np.testing.assert_array_equal(before['shape'][j],after['shape'][j])
    c.old.require(parent.numeric_bytes == child.numeric_bytes == 2496, 'payload size changed')
