"""Short process-level controls for --jobs; no long estimation sweep."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from experiments.foster_campaign_001.execution import THREAD_ENV, process_case
from experiments.foster_campaign_001.stimulus import cells


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def campaign(self,name,*options,expected=0):
        out=self.root/name
        command=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                 '--hours','0.02','--no-plots','--out',str(out),*options]
        # The CLI must set its budget even when the shell requests more threads.
        process=subprocess.run(command,capture_output=True,text=True,
                               env={**os.environ,**{k:'4' for k in THREAD_ENV}},timeout=60)
        self.assertEqual(process.returncode,expected,process.stdout+process.stderr)
        return out,json.loads((out/'summary.json').read_text())

    def test_serial_parallel_identical_and_concurrent(self):
        options=['--cells','A','B','--seeds','17','29','--loads','multiscale']
        serial,a=self.campaign('serial','--jobs','1',*options)
        parallel,b=self.campaign('parallel','--jobs','2',*options)
        self.assertEqual(b['effective_jobs'],2)
        self.assertEqual(b['completed_cases'],4)
        self.assertEqual([r['directory'] for r in b['cases']],['case_%04d'%i for i in range(4)])
        workers=[]
        for ra,rb in zip(a['cases'],b['cases']):
            self.assertEqual(ra['scenario'],rb['scenario'])
            self.assertEqual(ra['arms'],rb['arms'])
            ca=serial/ra['directory'];cb=parallel/rb['directory']
            for file in ['observations.npy','truth.npy','float32_trace.npy','float64_trace.npy',
                         'float32_chart.npy','float64_chart.npy','float32_trace.csv','float64_trace.csv']:
                self.assertEqual((ca/file).read_bytes(),(cb/file).read_bytes(),file)
            worker=json.loads((cb/'worker.json').read_text());workers.append(worker)
            self.assertEqual(worker['native_thread_environment'],THREAD_ENV)
        self.assertGreater(len({w['pid'] for w in workers}),1)
        events=sorted([(w['started_ns'],1) for w in workers]+[(w['finished_ns'],-1) for w in workers])
        active=0;maximum=0
        for _,delta in events:active+=delta;maximum=max(maximum,active)
        self.assertEqual(maximum,2,'two workers must overlap without exceeding --jobs')

    def test_parallel_failure_continues_and_jobs_cap(self):
        bad=copy.deepcopy(cells()['B']);bad['parameters']['Q_Ah']=1e-7
        fixture=self.root/'cells.json';fixture.write_text(json.dumps({'bad':bad}))
        out,result=self.campaign('failure','--jobs','8','--cell-file',str(fixture),
                                 '--cells','bad','B','--loads','pulses','--encoding','float32',expected=1)
        self.assertEqual(result['effective_jobs'],2)
        self.assertEqual(result['status'],'completed_with_failures')
        self.assertEqual([r['status'] for r in result['cases']],['plant_failed','completed'])
        self.assertTrue((out/'manifest.json').is_file())
        self.assertEqual(result['cases'][1]['arms']['float32']['retired_records'],2520)

    def test_jobs_validation_before_creating_output(self):
        for bad in ['0','-2','1.5']:
            out=self.root/('invalid_'+bad)
            r=subprocess.run([sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                              '--jobs',bad,'--out',str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,2)
            self.assertIn('--jobs',r.stderr)
            self.assertFalse(out.exists())

    def test_crashed_worker_preserves_partial_result(self):
        case=self.root/'case_0000';case.mkdir()
        original='{"status":"completed"}\n';(case/'result.json').write_text(original)
        with patch('experiments.foster_campaign_001.execution.subprocess.run') as run:
            run.return_value.returncode=-9
            result=process_case(self.root,0,dict(cell='B'))
        self.assertEqual(result['status'],'execution_failed')
        self.assertEqual((case/'result.json').read_text(),original)
        self.assertTrue((case/'worker_failure.json').is_file())


if __name__=='__main__':
    unittest.main()
