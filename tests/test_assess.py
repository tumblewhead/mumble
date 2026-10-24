"""Tests of reporting semantics, including a structural ambiguity canary."""
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from assess import assess_result


def fixture(modes=1):
    theta = ([math.log(.05), math.log(.5), math.log(5)][:modes]
             + [math.log(220), math.log(370), .6, math.log(.06)])
    alpha = [.12] + [.2] * modes + [.025] + [.004] * modes + [.005]
    nt, na = modes+4, 2*modes+3
    scales = [1.] * nt + [.2] * (modes+1) + [.03] * (modes+2)
    scales[modes+2] = .1
    return {"modes": modes, "theta": theta, "alpha": alpha,
            "coordinate_scales": scales, "joint_normal": np.eye(nt+na).tolist(),
            "charge_Ah": .003, "status": 0, "termination_reason": 0,
            "active_linear_constraints": 0, "active_outer_bounds": 0,
            "unexcited_theta_mask": 0}


class AssessmentTests(unittest.TestCase):
    def test_rest_nullspace_survives_arbitrary_repetition(self):
        r = fixture();n=1;nt=n+4;dim=len(r["coordinate_scales"])
        # Steady rest: V=U(z0)-u0. The SOC/hysteresis alternatives persist.
        row = np.zeros(dim)
        row[n+2] = 1.5 * r["coordinate_scales"][n+2]
        row[nt+2+2*n] = -r["coordinate_scales"][nt+2+2*n]
        r["charge_Ah"] = 0
        r["unexcited_theta_mask"] = (1 << n) | (1 << (n+1)) | (1 << (n+3))
        for count in (1, 1000, 10**12):
            r["joint_normal"] = (count/1e-6 * np.outer(row,row)).tolist()
            out=assess_result(r)
            self.assertEqual(out["numerical_rank"],1)
            for name in ("z0","current_soc","h0"):
                self.assertEqual(out["parameters"][name]["status"],"unresolved")
                self.assertEqual(out["parameters"][name]["range_kind"],"prior_support")
                self.assertFalse(out["parameters"][name]["passes_local_precision"])
            self.assertEqual(out["parameters"]["Q_Ah"]["status"],"unexcited")
            self.assertEqual(out["parameters"]["Q_Ah"]["local_range"],[.03,.1])
            json.dumps(out,allow_nan=False)

    def test_resolved_local_direction_stays_provisional(self):
        r=fixture(3);dim=len(r["coordinate_scales"])
        r["joint_normal"]=(np.eye(dim)*1e6).tolist()
        out=assess_result(r)
        for name in ("tau1","gamma_minus","Q_Ah","R0","H","current_soc"):
            self.assertEqual(out["parameters"][name]["status"],"provisional")
            self.assertTrue(out["parameters"][name]["passes_local_precision"])
            self.assertTrue(out["parameters"][name]["eligible_for_profile_check"])
        q=out["parameters"]["Q_Ah"]
        self.assertAlmostEqual(q["local_range"][0],.06*math.exp(-.002))
        self.assertFalse(out["coverage_certificate"])
        json.dumps(out,allow_nan=False)

    def test_wide_finite_ranges_are_unresolved(self):
        r=fixture();out=assess_result(r)
        for name in ("R0","H","z0","current_soc","Q_Ah"):
            p=out["parameters"][name]
            self.assertEqual(p["status"],"unresolved")
            self.assertFalse(p["passes_local_precision"])
            self.assertFalse(p["eligible_for_profile_check"])
        json.dumps(out,allow_nan=False)

    def test_current_soc_keeps_cross_covariance(self):
        r=fixture();n=1;dim=len(r["coordinate_scales"])
        cov=np.eye(dim)*1e-4
        zidx,qidx=n+2,n+3
        cov[zidx,zidx]=.04;cov[qidx,qidx]=.01;cov[zidx,qidx]=cov[qidx,zidx]=-.015
        r["joint_normal"]=np.linalg.inv(cov).tolist()
        g=np.zeros(dim);g[zidx]=.1;g[qidx]=.003/.06
        expected=2*math.sqrt(g@cov@g)
        out=assess_result(r)
        self.assertAlmostEqual(out["parameters"]["current_soc"]["local_halfwidth"],expected,places=12)
        diagonal_only=2*math.sqrt(g@np.diag(np.diag(cov))@g)
        self.assertGreater(abs(expected-diagonal_only),.001)

    def test_null_direction_not_replaced_with_pseudoinverse_zero(self):
        r=fixture();m=np.eye(len(r["coordinate_scales"]))*1e6;m[0,0]=0
        r["joint_normal"]=m.tolist();out=assess_result(r)
        p=out["parameters"]["tau1"]
        self.assertEqual(p["status"],"unresolved")
        self.assertEqual(p["local_range"],[.015,30.])
        self.assertIsNone(p["local_standard_deviation"])

    def test_hysteresis_zero_amplitude_is_unresolved(self):
        r=fixture();r["alpha"][2]=0;r["alpha"][-1]=0
        r["joint_normal"]=(np.eye(len(r["coordinate_scales"]))*1e12).tolist()
        out=assess_result(r);p=out["parameters"]["h0"]
        self.assertEqual(p["status"],"unresolved")
        self.assertEqual(p["local_range"],[-1.,1.])
        self.assertIsNone(p["point"])

    def test_hysteresis_ratio_keeps_joint_covariance(self):
        r=fixture();n=1;nt=n+4;dim=len(r["coordinate_scales"])
        hidx,uidx=nt+1+n,nt+2+2*n
        cov=np.eye(dim)*1e-6
        cov[uidx,uidx]=4e-6;cov[hidx,uidx]=cov[uidx,hidx]=2e-7
        r["joint_normal"]=np.linalg.inv(cov).tolist()
        H,u0=r["alpha"][1+n],r["alpha"][2+2*n]
        g=np.zeros(dim);g[hidx]=-u0/H**2*.03;g[uidx]=.03/H
        expected=math.sqrt(g@cov@g)
        out=assess_result(r)
        self.assertAlmostEqual(out["parameters"]["h0"]["point"],u0/H)
        self.assertAlmostEqual(out["parameters"]["h0"]["local_standard_deviation"],expected,places=13)

    def test_hysteresis_near_zero_roundoff_never_reports_ratio(self):
        r=fixture();r["alpha"][2]=-1e-17;r["alpha"][-1]=6e-17
        out=assess_result(r);p=out["parameters"]["h0"]
        self.assertEqual(p["status"],"unresolved")
        self.assertEqual(p["local_range"],[-1.,1.])
        self.assertIsNone(p["point"])

    def test_optimizer_stall_does_not_qualify_a_narrow_local_direction(self):
        r=fixture();r["joint_normal"]=(np.eye(len(r["coordinate_scales"]))*1e12).tolist();r["status"]=2
        out=assess_result(r);p=out["parameters"]["Q_Ah"]
        self.assertEqual(p["status"],"unresolved")
        self.assertEqual(p["range_kind"],"prior_support")
        self.assertAlmostEqual(p["point"],.06)

    def test_active_bounds_preserve_raw_width(self):
        r=fixture();r["joint_normal"]=(np.eye(len(r["coordinate_scales"]))*1e4).tolist()
        r["theta"][-1]=math.log(.03);r["active_outer_bounds"]=1
        out=assess_result(r);p=out["parameters"]["Q_Ah"]
        self.assertEqual(p["status"],"provisional")
        self.assertLess(p["local_range"][0],.03)
        self.assertTrue(p["active_constraints_present"])

    def test_materially_indefinite_matrix_rejected_for_diagnostics(self):
        r=fixture();m=np.eye(len(r["coordinate_scales"]));m[0,0]=-1;r["joint_normal"]=m.tolist()
        out=assess_result(r)
        self.assertTrue(out["matrix_invalid"])
        self.assertEqual(out["parameters"]["Q_Ah"]["status"],"unresolved")

    def test_fixed_current_soc_chart_is_not_unrestricted_information(self):
        r=fixture();r["joint_normal"]=(np.eye(len(r["coordinate_scales"]))*1e12).tolist()
        r["fixed_current_soc"]=.55
        out=assess_result(r)
        self.assertEqual(out["joint_matrix_chart"],"fixed_current_soc_constrained")
        for p in out["parameters"].values():
            self.assertEqual(p["status"],"unresolved")
            self.assertEqual(p["range_kind"],"prior_support")
            self.assertFalse(p["eligible_for_profile_check"])


if __name__=="__main__":
    unittest.main()
