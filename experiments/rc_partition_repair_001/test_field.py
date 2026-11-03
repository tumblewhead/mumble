import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from .field import PartitionField,build,features_jacobian,transported,Compressed
from .readouts import add_readouts
from experiments.hysteresis_sensitivity_basis_001.run import field as oldfield
from experiments.foster_feedback_001.estimator import Model


class PartitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.binary={k:build(Path(cls.tmp.name)/str(k),k) for k in [2,5]}
        cls.directory=Path('experiments/rc_sensitivity_basis_001/full001')
        cls.reg=json.loads((cls.directory/'registration.json').read_text())
        cls.hbins={k:Path('experiments/hysteresis_sensitivity_basis_001/build001')/k/'response.so' for k in ['derivative','collocation']}
        cls.model=Model(cls.directory/'backend_c/estimator.so',cls.reg['config'])
        cls.mean,cls.L,cls.center=map(np.asarray,[cls.reg['prior_mean'],cls.reg['prior_root'],cls.reg['center']])
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def make(self,degree=5,forced=2):
        return PartitionField(self.reg['config'],self.center,self.directory/'response_taylor2/response.so',
            self.hbins['derivative'],self.binary[forced],degree,forced)
    def fixture(self):
        k=np.arange(512)
        return np.c_[np.array([0.,1/35,.2,.7])[k%4],np.array([.12,-.08,0.])[(k//17)%3],np.full(512,25.),np.full(512,3.7),np.full(512,.001)]
    def old(self,name):return oldfield(name,self.reg,self.directory,'fixture',self.hbins)

    def test_rows_partition_controls(self):
        o=self.fixture();base=self.old('TaylorRC_TaylorH2');wide=self.old('R5_H7')
        br=base.rows(0,o);wr=wide.rows(0,o)
        for degree,forced in [(3,2),(5,2),(5,5)]:
            f=self.make(degree,forced);r=f.rows(0,o);n=f.n;nu=f.nu;col=3
            np.testing.assert_array_equal(r[:,:3],br[:,:3])
            for j in range(3):
                if degree==5:np.testing.assert_array_equal(r[:,col:col+n],wr[:,3+12*j:3+12*j+6])
                col+=n
                expected=br[:,3+6*j+3:3+6*j+6] if forced==2 else wr[:,3+12*j+6:3+12*j+12]
                np.testing.assert_array_equal(r[:,col:col+nu],expected);col+=nu
            np.testing.assert_array_equal(r[:,col:],br[:,21:])

    def test_zero_origin_and_later_rest(self):
        o=self.fixture();o[:,1]=0;f=self.make();wide=self.old('R5_H7')
        r=f.rows(0,o);wr=wide.rows(0,o)
        for j in range(3):np.testing.assert_array_equal(r[:,3+9*j+6:3+9*j+9],0.)
        x=self.mean+self.L@(.05*(-1.)**np.arange(16))
        np.testing.assert_allclose(r@f.features(x),wr@wide.features(x),atol=2e-10,rtol=0)
        np.testing.assert_allclose(r@features_jacobian(f,x),wr@features_jacobian(wide,x),atol=2e-9,rtol=1e-10)
        active=self.fixture();f=self.make();f.rows(0,active);before=f.state[3*f.n:6*f.n].copy()
        f.rows(len(active),o[:1]+np.array([.03,0,0,0,0]))
        self.assertGreater(np.linalg.norm(before),1e-6);self.assertGreater(np.linalg.norm(f.state[3*f.n:6*f.n]),1e-6)

    def test_feature_transport_derivatives_and_covariance(self):
        o=self.fixture();x=self.mean+self.L@(.05*(-1.)**np.arange(16));eps=2e-6
        for degree,forced in [(3,2),(5,2),(5,5)]:
            f=self.make(degree,forced);rows=f.update(0,o,return_rows=True);J=features_jacobian(f,x);e,D=transported(f,x)
            fd=[];td=[]
            for j in range(16):
                a=x+eps*self.L[:,j];b=x-eps*self.L[:,j]
                fd.append((f.features(a)-f.features(b))/(2*eps));td.append((transported(f,a)[0]-transported(f,b)[0])/(2*eps))
            np.testing.assert_allclose(J@self.L,np.array(fd).T,atol=1e-7,rtol=2e-5)
            np.testing.assert_allclose(D@self.L,np.array(td).T,atol=1e-8,rtol=2e-5)
            _,_,P,_,_=Compressed(f,self.mean,self.L)(np.linalg.solve(self.L,x-self.mean))
            B=rows@J@self.L;np.testing.assert_allclose(P,np.eye(16)+B.T@B,atol=1e-7,rtol=2e-10)

    def test_chunking_atomic_support_and_storage(self):
        o=self.fixture()
        for degree,forced,packed in [(3,2,5624),(5,2,7568),(5,5,11024)]:
            f=self.make(degree,forced);g=self.make(degree,forced);f.update(0,o)
            for k in range(0,len(o),128):g.update(k,o[k:k+128])
            np.testing.assert_array_equal(f.state,g.state)
            np.testing.assert_allclose(f.root.T@f.root,g.root.T@g.root,atol=2e-5,rtol=2e-12)
            old=(g.state.copy(),g.root.copy(),g.count,g.noise);bad=o[:5].copy();bad[-1,4]=0
            with self.assertRaises(ValueError):g.update(len(o),bad)
            np.testing.assert_array_equal(g.state,old[0]);np.testing.assert_array_equal(g.root,old[1]);self.assertEqual((g.count,g.noise),old[2:])
            with self.assertRaises(ValueError):g.update(len(o)+1,o[:1])
            with self.assertRaises(ValueError):g.update(len(o),o[:1],'wrong source')
            x=self.mean.copy();x[8]+=2
            with self.assertRaises(ValueError):g.features(x)
            self.assertEqual(f.storage()['packed_factor_B'],packed)
            self.assertEqual(f.root.shape,(f.width,f.width))
        with self.assertRaises(ValueError):PartitionField(self.reg['config'],self.center,self.directory/'response_taylor2/response.so',self.hbins['derivative'],self.binary[5],5,2)

    def test_native_augmented_QR_and_convergence_gate(self):
        o=self.fixture();f=self.make();f.update(0,o)
        report={'arms':{name:dict(status='unresolved',selected=dict(x=self.mean,w=np.zeros(16),root=self.L)) for name in ['direct','Free5_Forced2_TaylorH2']}}
        add_readouts({'Free5_Forced2_TaylorH2':f},lambda name:self.make(),self.model,o,self.mean,self.L,self.center,report)
        q=report['QR_readouts']['Free5_Forced2_TaylorH2']
        self.assertEqual(q['fit_comparison']['status'],'unresolved_candidate_or_reference')
        self.assertNotIn('forecasts',q)
        self.assertLess(abs(q['controls']['factor_vs_augmented_QR_SOC_ratio_difference']),1e-7)


if __name__=='__main__':unittest.main()
