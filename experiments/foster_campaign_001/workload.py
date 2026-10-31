"""Seeded semi-Markov activity envelopes; test harness only, no battery truth inputs.

Current fractions are generic synthetic battery-side assumptions. Operations are
activity episodes (e.g. a radio exchange or a batch of flash writes), not packets
or individual page-program timing. Separate LED activity may overlap operations.
"""
import copy
import math
import numpy as np
from .rate import DEFAULT_RATE, sample_period_s
CLOCK_HZ=1_000_000
EVENT_COLUMNS=['chain','event_index','start_us','end_us','state','fraction_of_peak','load_seed']
# total operating current before LED; default peak30mA, LED at most5mA.
OPERATIONS={
    'sleep':(.00025/.03,.5,8.),
    'sense':(.0025/.03,.08,.5),
    'compute':(.006/.03,.1,2.),
    'radio_tx':(.010/.03,.04,.32),
    'radio_rx':(.009/.03,.04,.5),
    'flash_program':(.018/.03,.04,.16),
    'flash_erase':(.025/.03,.06,.6),
}
TRANSITIONS={
    'sleep': [('sense',1.)],
    'sense': [('compute',.75),('radio_tx',.25)],
    'compute': [('radio_tx',.4),('flash_program',.3),('sleep',.3)],
    'radio_tx': [('radio_rx',.7),('sleep',.3)],
    'radio_rx': [('sleep',.7),('flash_program',.3)],
    'flash_program': [('sleep',.8),('flash_erase',.2)],
    'flash_erase': [('flash_program',1.)],
}
LED={'off':(0.,.5,6.),'on':(1/6,.2,4.)}
LED_TRANSITIONS={'off':[('on',1.)],'on':[('off',1.)]}

class Chain:
    def __init__(self,name,rng,seed,states,transitions,start):
        self.name=name;self.rng=rng;self.seed=seed;self.states=states;self.transitions=transitions
        self.state=start;self.end_us=0;self.count=0;self.events=[];self.dwell_us={s:0 for s in states}
        self.begin(0)
    def begin(self,start_us):
        fraction,low,high=self.states[self.state]
        duration=int(self.rng.integers(round(low*CLOCK_HZ),round(high*CLOCK_HZ)+1))
        self.end_us=start_us+duration;self.fraction=fraction
        self.events.append(dict(chain=self.name,event_index=self.count,start_us=start_us,end_us=self.end_us,state=self.state,fraction_of_peak=fraction,load_seed=self.seed));self.count+=1
    def transition(self):
        candidates=self.transitions[self.state];u=self.rng.random();cum=0.
        for state,prob in candidates:
            cum+=prob
            if u<cum:break
        self.state=state;self.begin(self.end_us)
    def interval(self,index,rate):
        # Common integer units: microseconds*rate. Each sample spans CLOCK_HZ.
        left=index*CLOCK_HZ;right=(index+1)*CLOCK_HZ;area=0.
        while left<right:
            if self.end_us*rate<=left:self.transition();continue
            stop=min(right,self.end_us*rate);area+=self.fraction*(stop-left)
            self.dwell_us[self.state]+=(stop-left)/rate;left=stop
        return area/CLOCK_HZ
    def take_events(self):result=self.events;self.events=[];return result

class EmbeddedWorkload:
    def __init__(self,seed,peak_current=.03,sample_rate_hz=DEFAULT_RATE):
        sample_period_s(sample_rate_hz)
        if not isinstance(seed,(int,np.integer)) or seed<0:raise ValueError('nonnegative integer load seed required')
        if not math.isfinite(peak_current) or not 0<=peak_current<=.25:raise ValueError('workload peak must be0..0.25A')
        self.seed=int(seed);self.rate=sample_rate_hz;self.peak=float(peak_current);self.next_index=0
        streams=np.random.SeedSequence(self.seed).spawn(2)
        self.chains=[Chain('operation',np.random.Generator(np.random.PCG64(streams[0])),self.seed,OPERATIONS,TRANSITIONS,'sleep'),Chain('LED',np.random.Generator(np.random.PCG64(streams[1])),self.seed,LED,LED_TRANSITIONS,'off')]
    def current(self,index):
        if index!=self.next_index:raise ValueError('workload source order')
        value=self.peak*sum(c.interval(index,self.rate) for c in self.chains);self.next_index+=1
        if not -1e-15<=value<=self.peak+1e-15:raise ValueError('workload current bounds')
        return value
    def take_events(self):
        return sorted([e for c in self.chains for e in c.take_events()],key=lambda e:(e['start_us'],e['chain'],e['event_index']))
    def snapshot(self):
        return copy.deepcopy(dict(schema='embedded_workload_checkpoint_v1', seed=self.seed,
            rate=self.rate, peak=self.peak, next_index=self.next_index,
            chains=[dict(name=c.name, rng=c.rng.bit_generator.state,
                         **{k:getattr(c,k) for k in ['state','end_us','count','events','dwell_us','fraction']})
                    for c in self.chains]))
    def restore(self, saved):
        if (saved['schema'],saved['seed'],saved['rate'],saved['peak']) != (
                'embedded_workload_checkpoint_v1',self.seed,self.rate,self.peak):
            raise ValueError('workload checkpoint configuration mismatch')
        if [c.name for c in self.chains] != [c['name'] for c in saved['chains']]:
            raise ValueError('workload checkpoint chain mismatch')
        self.next_index=saved['next_index']
        for chain, state in zip(self.chains,saved['chains']):
            chain.rng.bit_generator.state=copy.deepcopy(state['rng'])
            for key in ['state','end_us','count','events','dwell_us','fraction']:
                setattr(chain,key,copy.deepcopy(state[key]))
    def summary(self):
        return dict(kind='semi_markov_embedded_envelope_v1',load_seed=self.seed,noise_seed_used=False,peak_current_A=self.peak,sample_rate_Hz=self.rate,event_clock_hz=CLOCK_HZ,rng='PCG64 via SeedSequence(load_seed).spawn(2)',operations=OPERATIONS,transitions=TRANSITIONS,LED=LED,LED_transitions=LED_TRANSITIONS,chains={c.name:dict(events=c.count,elapsed_seconds_by_state={s:v/CLOCK_HZ for s,v in c.dwell_us.items()}) for c in self.chains},scope='Generic battery-side activity envelopes; interval-average command physically held for1/Fs. No sub-sample RF/PWM circuit or real board fidelity claim.',seed_scope='Logical workload independent of noise and cell; charger phase gating and terminal current may depend on measured voltage.')
