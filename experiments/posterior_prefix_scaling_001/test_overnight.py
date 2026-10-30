"""Input continuity and dispatch tests; no posterior sampling."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from generate import generate
from overnight import HERE, execute, prepare


class OvernightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run=Path(self.temp.name)/'run'
        with contextlib.redirect_stdout(io.StringIO()):prepare(self.run)

    def test_original_generator_default_unchanged(self):
        out=Path(self.temp.name)/'original'
        generate(out)
        for name in ('observations_8.json','observations_32.json','observations_128.json',
                     'plant_truth_not_inference.json','inference.json'):
            self.assertEqual((out/name).read_bytes(),(HERE/'attempt001/inputs'/name).read_bytes(),name)

    def test_extended_stream_and_inference_boundary(self):
        checks=json.loads((self.run/'input_checks.json').read_text())
        self.assertTrue(all(checks['checks'].values()))
        rows=json.loads((self.run/'inputs/observations_256.json').read_text())['records']
        self.assertEqual(len(rows),256)
        self.assertEqual(rows[128]['index'],128)
        self.assertEqual(rows[128]['dt'],rows[0]['dt'])
        cfg=json.loads((self.run/'inputs/inference.json').read_text())
        self.assertEqual(cfg['mutations'],192)
        self.assertEqual(cfg['particle_levels'],[2048,4096])
        self.assertEqual(cfg['replicates_per_level'],4)
        self.assertEqual(cfg['max_stages'],96)
        baseline=json.loads((HERE/'attempt001/inputs/inference.json').read_text())
        for key in baseline.keys()-{'mutations','max_paths_per_population','caps','prefixes'}:
            self.assertEqual(cfg[key],baseline[key],key)
        self.assertNotIn('plant_initial_x',cfg)
        self.assertNotIn('generation_seed',cfg)
        self.assertEqual({p.name for p in (self.run/'inputs').iterdir()},
                         {'observations_128.json','observations_256.json','inference.json'})
        # Include a worst-case64 batches of prior rejection plus initial evaluation.
        for n in (128,256):
            paths_per_particle=64+1+cfg['max_stages']*cfg['mutations']
            self.assertLessEqual(4096*paths_per_particle,cfg['max_paths_per_population'])
            self.assertLessEqual(4*sum(cfg['particle_levels'])*paths_per_particle*n,
                                 cfg['caps']['prefix_conservative_steps'][str(n)])

    def test_unresolved128_continues_and_labels256(self):
        calls=[]
        def fake(run,n):
            calls.append(n)
            return 'uncertainty_unresolved' if n==128 else 'finite_moment_checks_passed'
        execute(self.run,fake)
        self.assertEqual(calls,[128,256])
        self.assertTrue(json.loads((self.run/'summary.json').read_text())['prefix256_exploratory'])
        with self.assertRaises(FileExistsError):execute(self.run,fake)
        self.assertEqual(calls,[128,256])

    def test_passing128_labels_progression(self):
        execute(self.run,lambda run,n:'finite_moment_checks_passed')
        self.assertFalse(json.loads((self.run/'summary.json').read_text())['prefix256_exploratory'])

    def test_execution_error_stops_dispatch(self):
        calls=[]
        def fake(run,n):
            calls.append(n)
            raise RuntimeError('execution failed')
        with self.assertRaises(RuntimeError):execute(self.run,fake)
        self.assertEqual(calls,[128])
        self.assertFalse((self.run/'summary.json').exists())

    def test_changed_input_blocks_inference(self):
        with (self.run/'inputs/observations_256.json').open('a') as f:f.write(' ')
        calls=[]
        with self.assertRaisesRegex(RuntimeError,'Input changed'):
            execute(self.run,lambda run,n:calls.append(n))
        self.assertEqual(calls,[])
        self.assertFalse((self.run/'started.json').exists())

    def test_source_binding_blocks_inference(self):
        path=self.run/'provenance.json'
        p=json.loads(path.read_text())
        next(iter(p['sources'].values()))['sha256']='wrong'
        path.write_text(json.dumps(p))
        with self.assertRaisesRegex(RuntimeError,'Source changed'):execute(self.run)
        self.assertFalse((self.run/'started.json').exists())


if __name__=='__main__':unittest.main()
