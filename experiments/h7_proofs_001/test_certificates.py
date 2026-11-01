import unittest
from fractions import Fraction as F
import numpy as np
from .certify_qr import certificate
from specifications.h7_proofs_001.check_algebra import identities,Poly
from specifications.h7_proofs_001.ownership import explore,mutations,valid,State

class Certificates(unittest.TestCase):
    def test_zero_polynomial_identities_and_nonzero_control(self):
        self.assertTrue(all(not p.c for p in identities().values()))
        x=Poly.variable('x');self.assertTrue(((x+1)**2-x*x-1).c)
    def test_abstract_reachability_and_mutation_detection(self):
        self.assertEqual(explore()['states'],969);self.assertTrue(all(mutations().values()))
    def test_exact_identity_certificate(self):
        A=np.c_[np.eye(16),np.zeros(16)];R=np.zeros((17,17));R[:16]=A
        c=certificate(A,R,np.eye(16))
        self.assertTrue(c['certifies_relative_precision_and_covariance'])
        self.assertEqual(c['epsilon']['numerator'],'0')
    def test_corrupted_factor_is_not_certified(self):
        A=np.c_[np.eye(16),np.zeros(16)];R=np.zeros((17,17));R[:16]=A;R[0,0]=2
        Q=np.eye(16);Q[0,0]=.5;c=certificate(A,R,Q)
        self.assertFalse(c['certifies_relative_precision_and_covariance'])
        self.assertEqual(F(int(c['epsilon']['numerator']),int(c['epsilon']['denominator'])),3)
    def test_noninvertible_whitener_is_not_certified(self):
        A=np.c_[np.eye(16),np.zeros(16)];R=np.zeros((17,17));R[:16]=A
        c=certificate(A,R,np.zeros((16,16)))
        self.assertFalse(c['certifies_relative_precision_and_covariance']);self.assertIsNone(c['epsilon'])
    def test_malformed_certificate_inputs_are_rejected(self):
        A=np.c_[np.eye(16),np.zeros(16)];R=np.zeros((17,17));R[:16]=A
        for rows,factor,white in ((A[:,:1],R,np.eye(16)),(A,R[:1],np.eye(16)),(A,R,np.eye(1))):
            with self.assertRaises(ValueError):certificate(rows,factor,white)
        R[0,0]=np.inf
        with self.assertRaises(ValueError):certificate(A,R,np.eye(16))
    def test_TV_bound_is_sharp_for_two_point_tilt(self):
        p=[F(2,3),F(1,3)];h=[F(1),F(4)];Z=sum(a*b for a,b in zip(p,h))
        q=[a*b/Z for a,b in zip(p,h)]
        self.assertEqual(sum(abs(a-b) for a,b in zip(p,q))/2,F(1,3))

if __name__=='__main__':unittest.main()
