"""Measured-voltage CC/CV charger and variable load, exclusively in the harness."""
import math

RATE = 35
CURRENT_STEP = .000125
EVENT_COLUMNS = ['record_count', 'time_s', 'phase', 'reason', 'measured_voltage_V',
                 'current_A', 'charger_limit_C', 'discharge_load_C', 'completed_cycles']
DEFAULTS = dict(nominal_capacity_ah=.06, charge_c=[2.,1.,1.5], discharge_c=[.2,.45,.7],
    charge_step_s=900., discharge_step_s=600., cv_voltage=4.06, discharge_cutoff_v=3.18,
    cycle_rest_s=300., taper_end_c=.05, taper_hold_s=30., cv_gain=.5)


def quantize(current):
    return math.copysign(math.floor(abs(current)/CURRENT_STEP+.5)*CURRENT_STEP,current)


def validate(settings, sample_rate_hz=35):
    if set(settings)!=set(DEFAULTS):
        raise ValueError('incomplete charger settings')
    values=[v for v in settings.values() if not isinstance(v,list)]
    charge=settings['charge_c'];discharge=settings['discharge_c']
    if not charge or not discharge or not all(math.isfinite(v) for v in [*values,*charge,*discharge]):
        raise ValueError('finite charger settings and nonempty C-rate schedules required')
    if any(settings[k]<=0 for k in ['nominal_capacity_ah','charge_step_s','discharge_step_s','taper_end_c','taper_hold_s','cv_gain']):
        raise ValueError('positive capacity, dwell, taper endpoint and CV gain required')
    if settings['cycle_rest_s']<0 or min(charge)<=settings['taper_end_c'] or min(discharge)<=0:
        raise ValueError('nonnegative rest and positive C-rates; charger capabilities must exceed taper endpoint')
    if not 1.5<settings['discharge_cutoff_v']<settings['cv_voltage']<1.5+4095/1024:
        raise ValueError('ordered voltage cutoffs inside ADC range required')
    if any(round(settings[k]*sample_rate_hz)<1 for k in ['charge_step_s','discharge_step_s','taper_hold_s']):
        raise ValueError('each dwell must contain at least one sample at the selected rate')
    nominal=settings['nominal_capacity_ah']
    currents=[quantize(c*nominal) for c in charge+discharge]
    if min(currents)<=0 or max(currents)>.25 or quantize(settings['taper_end_c']*nominal)<=0:
        raise ValueError('C-rates must resolve on125uA current grid and stay within0.25A model limit')


class ChargeDischarge:
    """Controller consumes only indexed terminal-voltage measurements.

    Negative I charges. Capability/load schedules follow the global clock even
    during rest. A saturated integral voltage loop commands CV taper; no plant
    parameters, truth states or estimator outputs are controller inputs.
    """
    def __init__(self, settings, sample_rate_hz=35):
        validate(settings, sample_rate_hz)
        self.rate=sample_rate_hz
        self.s={k:(list(v) if isinstance(v,list) else v) for k,v in settings.items()}
        self.phase='cc';self.phase_start=0;self.next_index=0;self.cv_magnitude=0.
        self.low_samples=0;self.completed_cycles=0;self.events=[];self.last_voltage=None
        self.last_signature=None;self.last_current=0.;self.last_charge_limit=0.
        self.counts={p:0 for p in ['cc','cv','rest_after_charge','discharge','rest_after_discharge']}
        self.charge_Ah=0.;self.discharge_Ah=0.

    def schedule(self,index):
        charge=self.s['charge_c'][(index//round(self.s['charge_step_s']*self.rate))%len(self.s['charge_c'])]
        discharge=self.s['discharge_c'][(index//round(self.s['discharge_step_s']*self.rate))%len(self.s['discharge_c'])]
        return charge,discharge

    def event(self,index,reason,current):
        charge,discharge=self.schedule(index)
        self.events.append(dict(record_count=index,time_s=index/self.rate,phase=self.phase,reason=reason,
            measured_voltage_V=self.last_voltage,current_A=current,charger_limit_C=charge,
            discharge_load_C=discharge,completed_cycles=self.completed_cycles))

    def current(self,index):
        if index!=self.next_index:raise ValueError('controller source order')
        charge,discharge=self.schedule(index);q=self.s['nominal_capacity_ah']
        cap=quantize(charge*q);self.last_charge_limit=cap
        if self.phase=='cc':current=-cap
        elif self.phase=='cv':
            self.cv_magnitude=min(self.cv_magnitude,cap)
            current=-min(cap,quantize(self.cv_magnitude))
        elif self.phase=='discharge':current=quantize(discharge*q)
        else:current=0.
        signature=(self.phase,charge if self.phase in ['cc','cv'] else discharge if self.phase=='discharge' else 0)
        if signature!=self.last_signature:
            self.event(index,'phase start' if self.last_signature is None else 'scheduled capability/load change',current)
            self.last_signature=signature
        self.last_current=current
        return current

    def transition(self,phase,index,reason):
        self.phase=phase;self.phase_start=index;self.last_signature=None;self.low_samples=0
        self.event(index,reason,None)

    def observe(self,index,voltage):
        if index!=self.next_index or not math.isfinite(voltage):raise ValueError('invalid controller measurement/order')
        self.next_index+=1;self.last_voltage=voltage;self.counts[self.phase]+=1
        self.charge_Ah+=max(0.,-self.last_current)/(self.rate*3600)
        self.discharge_Ah+=max(0.,self.last_current)/(self.rate*3600)
        rest=round(self.s['cycle_rest_s']*self.rate)
        if self.phase=='cc' and voltage>=self.s['cv_voltage']:
            self.cv_magnitude=abs(self.last_current)
            self.transition('cv',index+1,'measured voltage reached CV setpoint')
        elif self.phase=='cv':
            # Ampere/(volt second) gain, held-interval dt=1/sample_rate_hz. Saturation
            # enforces the explicit charger capability; no exponential filter.
            self.cv_magnitude=max(0.,min(self.last_charge_limit,
                self.cv_magnitude+self.s['cv_gain']*(self.s['cv_voltage']-voltage)/self.rate))
            near_voltage=voltage>=self.s['cv_voltage']-1/1024
            below=abs(self.last_current)<=quantize(self.s['taper_end_c']*self.s['nominal_capacity_ah'])
            # Current dwell defines the taper endpoint. Reaching the voltage
            # setpoint at the dwell endpoint prevents ending on a current deficit.
            self.low_samples=self.low_samples+1 if below else 0
            if self.low_samples>=round(self.s['taper_hold_s']*self.rate) and near_voltage:
                self.transition('rest_after_charge' if rest else 'discharge',index+1,'CV taper current dwell completed')
        elif self.phase=='discharge' and voltage<=self.s['discharge_cutoff_v']:
            self.completed_cycles+=1
            self.transition('rest_after_discharge' if rest else 'cc',index+1,'measured voltage reached discharge cutoff')
        elif self.phase.startswith('rest') and index+1-self.phase_start>=rest:
            self.transition('discharge' if self.phase=='rest_after_charge' else 'cc',index+1,'rest completed')

    def take_events(self):
        events=self.events;self.events=[];return events

    def summary(self):
        return dict(settings=self.s,sample_rate_Hz=self.rate,phase=self.phase,phase_records=self.counts,
                    completed_cycles=self.completed_cycles,charge_Ah=self.charge_Ah,discharge_Ah=self.discharge_Ah,
                    authority='Harness only: nominal nameplate capacity, global-time schedules and measured terminal V; no true SOC/Q or estimator feedback',
                    current_grid_A=CURRENT_STEP,reference='C-rates use nominal_capacity_ah, not unknown actual capacity',
                    CV_scope='Finite-bandwidth integral controller, not algebraic exact voltage clamp; current-limited CC/CV',
                    timing='Phase changes apply to the sample after the triggering measurement')
