"""Exact fixed-rate campaign clock; 35 Hz remains the default."""
import math
DEFAULT_RATE = 35

def clock_hz(rate):
    if not isinstance(rate,int) or isinstance(rate,bool) or rate<1:
        raise ValueError('sample rate must be an integer >=1 Hz (model interval limit:1 second)')
    clock=math.lcm(1050,rate)
    if clock>2**31-1:raise ValueError('sample rate requires a clock beyond the supported 32-bit range')
    return clock
