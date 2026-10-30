"""Public diagnostic inputs frozen before held-out evaluation; no hidden truth."""
import math
from .model import Frame

TEMPERATURES = {
    'train_warm': [25,27,30,30,28,25,22,25],
    'train_cool': [25,22,20,18,20,22,25,25],
    'weak': [25]*8,
    'driven': [25,26,28,30,29,27,25,24],
    'reversal': [25,35,15,35,15,30,20,25],
}


def frames(name):
    temperatures = TEMPERATURES[name]
    currents = [0,.02,.02,0,-.015,.025,0,.02] if name != 'weak' else [0]*8
    phases = {'train_warm':.2,'train_cool':1.1,'weak':2.,'driven':2.7,'reversal':3.4}
    durations = [20,30,40,30,20,40,30,40]
    # Deliberately fabricated observations, not generated from a hidden truth
    # later used to center the prior, tune a rate, or train a held-out codeword.
    return [Frame(k,dt,I,T,3.7+.015*math.sin(.8*k+phases[name])-.1*I)
            for k,(dt,I,T) in enumerate(zip(durations,currents,temperatures))]


TRAINING = ('train_warm','train_cool')
HELD_OUT = ('weak','driven','reversal')
PROFILE_SCALES = (0.01,20.)
TEMPLATE_CHECKPOINTS = (3,7)
