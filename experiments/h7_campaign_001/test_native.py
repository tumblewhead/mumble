import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from experiments.hysteresis_refinement_001 import test_field as fixture
from experiments.hysteresis_refinement_001.field import MixedField,features_jacobian,transported
from experiments.field_tangent_native_001.native import Native,build


class H7NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MixedTests.setUpClass();cls.s=fixture.MixedTests();cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)
        cls.binary=build(cls.path/'h7',7);cls.oldbinary=build(cls.path/'h5',5)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup();fixture.MixedTests.tearDownClass()
    def test_H5_matches_frozen_preintegration_native_bitwise(self):
        path=Path('/home/easy/proj/mumble/.worktrees/field-comparison-plots/experiments/field_tangent_native_001/native.py')
        if not path.exists():self.skipTest('frozen preintegration worktree unavailable')
        spec=importlib.util.spec_from_file_location('frozen_h5_native',path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        binary=old.build(self.path/'frozen_h5');f=self.s.field(5);g=self.s.field(5)
        a=Native(self.oldbinary,f,self.s.mean,self.s.L);b=old.Native(binary,g,self.s.mean,self.s.L)
        a.initialize(np.zeros(16));b.initialize(np.zeros(16));sa=f.state.copy();sb=g.state.copy()
        for first in range(0,len(self.s.obs),16):
            obs=self.s.obs[first:first+16];a.step(first,obs,sa,1000);b.step(first,obs,sb,1000)
            np.testing.assert_array_equal(a.snapshot(),b.snapshot());np.testing.assert_array_equal(sa,sb)
            qa=a.query(state=sa,count=first+len(obs),reuse=True);qb=b.query(state=sb,count=first+len(obs),reuse=True)
            for key in ('w','x','end','endpoint_root'):np.testing.assert_array_equal(qa[key],qb[key])

    def test_projection_matches_mixed_analytic_derivative(self):
        f=self.s.field(7);a=Native(self.binary,f,self.s.mean,self.s.L);rng=np.random.default_rng(18)
        for _ in range(12):
            x=self.s.mean+self.s.L@rng.uniform(-.2,.2,16);row=rng.normal(size=f.width)
            r,g=a.projection(x,row)
            self.assertAlmostEqual(r,float(row@f.features(x)),places=10)
            np.testing.assert_allclose(g,row@features_jacobian(f,x),rtol=2e-12,atol=2e-11)
    def test_full_joint_batch_reference(self):
        f=self.s.field(7);obs=self.s.obs;f.update(0,obs[:128])
        L=self.s.L@(np.eye(16)+np.tril(np.full((16,16),.015),-1));w=np.linspace(-.02,.02,16);x=self.s.mean+L@w
        a=Native(self.binary,f,self.s.mean,L);a.initialize(w)
        phi=f.features(x);J=features_jacobian(f,x)@L
        B=np.vstack([np.eye(16),f.root@J]);r=np.r_[w,f.root@phi]
        for first in range(128,len(obs),16):
            rows=f.update(first,obs[first:first+16],return_rows=True);a.update(first,rows)
            B=np.vstack([B,rows@J]);r=np.r_[r,rows@phi]
            Q,R=np.linalg.qr(B,mode='reduced');delta=np.linalg.solve(R,-Q.T@r)
            expected=self.s.mean+L@(w+delta);end,D=transported(f,expected)
            root=D@L@np.linalg.solve(R,np.eye(16));out=a.query()
            np.testing.assert_allclose(out['end'],end,atol=5e-9,rtol=2e-8)
            np.testing.assert_allclose(out['endpoint_root']@out['endpoint_root'].T,root@root.T,atol=2e-11,rtol=2e-7)
    def test_fused_matches_rows_update_and_snapshot(self):
        f=self.s.field(7);g=self.s.field(7);a=Native(self.binary,f,self.s.mean,self.s.L);b=Native(self.binary,g,self.s.mean,self.s.L)
        a.initialize(np.zeros(16));b.initialize(np.zeros(16));state=f.state.copy()
        for first in range(0,len(self.s.obs),16):
            obs=self.s.obs[first:first+16];rows=g.rows(first,obs)
            b.update(first,rows);a.step(first,obs,state,1000)
            np.testing.assert_array_equal(a.snapshot(),b.snapshot());np.testing.assert_array_equal(state,g.state)
            for key in ('w','end','endpoint_root'):
                np.testing.assert_array_equal(a.query(state=state,count=first+len(obs),reuse=True)[key],b.query()[key])
        clone=Native(self.binary,g,self.s.mean,self.s.L);clone.restore(a.snapshot(),len(self.s.obs))
        np.testing.assert_array_equal(clone.query()['end'],b.query()['end'])
    def test_reject_wrong_binary_and_cross_degree_checkpoint(self):
        with self.assertRaisesRegex(ValueError,'representation mismatch'):Native(self.oldbinary,self.s.field(7),self.s.mean,self.s.L)
        h5=Native(self.oldbinary,self.s.field(5),self.s.mean,self.s.L);h5.initialize(np.zeros(16))
        h7=Native(self.binary,self.s.field(7),self.s.mean,self.s.L);h7.initialize(np.zeros(16));saved=h7.snapshot()
        with self.assertRaises(ValueError):h7.restore(h5.snapshot(),0)
        np.testing.assert_array_equal(saved,h7.snapshot())
    def test_fused_failure_atomicity_and_null_information(self):
        f=self.s.field(7);a=Native(self.binary,f,self.s.mean,self.s.L);a.initialize(np.zeros(16));state=f.state.copy();old=a.snapshot()
        obs=self.s.obs[:16].copy();obs[-1,4]=0
        with self.assertRaises(ValueError):a.step(0,obs,state,1000)
        np.testing.assert_array_equal(state,f.state);np.testing.assert_array_equal(old,a.snapshot())
        obs=self.s.obs[:16].copy();obs[:,1]=0;a.step(0,obs,state,1000)
        result=a.query(state=state,count=16)
        self.assertAlmostEqual(result['x'][5],self.s.mean[5],places=10)
        self.assertAlmostEqual(np.linalg.norm(result['endpoint_root'][5]),np.linalg.norm(self.s.L[5]),places=10)

if __name__=='__main__':unittest.main()
