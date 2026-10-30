"""Exact fixed-rate campaign clock; 35 Hz remains the default."""
import math
DEFAULT_RATE = 35
# Historical files without metadata were generated at35Hz; never reinterpret them
# when changing the default for future campaigns. This is not an active setting.
LEGACY_RATE = 35

def clock_hz(rate):
    if not isinstance(rate,int) or isinstance(rate,bool) or rate<1:
        raise ValueError('sample rate must be an integer >=1 Hz (model interval limit:1 second)')
    clock=math.lcm(1050,rate)
    if clock>2**31-1:raise ValueError('sample rate requires a clock beyond the supported 32-bit range')
    return clock

def sample_period_s(rate):
    """Uniform sample interval in seconds, derived only from the selected Fs."""
    clock_hz(rate)
    return 1.0 / rate
