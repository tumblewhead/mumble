"""Physical reporting only; never fed back to the estimator."""
import numpy as np

STATES = ['SOC', 'v1_V', 'v2_V', 'v3_V', 'h']
PARAMETERS = ['Q_Ah', 'R0_ohm', 'R1_ohm', 'tau1_s', 'R2_ohm',
              'tau2_s', 'R3_ohm', 'tau3_s', 'H_V', 'gamma_plus', 'gamma_minus']
OBS_COLUMNS = ['dt_s', 'current_A', 'temperature_C', 'voltage_V', 'sigma_V']
TRUTH_COLUMNS = STATES + PARAMETERS + ['noiseless_voltage_V']
TRACE_COLUMNS = (['record_count', 'time_s', 'current_A', 'temperature_C', 'measured_voltage_V',
                  'assimilated_endpoint_voltage_V'] + STATES + PARAMETERS +
                 [p + '_ref' for p in PARAMETERS] + ['C1_F', 'C2_F', 'C3_F'] +
                 ['Q_log_sd', 'SOC_sd', 'log_evidence'])


def thermal(config, temperature):
    return np.exp(np.asarray(config['arrhenius_A_K']) *
                  (1 / (np.asarray(temperature)[..., None] + 273.15) -
                   1 / config['reference_temperature_K']))


def physical(chart, config, temperature):
    ref = np.exp(np.asarray(chart)[..., 5:]).copy()
    ref[..., 5] += ref[..., 3]
    ref[..., 7] += ref[..., 5]
    return ref, ref * thermal(config, temperature)


def trace_row(readout, observation, config):
    m = np.asarray(readout['chart_mean'])
    ref, p = physical(m, config, observation[2])
    voltage = (config['ocv_intercept_V'] + config['ocv_slope_V_per_SOC'] * m[0] +
               p[8] * m[4] - observation[1] * p[1] - sum(m[1:4]))
    capacitance = p[[3, 5, 7]] / p[[2, 4, 6]]
    return np.r_[readout['records'], readout['records'] / 35, observation[1:4],
                 voltage, m[:5], p, ref, capacitance, readout['Q_log_sd'],
                 readout['SOC_sd'], readout['log_evidence']]
