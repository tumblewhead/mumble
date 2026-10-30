"""Explicit estimator coordinates; physical plant states remain unchanged."""
import numpy as np
from experiments.foster_feedback_001.estimator import prior as legacy_prior


def chart_name(config):
    name=config.get('hysteresis_chart','legacy')
    if name not in ('legacy','bounded'):raise ValueError('unknown hysteresis chart')
    return name


def prior(config):
    mean,root=legacy_prior(config)
    if chart_name(config)=='bounded':
        h=mean[4]
        if not -1<h<1:raise ValueError('bounded chart prior requires -1 < h < 1')
        mean[4]=np.arctanh(h)
        root[4,:]/=(1-h*h)
    return mean,root


def physical_states(chart,config):
    state=np.asarray(chart)[..., :5].copy()
    if chart_name(config)=='bounded':state[...,4]=np.tanh(state[...,4])
    return state
