"""Promotion controls: default means field, explicit controls stay available."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from .backend import arm_kinds
from .run import parser


class FieldDefaultTests(unittest.TestCase):
    def test_default_and_explicit_control_selection(self):
        args=parser().parse_args([])
        self.assertEqual((args.history,args.encoding,args.backend,args.hysteresis_chart),
                         ('joint-field','float64','c','bounded'))
        self.assertEqual(arm_kinds(args),['field64'])
        self.assertEqual(arm_kinds(parser().parse_args(['--history','compare-tangent'])),['field64','tangent64'])
        self.assertEqual(arm_kinds(parser().parse_args(['--history','compare'])),['float64','field64'])
        self.assertEqual(arm_kinds(parser().parse_args(['--history','rolling','--encoding','both'])),['float64','float32'])

    def test_default_campaign_matches_explicit_field_on_identical_stream(self):
        with tempfile.TemporaryDirectory(prefix='mumble-field-default-') as folder:
            root=Path(folder)
            for name,extra in [('default',[]),('explicit',['--history','joint-field','--encoding','float64'])]:
                command=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                         '--hours','.04','--cells','A','--loads','embedded','--load-seeds','7',
                         '--seeds','1100','--noise-v','.002','--recording','compact',
                         '--no-plots','--out',str(root/name),*extra]
                p=subprocess.run(command,capture_output=True,text=True,timeout=60)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            a=root/'default/case_0000';b=root/'explicit/case_0000'
            ra=json.loads((a/'result.json').read_text());rb=json.loads((b/'result.json').read_text())
            self.assertEqual(set(ra['arms']),{'field64'})
            self.assertGreater(ra['arms']['field64']['field_history']['accepted'],0)
            self.assertEqual(ra['arms'],rb['arms'])
            np.testing.assert_array_equal(np.load(a/'field64_message.npy'),np.load(b/'field64_message.npy'))
            with np.load(a/'plot_summary.npz') as av,np.load(b/'plot_summary.npz') as bv:
                for key in av.files:np.testing.assert_array_equal(av[key],bv[key])

    def test_incompatible_options_explain_how_to_select_rolling(self):
        with tempfile.TemporaryDirectory() as folder:
            for extra in [['--encoding','float32'],['--backend','python'],['--hysteresis-chart','legacy']]:
                out=Path(folder)/'not_created'
                p=subprocess.run([sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                                  '--out',str(out),*extra],capture_output=True,text=True)
                self.assertEqual(p.returncode,2)
                self.assertIn('use --history rolling',p.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
