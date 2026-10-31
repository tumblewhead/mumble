"""Full-recording parity, checkpoint continuation and bounded summary controls."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from .backend import CBackend
from .compact import Bins, StimulusStream, restore_checkpoint, EventSummary
from .replay import replay
from .telemetry import TRACE_COLUMNS


class CompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='foster-compact-tests-')
        cls.root = Path(cls.temp.name)
        for recording in ['full', 'compact']:
            out = cls.root/recording
            command = [sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                       '--recording',recording,'--backend','c','--hours','0.20002',
                       '--sample-rate-hz','50','--cells','A','--loads','charge-discharge',
                       '--checkpoint-hours','0.01','--summary-bins','37','--no-plots','--out',str(out)]
            process = subprocess.run(command,capture_output=True,text=True,timeout=90)
            if process.returncode:
                raise AssertionError(process.stdout+process.stderr)
        cls.full = cls.root/'full/case_0000'
        cls.case = cls.root/'compact/case_0000'
        cls.config = json.loads((cls.case.parent/'calibration.json').read_text())
        cls.plan = json.loads((cls.case.parent/'campaign_plan.json').read_text())
        cls.result = json.loads((cls.case/'result.json').read_text())
        cls.cell = json.loads((cls.case/'scenario.json').read_text())['cell_definition']
        cls.entries = json.loads((cls.case/'checkpoints/index.json').read_text())['checkpoints']

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_full_stream_and_final_joint_message_are_exact(self):
        inputs = json.loads((self.case/'inputs.json').read_text())
        for name, key in [('observations','observation_sha256'),('truth','truth_sha256')]:
            data = np.load(self.full/(name+'.npy'))
            self.assertEqual(hashlib.sha256(data.astype('<f8').tobytes()).hexdigest(), inputs[key])
            self.assertFalse((self.case/(name+'.npy')).exists())
        full_result = json.loads((self.full/'result.json').read_text())
        for kind in ['float32','float64']:
            np.testing.assert_array_equal(np.load(self.case/(kind+'_message.npy')),
                                          np.load(self.full/(kind+'_message.npy')))
            self.assertEqual(self.result['arms'][kind], full_result['arms'][kind])
            self.assertFalse((self.case/(kind+'_trace.npy')).exists())
            self.assertFalse((self.case/(kind+'_trace.csv')).exists())
        self.assertEqual(self.result['encoding_difference'],full_result['encoding_difference'])
        self.assertFalse((self.case/'stimulus_events.csv').exists())
        stream = StimulusStream(self.config,self.cell,self.result['scenario'],self.plan['configuration'])
        events = EventSummary()
        while stream.index < self.result['records']:
            _, _, rows = stream.read(min(8192,self.result['records']-stream.index))
            events.add(rows)
        saved=json.loads((self.case/'events_summary.json').read_text())
        self.assertEqual(events.result(),saved['controller'])

    def test_summary_extrema_means_derived_errors_and_counts(self):
        obs, truth = [np.load(self.full/(name+'.npy')) for name in ['observations','truth']]
        with np.load(self.case/'plot_summary.npz') as summary:
            self.assertEqual(int(summary['plant_count'].sum()), len(obs))
            self.assertLessEqual(len(summary['plant_count']),37)
            np.testing.assert_array_equal(summary['plant_low'].min(axis=0)[:5],obs.min(axis=0))
            np.testing.assert_array_equal(summary['plant_high'].max(axis=0)[5:22],truth.max(axis=0))
            for kind in ['float32','float64']:
                rows = np.load(self.full/(kind+'_trace.npy'))[:self.result['arms'][kind]['outputs']]
                expected = 100*(rows[:,11]/truth[rows[:,0].astype(int)-1,5]-1)
                col = len(TRACE_COLUMNS)+32
                self.assertEqual(summary[kind+'_count'].sum(),len(rows))
                self.assertEqual(summary[kind+'_low'][:,col].min(),expected.min())
                self.assertEqual(summary[kind+'_high'][:,col].max(),expected.max())
                np.testing.assert_allclose(np.average(summary[kind+'_mean'][:,col],weights=summary[kind+'_count']),
                                           expected.mean(),rtol=1e-13,atol=1e-13)
        self.assertLess((self.case/'plot_summary.npz').stat().st_size,150000)

    def test_midrun_replay_exact_including_full_joint_state(self):
        out = self.root/'replay_middle'
        result = replay(self.case,out,593.17/3600,10.13,plots=False)
        self.assertGreater(result['checkpoint']['sequence'],0)
        start = result['record_offset'];end = start+result['records']
        for name in ['observations','truth']:
            np.testing.assert_array_equal(np.load(out/(name+'.npy')),
                                          np.load(self.full/(name+'.npy'))[start:end])
        obs = np.load(self.full/'observations.npy')
        for kind in ['float32','float64']:
            original = np.load(self.full/(kind+'_trace.npy'))
            select = (original[:,0]>start)&(original[:,0]<=end)
            count = result['arms'][kind]['outputs']
            np.testing.assert_array_equal(np.load(out/(kind+'_trace.npy'))[:count],original[select])
            np.testing.assert_array_equal(np.load(out/(kind+'_chart.npy'))[:count],
                                          np.load(self.full/(kind+'_chart.npy'))[select])
            # Independently advance from the prior, not from another checkpoint.
            bank = CBackend(self.case.parent,self.config,self.result['source_id'],
                            self.result['model_id'],kind,50)
            stop = result['solver_stop_record']
            for first in range(0,stop,16):
                bank.advance(first,obs[first:min(first+16,stop)])
            np.testing.assert_array_equal(bank.full_message(),np.load(out/(kind+'_message.npy')))

    def test_replay_from_initial_and_final_partial_interval(self):
        for label, start, duration in [('initial',.17,1.11),('end',719.13,4.)]:
            out = self.root/label
            result = replay(self.case,out,start/3600,duration,plots=False)
            first = result['record_offset'];end = first+result['records']
            np.testing.assert_array_equal(np.load(out/'observations.npy'),
                                          np.load(self.full/'observations.npy')[first:end])
            for kind in ['float32','float64']:
                full = np.load(self.full/(kind+'_trace.npy'))
                np.testing.assert_array_equal(np.load(out/(kind+'_trace.npy'))[:result['arms'][kind]['outputs']],
                                              full[(full[:,0]>first)&(full[:,0]<=end)])

    def test_checkpoint_rejects_checksum_runtime_and_recipe_mismatch(self):
        entry = copy.deepcopy(self.entries[1]);entry['sha256']='0'*64
        args = (self.config,self.cell,self.result['scenario'],self.plan['configuration'])
        with self.assertRaisesRegex(ValueError,'checksum'):
            restore_checkpoint(self.case,entry,*args)
        with patch('experiments.foster_campaign_001.compact.runtime_identity',return_value={}):
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                restore_checkpoint(self.case,self.entries[1],*args)
        path = self.case/'scenario.json';original=path.read_bytes()
        try:
            path.write_bytes(original+b' ')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                restore_checkpoint(self.case,self.entries[1],*args)
        finally:
            path.write_bytes(original)

    def test_explicit_debug_window_flags_and_invalid_ranges(self):
        out=self.root/'explicit_window'
        command=[sys.executable,'-B','-m','experiments.foster_campaign_001.replay',str(self.case),
                 '--debug-start-hour','0.16','--debug-stop-hour','0.17','--no-plots','--out',str(out)]
        process=subprocess.run(command,capture_output=True,text=True,timeout=60)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        result=json.loads((out/'result.json').read_text())
        self.assertEqual(result['record_offset'],28800)
        self.assertEqual(result['records'],1800)
        np.testing.assert_array_equal(np.load(out/'observations.npy'),np.load(self.full/'observations.npy')[28800:30600])
        for options in [['--debug-stop-hour','0.1'],['--debug-stop-hour','nan'],
                        ['--debug-stop-hour','0.17','--duration-s','1']]:
            command=[sys.executable,'-B','-m','experiments.foster_campaign_001.replay',str(self.case),
                     '--debug-start-hour','0.16','--out',str(self.root/'bad_window'),*options]
            process=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(process.returncode,2)
            self.assertFalse((self.root/'bad_window').exists())

    def test_summary_binning_preserves_spikes_independent_of_chunk_size(self):
        a,b = Bins(10003,17,2),Bins(10003,17,2)
        values = np.ones((10003,2));values[4444,0]=1e6;values[7777,1]=-1e6
        counts = np.arange(1,10004)
        a.add(counts,values)
        for first in range(0,len(values),113):
            b.add(counts[first:first+113],values[first:first+113])
        for name in ['count','first','last','low','high','total']:
            np.testing.assert_array_equal(getattr(a,name),getattr(b,name))
        self.assertEqual(a.high[:,0].max(),1e6)
        self.assertEqual(a.low[:,1].min(),-1e6)

    def test_stream_snapshot_across_rates_and_controller_transitions(self):
        for rate in [10,35,50]:
            settings = dict(self.plan['configuration'],sample_rate_hz=rate)
            cell = copy.deepcopy(self.cell);cell['initial_state'][0]=.90
            a = StimulusStream(self.config,cell,self.result['scenario'],settings)
            a.read(23)
            self.assertEqual(a.controller.phase,'cv')
            state = json.loads(json.dumps(a.snapshot()))
            expected = a.read(129)
            b = StimulusStream(self.config,cell,self.result['scenario'],settings)
            b.restore(state)
            actual = b.read(129)
            for i in [0,1]:
                np.testing.assert_array_equal(expected[i],actual[i])
            self.assertEqual(expected[2],actual[2])
            self.assertEqual(a.snapshot(),b.snapshot())

    def test_cli_rejects_invalid_compact_settings_before_creating_output(self):
        for options in [['--backend','python'],['--sample-csv'],['--summary-bins','0'],['--checkpoint-hours','nan']]:
            out=self.root/'invalid'
            p=subprocess.run([sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                              '--recording','compact','--out',str(out),*options],capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stdout+p.stderr)
            self.assertFalse(out.exists())

    def test_failure_checkpoint_replay_preserves_original_failure_boundary(self):
        out = self.root/'failed_run'
        command = [sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                   '--recording','compact','--hours','0.14','--sample-rate-hz','50',
                   '--cells','A','--loads','charge-discharge','--noise-v','0.02','--seeds','1104',
                   '--hysteresis-chart','legacy',
                   '--checkpoint-hours','0.01','--summary-bins','37','--no-plots','--out',str(out)]
        process = subprocess.run(command,capture_output=True,text=True,timeout=60)
        self.assertEqual(process.returncode,1,process.stdout+process.stderr)
        case = out/'case_0000'
        result = json.loads((case/'result.json').read_text())
        self.assertEqual(json.loads((case/'inputs.json').read_text())['status'],'generated_prefix')
        detail = replay(case,self.root/'failed_detail',400/3600,60,plots=False)
        self.assertEqual(detail['status'],'unresolved')
        with self.assertRaisesRegex(ValueError,'recorded plant prefix'):
            replay(case,self.root/'after_failure',503/3600,1,plots=False)
        for kind in ['float32','float64']:
            self.assertEqual(detail['arms'][kind]['failure'],result['arms'][kind]['failure'])
            self.assertEqual(detail['arms'][kind]['retired_records'],result['arms'][kind]['retired_records'])
            np.testing.assert_array_equal(np.load(case/(kind+'_message.npy')),
                                          np.load(self.root/'failed_detail'/(kind+'_message.npy')))


if __name__ == '__main__':
    unittest.main()
