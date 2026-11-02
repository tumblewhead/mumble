import copy
import ctypes as C
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from .build import build
from .contracts import load,validate
from experiments.foster_campaign_001.backend import ROOT
from experiments.foster_campaign_001.coordinates import prior
from experiments.hysteresis_refinement_001.field import MixedField
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.field_tangent_native_001.native import ptr, Native


def observations(n):
    i=np.arange(n);dt=np.array([0.,1/35,1/50,1/100,1.])[i%5]
    current=np.array([0.,-0.,.25,-.25,1e-14,-1e-14,.045,-.12])[i%8]
    return np.c_[dt,current,25+10*np.sin(i/29),3.7+.01*np.cos(i),np.full(n,.002)]


class Reuse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.path=Path(cls.tmp.name)
        cls.config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());cls.config['hysteresis_chart']='bounded'
        cls.mean,cls.L=prior(cls.config);cls.center=partition(cls.mean)[1]
        cls.libraries=[build(cls.path/name,candidate=candidate,native=True) for name,candidate in [('base',False),('candidate',True)]]
        cls.counter_libraries=[build(cls.path/name,candidate=candidate,counters=True)[0] for name,candidate in [('base_count',False),('candidate_count',True)]]

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def fields(self,libraries=None):
        return [MixedField(self.config,self.center,1.,7,lib[0],'reuse-test') for lib in (libraries or self.libraries)]

    def test_rows_and_states_bitwise_over_irregular_stream(self):
        a,b=self.fields();rows=observations(4097)
        for first in range(0,len(rows),31):
            for x,y in zip((a.rows(first,rows[first:first+31]),a.state),(b.rows(first,rows[first:first+31]),b.state)):
                self.assertEqual(x.tobytes(),y.tobytes())

    def test_full_field_QR_and_features_bitwise(self):
        a,b=self.fields();rows=observations(257)
        # Small balanced currents keep queried SOC paths in support.
        rows[:,1]*=.01
        for first in range(0,len(rows),16):
            a.update(first,rows[first:first+16]);b.update(first,rows[first:first+16])
            self.assertEqual(a.root.tobytes(),b.root.tobytes());self.assertEqual(a.state.tobytes(),b.state.tobytes())
            self.assertEqual(a.features(self.mean).tobytes(),b.features(self.mean).tobytes())

    def test_fused_context_and_readout_bitwise(self):
        fields=self.fields();natives=[Native(lib[1],f,self.mean,self.L) for lib,f in zip(self.libraries,fields)]
        for n in natives:n.initialize(np.zeros(16));n.prepare_step()
        rows=observations(512);rows[:,0]=1/35;rows[:,1]*=.01;rows[:,3]=3.69
        states=[f.state.copy() for f in fields]
        for first in range(0,len(rows),16):
            for n,state in zip(natives,states):n.step(first,rows[first:first+16],state,35,query=False)
            self.assertEqual(natives[0].snapshot().tobytes(),natives[1].snapshot().tobytes())
            self.assertEqual(states[0].tobytes(),states[1].tobytes())
            outcomes=[]
            for n,state in zip(natives,states):
                try:
                    result=n.query(state,first+16);outcomes.append(('ok',b''.join(np.asarray(result[k]).tobytes() for k in result)))
                except ValueError as error:outcomes.append(('error',str(error)))
            self.assertEqual(outcomes[0],outcomes[1])

    def raw(self,f,rows,state,out):
        rows=np.ascontiguousarray(rows)
        return f.fn(ptr(rows),len(rows),ptr(f.cal),6,8,36,ptr(f.rates),ptr(f.p1),ptr(f.p2),ptr(state),ptr(out))

    def test_invalid_prefix_and_unwritten_suffix_parity(self):
        for bad in ('nan','sigma','T','dt'):
            a,b=self.fields();rows=observations(17)
            col,value={'nan':(3,float('nan')),'sigma':(4,0.),'T':(2,36.),'dt':(0,-.01)}[bad]
            rows[7,col]=value;states=[f.state.copy() for f in (a,b)]
            outputs=[np.full((17,112),-123.) for _ in range(2)]
            statuses=[self.raw(f,rows,s,o) for f,s,o in zip((a,b),states,outputs)]
            self.assertEqual(statuses,[-1,-1]);self.assertEqual(states[0].tobytes(),states[1].tobytes())
            self.assertEqual(outputs[0].tobytes(),outputs[1].tobytes());self.assertTrue(np.all(outputs[0][7:]==-123.))

    def test_empty_call_preserves_outputs(self):
        for f in self.fields():
            state=f.state.copy();out=np.full((1,112),-123.);before=state.tobytes()
            self.assertEqual(self.raw(f,np.empty((0,5)),state,out),0)
            self.assertEqual(state.tobytes(),before);self.assertTrue(np.all(out==-123.))

    def test_call_count_and_counter_build_parity(self):
        for current in (0.,-0.,.04,-.04):
            outputs=[]
            for candidate,binary in enumerate(self.counter_libraries):
                f=MixedField(self.config,self.center,1.,7,binary,'counts');lib=C.CDLL(str(binary))
                lib.ar_exp_count.restype=lib.ar_expm1_count.restype=C.c_uint64
                rows=observations(1);rows[0]=[1/35,current,25.,3.7,.002]
                lib.ar_reset();outputs.append(f.rows(0,rows))
                expected=(29,18) if current==0 else (37,26) if candidate else (93,82)
                self.assertEqual((lib.ar_exp_count(),lib.ar_expm1_count()),expected)
            self.assertEqual(outputs[0].tobytes(),outputs[1].tobytes())

    def test_field_invalid_update_keeps_owned_state(self):
        for f in self.fields():
            before=(f.root.tobytes(),f.state.tobytes(),f.count);rows=observations(16);rows[-1,4]=0
            with self.assertRaises(ValueError):f.update(0,rows)
            self.assertEqual(before,(f.root.tobytes(),f.state.tobytes(),f.count))


class Contract(unittest.TestCase):
    def test_dependency_map_and_key_coverage(self):
        g=load();deps=validate(g);self.assertIn('old_evidence',deps['query'])
        sizes=[len(e['shape_dependencies']) for e in g['coefficient_entries']]
        self.assertEqual([sizes.count(i) for i in range(4)],[10,33,23,12])

    def test_mixed_dependency_mutation_rejected(self):
        g=load();entry=next(e for e in g['coefficient_entries'] if e['i']==1 and e['j']==9)
        entry['shape_dependencies'].remove('kminus')
        with self.assertRaisesRegex(ValueError,'joint coefficient'):validate(g)

    def test_stale_temperature_key_rejected(self):
        g=load();g['nodes'][1]['cache_key'].remove('T')
        with self.assertRaisesRegex(ValueError,'cache dependency'):validate(g)

    def test_reordered_dependency_rejected(self):
        g=load();g['nodes'][0],g['nodes'][1]=g['nodes'][1],g['nodes'][0]
        with self.assertRaisesRegex(ValueError,'topological'):validate(g)


if __name__=='__main__':unittest.main()
