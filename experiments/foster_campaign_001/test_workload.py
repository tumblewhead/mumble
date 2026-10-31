"""Physical/time/RNG contracts for the embedded semi-Markov harness."""
import copy,csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from .workload import EmbeddedWorkload,TRANSITIONS,OPERATIONS,CLOCK_HZ
from .stimulus import generate,cells
from .charger import ChargeDischarge,DEFAULTS,quantize
from .run import parser
ROOT=Path(__file__).resolve().parents[2]
CONFIG=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())

class WorkloadTests(unittest.TestCase):
    def schedule(self,seed=7,rate=50,seconds=60):
        w=EmbeddedWorkload(seed,.03,rate);samples=[];events=[]
        for i in range(round(seconds*rate)):
            samples.append(w.current(i));events+=w.take_events()
        return np.array(samples),events,w.summary()
    def test_reproducibility_distinct_seeds_and_bounds(self):
        a,e,s=self.schedule();b,f,t=self.schedule();c,g,_=self.schedule(seed=8)
        np.testing.assert_array_equal(a,b);self.assertEqual(e,f);self.assertEqual(s,t);self.assertNotEqual(e,g);self.assertFalse(np.array_equal(a,c))
        self.assertTrue(np.all((a>=0)&(a<=.03+1e-15)));self.assertFalse(s['noise_seed_used'])
    def test_rate_independent_events_and_charge(self):
        a,e,_=self.schedule(rate=35);b,f,_=self.schedule(rate=50);c,g,_=self.schedule(rate=100)
        self.assertEqual(e,f);self.assertEqual(e,g)
        self.assertAlmostEqual(a.sum()/35,b.sum()/50,places=12);self.assertAlmostEqual(a.sum()/35,c.sum()/100,places=12)
    def test_legal_transitions_and_positive_dwell(self):
        _,events,_=self.schedule(seconds=600)
        operations=[e for e in events if e['chain']=='operation'];self.assertEqual(operations[0]['state'],'sleep')
        for previous,current in zip(operations,operations[1:]):
            self.assertIn(current['state'],dict(TRANSITIONS[previous['state']]));self.assertEqual(previous['end_us'],current['start_us'])
        for e in operations:
            _,low,high=OPERATIONS[e['state']];self.assertGreaterEqual(e['end_us']-e['start_us'],round(low*CLOCK_HZ));self.assertLessEqual(e['end_us']-e['start_us'],round(high*CLOCK_HZ))
        self.assertEqual(set(OPERATIONS),{e['state'] for e in operations})
    def test_source_order_and_external_discharge(self):
        w=EmbeddedWorkload(7)
        with self.assertRaises(ValueError):w.current(1)
        c=ChargeDischarge(DEFAULTS,50);c.phase='discharge';requested=.00813
        self.assertEqual(c.current(0,requested),quantize(requested));c.observe(0,3.7)
        self.assertAlmostEqual(c.discharge_Ah,quantize(requested)/50/3600)
        self.assertAlmostEqual(c.take_events()[0]['discharge_load_C'],requested/.06)
        c.phase='cc';self.assertEqual(c.current(1,.01),-.12)
        with self.assertRaises(ValueError):c.current(1,float('nan'))
    def test_noise_and_chunk_do_not_change_event_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);arrays=[];events=[]
            for name,noise_seed,chunk in [('a',17,13),('b',18,8192),('c',17,8192)]:
                p=root/name;p.mkdir();obs,truth,result=generate(p,CONFIG,1000,cells()['A'],'embedded',.03,.002,noise_seed,'constant',chunk=chunk,sample_rate_hz=50,load_seed=7)
                self.assertEqual(result['status'],'generated');arrays.append(np.array(obs));events.append((p/'workload_events.csv').read_bytes())
            self.assertEqual(events[0],events[1]);self.assertEqual(events[0],events[2]);np.testing.assert_array_equal(arrays[0],arrays[2]);self.assertFalse(np.array_equal(arrays[0][:,3],arrays[1][:,3]))
    def test_crossed_cli_parallel_and_seed_labels(self):
        from .plot import render_summary
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);results=[]
            for jobs in [1,2]:
                out=root/f'jobs{jobs}'
                cmd=[sys.executable,'-B','-m','experiments.foster_campaign_001.run','--hours','.003','--jobs',str(jobs),'--sample-rate-hz','50','--loads','embedded','--load-seeds','7','8','--seeds','17','18','--cells','A','--encoding','float64','--no-plots','--out',str(out)]
                proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True);self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                summary=json.loads((out/'summary.json').read_text());self.assertEqual(summary['requested_cases'],4);results.append(summary)
                self.assertEqual({(c['scenario']['seed'],c['scenario']['load_seed']) for c in summary['cases']},{(17,7),(17,8),(18,7),(18,8)})
            for case in results[0]['cases']:
                name=case['directory']
                for f in ['observations.npy','truth.npy','float64_trace.npy','workload_events.csv']:
                    self.assertEqual((root/'jobs1'/name/f).read_bytes(),(root/'jobs2'/name/f).read_bytes())
            receipt=render_summary(root/'jobs1')
            for style in receipt['arm_styles']:
                self.assertIn('load seed',style['label']);self.assertIn('noise seed',style['label']);self.assertIn(style['load_seed'],[7,8])
    def test_invalid_seed_rejected_and_old_defaults(self):
        self.assertEqual(parser().parse_args([]).load_seeds,[0]);self.assertEqual(parser().parse_args([]).loads,['cycle'])
        for seed in [-1,1.5]:
            with self.assertRaises(ValueError):EmbeddedWorkload(seed)
        cmd=[sys.executable,'-B','-m','experiments.foster_campaign_001.run','--load-seeds','-1']
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True);self.assertEqual(p.returncode,2)
