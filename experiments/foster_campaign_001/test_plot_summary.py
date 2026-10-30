"""Overlay controls using small saved telemetry fixtures, without solver runs."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')
import numpy as np

from .plot import render, render_summary
from .telemetry import PARAMETERS, TRACE_COLUMNS


class SummaryPlotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'calibration.json').write_text('{}')
        reports = []
        for index, n in enumerate([32, 48]):
            case = self.root/f'case_{index:04d}'
            case.mkdir()
            obs = np.ones((n, 5))
            obs[:, 0] = 1/35
            obs[:, 1] = index + np.arange(n)/100
            truth = np.ones((n, 17))
            truth[:, 0] = .4 + index/10
            truth[:, 5] = .06
            truth[:, 16] = 3.7
            np.save(case/'observations.npy', obs)
            np.save(case/'truth.npy', truth)
            # Sentinel padding must never appear in an unresolved arm's plots.
            rows = np.full((5, len(TRACE_COLUMNS)), 999.)
            valid = n//16
            rows[:valid] = 1.
            rows[:valid, 0] = np.arange(1, valid+1)*16
            rows[:valid, 1] = rows[:valid, 0]/35
            rows[:valid, 4] = 3.7
            rows[:valid, 5] = 3.702
            rows[:valid, 6] = truth[0, 0]+.002
            rows[:valid, 11] = .06012
            kinds = ['float32'] if index else ['float32', 'float64']
            for kind in kinds:
                np.save(case/(kind+'_trace.npy'), rows)
            report = dict(directory=case.name, status='unresolved' if index else 'completed',
                          scenario=dict(cell=str(index), load='pulses', noise_v=.002, seed=index),
                          arms={kind: dict(outputs=valid) for kind in kinds})
            cell = dict(parameters={name: 1. for name in PARAMETERS})
            (case/'scenario.json').write_text(json.dumps(dict(cell_definition=cell)))
            (case/'result.json').write_text(json.dumps(report))
            (case/'signals.png').write_bytes(b'preserved individual plot')
            reports.append(report)
        reports.append(dict(directory='case_0002', status='plant_failed'))
        (self.root/'summary.json').write_text(json.dumps(dict(cases=reports)))

    def test_overlays_keep_values_times_valid_prefix_and_individual_files(self):
        captured = {}

        def inspect(fig, axes, destination, name, heading, title):
            captured[name] = axes

        with patch('experiments.foster_campaign_001.plot.save_plot', side_effect=inspect):
            receipt = render_summary(self.root)
        self.assertEqual(len(captured), 6)
        self.assertEqual(len(receipt['included']), 2)
        self.assertEqual(receipt['skipped'][0]['directory'], 'case_0002')
        current = captured['signals'][1].lines
        self.assertEqual([len(line.get_ydata()) for line in current], [32, 48])
        for index, line in enumerate(current):
            np.testing.assert_allclose(line.get_ydata(), index+np.arange(len(line.get_ydata()))/100)
            self.assertEqual(line.get_alpha(), .8)
            self.assertAlmostEqual(line.get_xdata()[-1], [32,48][index]/126000)
        q_lines = captured['errors'][0].lines
        self.assertEqual([len(line.get_ydata()) for line in q_lines], [2, 2, 3])
        for line in q_lines:
            np.testing.assert_allclose(line.get_ydata(), .2, atol=1e-12)
        for line in captured['errors'][1].lines:
            np.testing.assert_allclose(line.get_ydata(), .2, atol=1e-12)
        for line in captured['errors'][2].lines:
            if '/ float' in line.get_label():
                np.testing.assert_allclose(line.get_ydata(), 2., atol=1e-12)
        # Reference bands/zero lines are drawn once, not once per case.
        self.assertEqual(len(captured['errors'][0].patches), 1)
        self.assertEqual(len(captured['errors'][2].lines), 4)
        for case in ['case_0000', 'case_0001']:
            self.assertEqual((self.root/case/'signals.png').read_bytes(), b'preserved individual plot')
        with self.assertRaises(FileExistsError):
            render_summary(self.root)

    def test_zoom_skips_short_case_and_individual_opacity_stays_opaque(self):
        with patch('experiments.foster_campaign_001.plot.save_plot') as save:
            receipt = render_summary(self.root, start_hour=33/126000)
            self.assertEqual([r['directory'] for r in receipt['included']], ['case_0001'])
            self.assertEqual(len(receipt['skipped']), 2)
            self.assertEqual(save.call_count, 6)
        case = self.root/'case_0000'
        report = json.loads((case/'result.json').read_text())
        cell = json.loads((case/'scenario.json').read_text())['cell_definition']
        with patch('experiments.foster_campaign_001.plot.save_plot') as save:
            render(case, report, {}, cell, self.root/'individual')
            axes = save.call_args_list[0].args[1]
            self.assertTrue(all(line.get_alpha() == 1. for line in axes[0].lines))
        import matplotlib.pyplot as plt
        plt.close('all')



# Style and case identity must survive zooms and duplicate seeds.
class SummaryIdentityTests(unittest.TestCase):
    setUp = SummaryPlotTests.setUp
    def test_each_arm_has_unique_label_color_and_precision_style(self):
        import matplotlib.pyplot as plt
        captured={}
        def inspect(fig,axes,destination,name,heading,title):captured[name]=axes
        with patch('experiments.foster_campaign_001.plot.save_plot',side_effect=inspect):
            receipt=render_summary(self.root)
        lines=captured['errors'][0].lines
        self.assertEqual(len(set(line.get_label() for line in lines)),3)
        self.assertEqual(len(set(tuple(line.get_color()) for line in lines)),3)
        for line in lines:
            self.assertIn('seed ',line.get_label())
            self.assertEqual(line.get_linestyle(),'--' if 'float32' in line.get_label() else '-')
        self.assertEqual(len(receipt['arm_styles']),3)
        plt.close('all')
    def test_duplicate_seed_disambiguation_and_color_stability(self):
        path=self.root/'summary.json';data=json.loads(path.read_text())
        data['cases'][1]['scenario']['seed']=0;path.write_text(json.dumps(data))
        with patch('experiments.foster_campaign_001.plot.save_plot'):
            full=render_summary(self.root)
            zoom=render_summary(self.root,self.root/'zoom',start_hour=33/126000)
        self.assertEqual(full['arm_styles'],zoom['arm_styles'])
        self.assertEqual(len({a['label'] for a in full['arm_styles']}),3)
        self.assertTrue(all('case_' in a['label'] for a in full['arm_styles']))
        import matplotlib.pyplot as plt
        plt.close('all')

if __name__ == '__main__':
    unittest.main()
