import numpy as np
from . import test_completion
from .rc_control import RC5Control
from .basis import CompletedField
from experiments.hysteresis_refinement_001.field import MixedField,features_jacobian,transported
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from


class RCControl(test_completion.Completion):
    # Reuse the candidate tests with RC5 and appropriate storage assertions.
    def field(self,kind):return RC5Control(self.config,self.center,self.binary,kind)
    def test_domain_atomicity_and_storage(self):
        for kind,width,factor in [('td2',52,11024),('c22',54,11880),('tensor',58,13688)]:
            f=self.field(kind);self.assertEqual(f.width,width)
            self.assertEqual(f.storage()['packed_factor_B'],factor)
            self.assertEqual(f.storage()['numeric_factor_response_domain_scalars_B'],factor+456+96)
            f.update(0,self.rows());snapshot=f.root.copy()
            with self.assertRaises(ValueError):f.update(0,self.rows())
            np.testing.assert_array_equal(f.root,snapshot)
    def test_RC_rows_match_H7_and_H_rows_unchanged(self):
        obs=self.rows();h7=MixedField(self.config,self.center,1.,7,self.binary)
        r7=h7.rows(0,obs)
        for kind in ['c22','tensor']:
            f=self.field(kind);low=CompletedField(self.config,self.center,self.binary,kind)
            rows=f.rows(0,obs);lr=low.rows(0,obs)
            np.testing.assert_array_equal(rows[:,:39],r7[:,:39])
            np.testing.assert_array_equal(rows[:,39:-1],lr[:,21:-1])
            np.testing.assert_array_equal(f.state[36:],low.state[18:])
