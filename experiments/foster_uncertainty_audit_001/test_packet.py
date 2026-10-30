import json,math,tempfile,unittest
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import prepare_c
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_feedback_001.estimator import Model
from .conditional_packet import partition,chart_from,make,compose
ROOT=Path(__file__).resolve().parents[2]

class ConditionalPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.cfg=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());cls.cfg['hysteresis_chart']='bounded'
        binary,_=prepare_c(Path(cls.temp.name),50,cls.cfg);cls.model=Model(binary,cls.cfg)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def observations(self):
        t=np.arange(97);return np.column_stack([np.where(t%7==0,0.,.02),np.select([t%3==0,t%3==1],[-.12,.04],default=0.),25+7*np.sin(t/10),3.7+.01*np.cos(t),np.full(len(t),.02)])
    def test_requery_preserves_full_physical_likelihood_and_transport(self):
        x,_=prior(self.cfg);amp,shape=partition(x);obs=self.observations()
        for ratio in [.8,1.,1.2]:
            s=shape*ratio;packet=make(obs,s,self.cfg)
            for shift in [-.1,0.,.1]:
                a=amp.copy();a[4:10]*=1+shift;a[10]=a[9]*shift;a[0]+=.1*shift
                chart=chart_from(a,s);v,_,end,_=self.model.evaluate(chart,obs)
                exact=.5*np.sum(((v-obs[:,3])/obs[:,4])**2)+np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi)
                self.assertAlmostEqual(packet.nll(a),exact,places=8)
                expected,_=partition(end);np.testing.assert_allclose(packet.outgoing(a),expected,atol=2e-14,rtol=2e-13)
    def test_chronological_composition_and_cross_terms(self):
        x,_=prior(self.cfg);a,s=partition(x);obs=self.observations();whole=make(obs,s,self.cfg)
        packets=[make(obs[b:e],s,self.cfg,begin=b) for b,e in [(0,11),(11,41),(41,97)]]
        left=compose(compose(packets[0],packets[1]),packets[2]);right=compose(packets[0],compose(packets[1],packets[2]))
        for trial in [a,a+np.array([.01,.001,-.001,.002,.2,.001,-.001,.001,.001,.0001,.001])]:
            self.assertAlmostEqual(whole.nll(trial),left.nll(trial),places=8);self.assertAlmostEqual(whole.nll(trial),right.nll(trial),places=8)
            np.testing.assert_allclose(whole.outgoing(trial),left.outgoing(trial),atol=2e-14)
        G=whole.root[:,:11].T@whole.root[:,:11];self.assertGreater(abs(G[0,4]),0);self.assertGreater(abs(G[4,9]),0)
    def test_domain_and_source_guards(self):
        x,_=prior(self.cfg);a,s=partition(x);obs=self.observations();left=make(obs[:10],s,self.cfg);wrong=make(obs[10:],s,self.cfg,begin=9)
        with self.assertRaises(ValueError):compose(left,wrong)
        wrong=make(obs[10:],s*1.1,self.cfg,begin=10)
        with self.assertRaises(ValueError):compose(left,wrong)
        bad=a.copy();bad[10]=2*bad[9]
        with self.assertRaises(ValueError):left.nll(bad)
        bad=a.copy();bad[0]=-1
        with self.assertRaises(ValueError):left.nll(bad)
        with self.assertRaises(ValueError):make(obs,np.array([1.,.5,5.,1.,1.]),self.cfg)

        bad=a.copy();bad[4]=float('nan')
        with self.assertRaises(ValueError):left.nll(bad)
        import copy
        config=copy.deepcopy(self.cfg);config['arrhenius_A_K'][3]=-100000
        with self.assertRaises(ValueError):make(obs,s,config)
