"""Fixed stationary probes with supported per-step intervals."""
import math
from experiments.region_compression_001.compare import scalar_stats
from experiments.region_compression_001.regions import stationary_probe


def segment(current, duration):
    whole = int(math.floor(duration))
    steps = [[current, 1.] for _ in range(whole)]
    if duration-whole > 0:
        steps.append([current, duration-whole])
    return steps


def definitions(horizons):
    probes = [dict(name='boundary', horizon_s=0., profile='boundary', steps=[])]
    for t in horizons:
        for profile in ['rest', 'load', 'reversal']:
            steps = segment(0. if profile == 'rest' else .05, t)
            if profile == 'reversal':
                steps += segment(-.05, t)
            probes.append(dict(name=f'{profile}_{t:.12g}s', horizon_s=t, profile=profile, steps=steps))
    return probes


def assess(x, probes):
    result = {}
    for probe in probes:
        voltage, valid = stationary_probe(x, probe['steps'])
        result[probe['name']] = dict(horizon_s=probe['horizon_s'], profile=probe['profile'],
            invalid_mass_fraction=float(1-valid.mean()), voltage_V=scalar_stats(voltage) if valid.all() else None,
            status='finite_all_draws_supported' if valid.all() else 'unavailable_support_loss')
    return result
