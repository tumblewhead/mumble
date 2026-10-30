"""Synthetic cells, programmable current and exogenous temperature: harness only."""
import json
import math
import time
from pathlib import Path
import numpy as np
from experiments.foster_feedback_001.plant import CELLS, scalar_step
from .telemetry import PARAMETERS, thermal

INITIAL = [.63, .001, -.002, .001, .15]
LOADS = ['legacy', 'cycle', 'pulses', 'multiscale', 'rest']


def cells(path=None):
    result = {name: dict(parameters=dict(zip(PARAMETERS, p)), initial_state=INITIAL.copy())
              for name, p in CELLS.items()}
    if path:
        custom = json.loads(Path(path).read_text())
        if not isinstance(custom, dict) or not custom:
            raise ValueError('cell file must be a nonempty name-to-cell object')
        result.update(custom)
    for name, cell in result.items():
        if not isinstance(name, str) or not name or not isinstance(cell, dict):
            raise ValueError('invalid cell name/object')
        if set(cell) != {'parameters', 'initial_state'} or set(cell['parameters']) != set(PARAMETERS):
            raise ValueError('cell needs exactly parameters (all eleven named quantities) and initial_state')
        p = np.asarray([cell['parameters'][k] for k in PARAMETERS], dtype=float)
        state = np.asarray(cell['initial_state'], dtype=float)
        if not np.isfinite(p).all() or np.any(p <= 0) or not p[3] < p[5] < p[7]:
            raise ValueError('positive cell parameters and tau1 < tau2 < tau3 required')
        if state.shape != (5,) or not np.isfinite(state).all() or not 0 <= state[0] <= 1 or abs(state[4]) > 1:
            raise ValueError('invalid initial [SOC,v1,v2,v3,h]')
    return result


def current(indices, load, amplitude):
    """Integer sample phases avoid ambiguous edges; positive means discharge."""
    indices = np.asarray(indices, dtype=np.int64)
    if load not in LOADS:
        raise ValueError('unknown load')
    if load == 'rest':
        return np.zeros(indices.shape)
    if load == 'multiscale':
        # Each segment is a balanced +/- pair followed by rest. Period=300s.
        ticks = indices % 10500
        values = np.zeros(indices.shape)
        start = 0
        for duration, rest, fraction in [(7, 21, 1.), (70, 35, .5),
                                          (700, 175, 1.), (4200, 315, .75)]:
            values[(ticks >= start) & (ticks < start + duration)] = fraction * amplitude
            values[(ticks >= start + duration) & (ticks < start + 2 * duration)] = -fraction * amplitude
            start += 2 * duration + rest
        assert start == 10500
    elif load == 'cycle':
        # 120s divides both active stages exactly; the repeating schedule has
        # zero net commanded charge. The legacy160s gated schedule does not.
        ticks = indices % 4200
        values = np.where(ticks < 1750, amplitude,
                          np.where((ticks >= 2100) & (ticks < 3850), -amplitude, 0.))
        clock = indices % 504000
        values[(clock >= 189000) & (clock < 378000)] = 0.
    else:
        ticks = indices % 5600
        values = np.where(ticks < 2450, amplitude,
                          np.where((ticks >= 2800) & (ticks < 5250), -amplitude, 0.))
        if load == 'legacy':
            # Preserve the original one-time rest and its small net charge.
            clock = indices
            values[(clock >= 189000) & (clock < 378000)] = 0.
    # Symmetric quantization of commanded load; measured I is exact in this control.
    return np.sign(values) * np.floor(np.abs(values) / .000125 + .5) * .000125


def temperatures(indices, mode, mean, amplitude, period):
    t = (np.asarray(indices) + 1) / 35
    raw = mean + amplitude * np.sin(2 * np.pi * t / period) if mode == 'cycle' else np.full(t.shape, mean)
    return -40 + np.floor((raw + 40) / .0625 + .5) * .0625


def generate(out, config, n, cell, load, amplitude, noise, seed, temperature,
             temperature_mean=25., temperature_amplitude=8., temperature_period=3600., chunk=8192,
             progress=None):
    """Write every 35Hz observation/truth row with bounded working buffers."""
    obs = np.lib.format.open_memmap(out / 'observations.npy', mode='w+', dtype='float64', shape=(n, 5))
    truth = np.lib.format.open_memmap(out / 'truth.npy', mode='w+', dtype='float64', shape=(n, 17))
    ref = np.array([cell['parameters'][k] for k in PARAMETERS])
    state = cell['initial_state'].copy()
    rng = np.random.default_rng(seed)
    sigma = math.sqrt(noise ** 2 + (1 / 1024) ** 2 / 12)
    valid = 0
    last_progress = time.perf_counter()
    for begin in range(0, n, chunk):
        end = min(n, begin + chunk)
        ix = np.arange(begin, end)
        I = current(ix, load, amplitude)
        T = temperatures(ix, temperature, temperature_mean, temperature_amplitude, temperature_period)
        params = ref * thermal(config, T)
        errors = rng.normal(0, noise, len(ix))
        for j, k in enumerate(ix):
            try:
                state, voltage = scalar_step(state, params[j], 1 / 35, float(I[j]),
                                             config['ocv_intercept_V'], config['ocv_slope_V_per_SOC'])
                code = math.floor((voltage + errors[j] - 1.5) * 1024 + .5)
                if not 0 <= code <= 4095:
                    raise ValueError('voltage ADC range; no clipping')
            except ValueError as e:
                obs.flush(); truth.flush()
                return obs, truth, dict(status='plant_failed', valid_records=valid,
                                        failure=dict(index=int(k), reason=str(e)))
            obs[k] = 1 / 35, I[j], T[j], 1.5 + code / 1024, sigma
            truth[k] = *state, *params[j], voltage
            valid += 1
        if progress and time.perf_counter()-last_progress >= 25:
            progress(valid)
            last_progress = time.perf_counter()
    obs.flush(); truth.flush()
    return obs, truth, dict(status='generated', valid_records=valid)
