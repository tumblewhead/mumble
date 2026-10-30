"""Synthetic cells, programmable current and exogenous temperature: harness only."""
import json
import csv
from contextlib import nullcontext
import math
import time
from pathlib import Path
import numpy as np
from experiments.foster_feedback_001.plant import CELLS, scalar_step
from .rate import DEFAULT_RATE, sample_period_s
from .telemetry import PARAMETERS, thermal
from .charger import ChargeDischarge, DEFAULTS, EVENT_COLUMNS

INITIAL = [.63, .001, -.002, .001, .15]
LOADS = ['legacy', 'cycle', 'pulses', 'multiscale', 'rest', 'charge-discharge']


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


def current(indices, load, amplitude, sample_rate_hz=DEFAULT_RATE):
    """Integer sample phases avoid ambiguous edges; positive means discharge."""
    indices = np.asarray(indices, dtype=np.int64)
    rate = sample_rate_hz
    if load not in LOADS:
        raise ValueError('unknown load')
    if load == 'charge-discharge':
        raise ValueError('charge-discharge requires the measured-voltage controller')
    if load == 'rest':
        return np.zeros(indices.shape)
    if load == 'multiscale':
        # Each segment is a balanced +/- pair followed by rest. Period=300s.
        ticks = (indices % (300*rate))*5  # Schedule units are fifths of a second.
        values = np.zeros(indices.shape)
        start = 0
        for duration, rest, fraction in [(1, 3, 1.), (10, 5, .5),
                                          (100, 25, 1.), (600, 45, .75)]:
            values[(ticks >= start*rate) & (ticks < (start + duration)*rate)] = fraction * amplitude
            values[(ticks >= (start + duration)*rate) & (ticks < (start + 2 * duration)*rate)] = -fraction * amplitude
            start += 2 * duration + rest
        assert start == 1500
    elif load == 'cycle':
        # 120s divides both active stages exactly; the repeating schedule has
        # zero net commanded charge. The legacy160s gated schedule does not.
        ticks = indices % (120*rate)
        values = np.where(ticks < 50*rate, amplitude,
                          np.where((ticks >= 60*rate) & (ticks < 110*rate), -amplitude, 0.))
        clock = indices % (14400*rate)
        values[(clock >= 5400*rate) & (clock < 10800*rate)] = 0.
    else:
        ticks = indices % (160*rate)
        values = np.where(ticks < 70*rate, amplitude,
                          np.where((ticks >= 80*rate) & (ticks < 150*rate), -amplitude, 0.))
        if load == 'legacy':
            # Preserve the original one-time rest and its small net charge.
            clock = indices
            values[(clock >= 5400*rate) & (clock < 10800*rate)] = 0.
    # Symmetric quantization of commanded load; measured I is exact in this control.
    return np.sign(values) * np.floor(np.abs(values) / .000125 + .5) * .000125


def temperatures(indices, mode, mean, amplitude, period, sample_rate_hz=DEFAULT_RATE):
    t = (np.asarray(indices) + 1) / sample_rate_hz
    raw = mean + amplitude * np.sin(2 * np.pi * t / period) if mode == 'cycle' else np.full(t.shape, mean)
    return -40 + np.floor((raw + 40) / .0625 + .5) * .0625


def generate(out, config, n, cell, load, amplitude, noise, seed, temperature,
             temperature_mean=25., temperature_amplitude=8., temperature_period=3600., chunk=8192,
             progress=None, charger_settings=None, sample_rate_hz=DEFAULT_RATE):
    """Write every observation/truth row at the declared rate with bounded buffers."""
    dt = sample_period_s(sample_rate_hz)
    obs = np.lib.format.open_memmap(out / 'observations.npy', mode='w+', dtype='float64', shape=(n, 5))
    truth = np.lib.format.open_memmap(out / 'truth.npy', mode='w+', dtype='float64', shape=(n, 17))
    ref = np.array([cell['parameters'][k] for k in PARAMETERS])
    state = cell['initial_state'].copy()
    controller=ChargeDischarge(charger_settings or DEFAULTS, sample_rate_hz=sample_rate_hz) if load=='charge-discharge' else None
    rng = np.random.default_rng(seed)
    sigma = math.sqrt(noise ** 2 + (1 / 1024) ** 2 / 12)
    valid = 0
    last_progress = time.perf_counter()
    with ((out/'stimulus_events.csv').open('x',newline='') if controller else nullcontext()) as events_file:
        writer=csv.DictWriter(events_file,fieldnames=EVENT_COLUMNS) if controller else None
        if writer:writer.writeheader()
        for begin in range(0, n, chunk):
            end = min(n, begin + chunk)
            ix = np.arange(begin, end)
            I = np.empty(len(ix)) if controller else current(ix, load, amplitude, sample_rate_hz)
            T = temperatures(ix, temperature, temperature_mean, temperature_amplitude, temperature_period, sample_rate_hz)
            params = ref * thermal(config, T)
            errors = rng.normal(0, noise, len(ix))
            for j, k in enumerate(ix):
                if controller:
                    I[j]=controller.current(int(k));writer.writerows(controller.take_events())
                try:
                    state, voltage = scalar_step(state, params[j], dt, float(I[j]),
                                                 config['ocv_intercept_V'], config['ocv_slope_V_per_SOC'])
                    code = math.floor((voltage + errors[j] - 1.5) * 1024 + .5)
                    if not 0 <= code <= 4095:
                        raise ValueError('voltage ADC range; no clipping')
                except ValueError as e:
                    obs.flush(); truth.flush()
                    return obs, truth, dict(status='plant_failed', valid_records=valid,
                                            failure=dict(index=int(k), reason=str(e)),
                                            **({'charger':controller.summary()} if controller else {}))
                measured_voltage=1.5+code/1024
                obs[k] = dt, I[j], T[j], measured_voltage, sigma
                truth[k] = *state, *params[j], voltage
                valid += 1
                if controller:
                    controller.observe(int(k),measured_voltage);writer.writerows(controller.take_events())
            if progress and time.perf_counter()-last_progress >= 25:
                progress(valid)
                last_progress = time.perf_counter()
    obs.flush(); truth.flush()
    return obs, truth, dict(status='generated', valid_records=valid,
                            **({'charger':controller.summary()} if controller else {}))
