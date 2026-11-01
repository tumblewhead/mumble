"""Error transformations preserve saved evidence and agree across recording modes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from .plot import select_arms,parameter_error,render
from .error_comparison import error_bins,render_error_comparisons
from .telemetry import PARAMETERS

class ParameterErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.truth=np.array([.06,.1,.04,.05,.08,.5,.12,5,.015,6,9]);self.rows=np.ones((18,39))
        self.rows[:16,0]=np.arange(1,17)*16;self.rows[:16,1]=self.rows[:16,0]/50
        self.rows[:16,22:33]=self.truth*(1+np.linspace(-.2,.3,16)[:,None]*np.linspace(.5,1.5,11)[None,:]);self.rows[16:]=99999
        self.report=dict(directory='case_0000',recording='full',sample_rate_Hz=50,scenario=dict(cell='A',load='cycle',noise_v=.002,seed=7),arms={a:dict(outputs=16) for a in ('field64','tangent64')})
        self.case=self.path/'case_0000';self.case.mkdir();self.cell=dict(parameters=dict(zip(PARAMETERS,self.truth)))
        (self.case/'scenario.json').write_text(json.dumps(dict(cell_definition=self.cell)))
        z={}
        for arm in self.report['arms']:
            np.save(self.case/(arm+'_trace.npy'),self.rows)
            blocks=self.rows[:16].reshape(2,8,39)
            z.update({arm+'_first':blocks[:,0,0],arm+'_last':blocks[:,-1,0],arm+'_count':np.full(2,8)})
            for name,fn in [('mean',np.mean),('low',np.min),('high',np.max)]:
                z[arm+'_'+name]=np.pad(fn(blocks,axis=1),((0,0),(0,36)))
        z.update(plant_first=z['field64_first'],plant_last=z['field64_last'],plant_count=np.full(2,128))
        for name in ('mean','low','high'):z['plant_'+name]=np.ones((2,25))
        np.savez(self.case/'plot_summary.npz',**z)
    def test_default_filter_and_explicit_selection_do_not_mutate_result(self):
        result=dict(arms={a:{} for a in ('float64','field64','tangent64')})
        self.assertEqual(list(select_arms(result)['arms']),['field64','tangent64'])
        self.assertEqual(list(select_arms(result,['float64'])['arms']),['float64'])
        self.assertEqual(len(result['arms']),3)
    def test_full_and_compact_mean_min_max_errors_match(self):
        full=error_bins(self.case,self.report,'field64',self.truth,points=2)
        compact=error_bins(self.case,dict(self.report,recording='compact'),'field64',self.truth)
        for key in full:np.testing.assert_allclose(full[key],compact[key],rtol=1e-13,atol=1e-13)
        np.testing.assert_allclose(full['low'][0],-20*np.linspace(.5,1.5,11),atol=1e-13)
        self.assertLess(abs(full['high']).max(),100)
    def test_compact_parameter_errors_preserve_all_three_statistics(self):
        captured={}
        def save(fig,axes,destination,name,heading,title):captured[name]=axes
        with patch('experiments.foster_campaign_001.plot.save_plot',side_effect=save):
            render(self.case,dict(self.report,recording='compact'),{},self.cell,self.path/'plots')
        ax=captured['parameter_errors'][0]
        expected=error_bins(self.case,dict(self.report,recording='compact'),'field64',self.truth)
        np.testing.assert_allclose(ax.lines[0].get_ydata(),np.repeat(expected['mean'][:,0],2))
        self.assertEqual([v.get_label() for v in ax.lines[:2]],['field64 (bin mean/range)','tangent64 (bin mean/range)'])
        import matplotlib.pyplot as plt
        plt.close('all')
    def test_facets_have_only_selected_arms_and_case_identity(self):
        captured=[]
        def save(fig,*args,**kwargs):
            captured.append([(ax.get_title(),[line.get_label() for line in ax.lines]) for ax in fig.axes])
        with patch('matplotlib.figure.Figure.savefig',new=save):
            files=render_error_comparisons(self.path,[dict(self.report,recording='compact')],self.path/'facets')
        self.assertEqual(len(files),22)
        self.assertIn('case_0000',captured[0][0][0])
        self.assertEqual(captured[0][0][1][:2],['field64','tangent64'])

if __name__=='__main__':unittest.main()
