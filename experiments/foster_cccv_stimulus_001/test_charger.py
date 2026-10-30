"""Targeted charger controls independent of estimator truth and objectives."""
import csv
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
import numpy as np
from experiments.foster_campaign_001.charger import ChargeDischarge, DEFAULTS, validate, quantize
from experiments.foster_campaign_001.stimulus import generate, cells

CONFIG=json.loads(Path('experiments/foster_feedback_001/calibration.json').read_text())


class ChargerTests(unittest.TestCase):
    def test_c_rates_and_global_capability_schedule(self):
        c=ChargeDischarge({**DEFAULTS,'charge_step_s':1.})
        currents=[]
        for i in range(105):
            currents.append(c.current(i));c.observe(i,3.8)
        np.testing.assert_array_equal(currents[:35],np.full(35,-.12))
        np.testing.assert_array_equal(currents[35:70],np.full(35,-.06))
        np.testing.assert_array_equal(currents[70:],np.full(35,-.09))

    def test_voltage_loop_regulates_without_plant_state(self):
        c=ChargeDischarge({**DEFAULTS,'charge_c':[2.]})
        measured=[]
        for i in range(3000):
            current=c.current(i)
            voltage=3.99-.6*current
            measured.append(voltage);c.observe(i,voltage)
        self.assertEqual(c.phase,'cv')
        self.assertLess(max(abs(np.array(measured[-100:])-4.06)),.0001)
        self.assertTrue(all(-.12<=quantize(x)<=0 for x in [-c.cv_magnitude]))

    def test_taper_dwell_rest_and_discharge(self):
        c=ChargeDischarge({**DEFAULTS,'charge_c':[2.],'taper_hold_s':1.,'cycle_rest_s':1.})
        c.current(0);c.observe(0,4.07)
        self.assertEqual(c.phase,'cv');c.cv_magnitude=.002
        for i in range(1,35):c.current(i);c.observe(i,4.06)
        self.assertEqual(c.phase,'cv')
        c.current(35);c.observe(35,4.06)
        self.assertEqual(c.phase,'rest_after_charge')
        for i in range(36,71):
            self.assertEqual(c.current(i),0);c.observe(i,4.)
        self.assertEqual(c.phase,'discharge');self.assertEqual(c.current(71),.012)
        c.observe(71,3.17)
        self.assertEqual(c.completed_cycles,1);self.assertEqual(c.phase,'rest_after_discharge')
        for i in range(72,107):self.assertEqual(c.current(i),0);c.observe(i,3.2)
        self.assertEqual(c.phase,'cc')

    def test_low_current_dwell_resets_and_cannot_terminate_below_voltage(self):
        c=ChargeDischarge({**DEFAULTS,'charge_c':[2.],'taper_hold_s':1.})
        c.current(0);c.observe(0,4.07);c.cv_magnitude=.002
        for i in range(1,20):c.current(i);c.observe(i,4.06)
        c.cv_magnitude=.01;c.current(20);c.observe(20,4.06)
        self.assertEqual(c.low_samples,0)
        c.cv_magnitude=.002;c.low_samples=100
        c.current(21);c.observe(21,4.)
        self.assertEqual(c.phase,'cv')

    def test_variable_discharge_schedule(self):
        c=ChargeDischarge({**DEFAULTS,'discharge_step_s':1.});c.phase='discharge'
        currents=[]
        for i in range(105):currents.append(c.current(i));c.observe(i,3.8)
        for start,value in [(0,.012),(35,.027),(70,.042)]:
            np.testing.assert_array_equal(currents[start:start+35],np.full(35,value))

    def test_invalid_physical_and_grid_settings(self):
        for change in [dict(charge_c=[]),dict(discharge_c=[0]),dict(nominal_capacity_ah=.2),
                       dict(cv_voltage=3.),dict(cv_gain=float('nan')),dict(taper_hold_s=0),
                       dict(charge_c=[.01]),dict(nominal_capacity_ah=1e-7),dict(cycle_rest_s=-1)]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate({**DEFAULTS,**change})

    def test_generation_chunk_invariance_and_controller_event_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paths=[root/'a',root/'b']
            for p in paths:p.mkdir()
            # Lower setpoint deliberately entersCV in a short control; default
            # physical campaign keeps4.06V. It is not tuning of an estimation run.
            settings={**DEFAULTS,'cv_voltage':3.75,'charge_step_s':3.}
            a,t,x=generate(paths[0],CONFIG,500,cells()['B'],'charge-discharge',.03,.004,42,'cycle',chunk=13,charger_settings=settings)
            b,u,y=generate(paths[1],CONFIG,500,cells()['B'],'charge-discharge',.03,.004,42,'cycle',chunk=8192,charger_settings=settings)
            np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(t,u)
            self.assertEqual(x,y)
            self.assertEqual((paths[0]/'stimulus_events.csv').read_bytes(),(paths[1]/'stimulus_events.csv').read_bytes())
            with (paths[0]/'stimulus_events.csv').open() as stream:
                events=list(csv.DictReader(stream))
            transitions=[e for e in events if e['reason']=='measured voltage reached CV setpoint']
            self.assertTrue(transitions)
            for e in transitions:
                i=int(e['record_count'])-1
                self.assertEqual(float(e['measured_voltage_V']),a[i,3])
                self.assertGreaterEqual(a[i,3],settings['cv_voltage'])
            self.assertEqual(sum(x['charger']['phase_records'].values()),500)
            self.assertGreater(x['charger']['charge_Ah'],0.)

    def test_parallel_cccv_arguments_and_trace_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);outputs=[]
            for jobs in [1,2]:
                out=root/str(jobs);outputs.append(out)
                command=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                    '--jobs',str(jobs),'--hours','0.002','--cells','A','B','--loads','charge-discharge',
                    '--charge-step-s','2','--discharge-step-s','2','--cv-voltage','3.75',
                    '--no-plots','--out',str(out)]
                process=subprocess.run(command,capture_output=True,text=True,timeout=60)
                self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            for case in ['case_0000','case_0001']:
                for name in ['observations.npy','truth.npy','stimulus_events.csv','float32_trace.npy','float64_trace.npy']:
                    self.assertEqual((outputs[0]/case/name).read_bytes(),(outputs[1]/case/name).read_bytes())


if __name__=='__main__':unittest.main()
