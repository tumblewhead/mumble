"""Independent arithmetic witnesses, certificate controls, and replay integrity."""
import contextlib
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from .interval import Interval as IV,S,exp_minus,display_bounds
from .certificate import Certificate,Response,dual_lower,DEFAULT_SHAPE,DEFAULT_BOX
from .history import ReplayRows,ReplayIntegrityError,field_snapshot,audit
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_campaign_001.stimulus import cells
from experiments.foster_campaign_001.run import parser
from experiments.foster_campaign_001.h7_backend import H7Backend
from experiments.foster_campaign_001.backend import prepare_c
from experiments.foster_feedback_001.estimator import Model
from experiments.slow_likelihood_diagnostic_001.numerics import Exact


def decimal(x):
    x=F(x);return D(x.numerator)/D(x.denominator)


class IntervalTests(unittest.TestCase):
    def test_arithmetic_encloses_exact_endpoint_operations(self):
        values=[(F('-1.3'),F('.4')),(F('.01'),F('1.02')),(F('-2.1'),F('-.7'))]
        for a,b in values:
            for c,d in values:
                x,y=IV.bounds(a,b),IV.bounds(c,d)
                for i in (a,(a+b)/2,b):
                    for j in (c,(c+d)/2,d):
                        self.assertTrue((x+y).contains(i+j))
                        self.assertTrue((x-y).contains(i-j))
                        self.assertTrue((x*y).contains(i*j))
                        if c*d>0:self.assertTrue((x/y).contains(i/j))
        with self.assertRaises(ValueError):IV.bounds(1)/IV.bounds(-1,1)

    def test_exponentials_against_independent_high_precision_decimal(self):
        with localcontext() as ctx:
            ctx.prec=100
            for value in ['0','0.000000001','.1','.9','1','2','15','100']:
                x=F(value);result=exp_minus(IV.bounds(x))
                oracle=F((-decimal(x)).exp())
                self.assertTrue(result.contains(oracle),(value,result,oracle))
                self.assertLess(F(result.hi-result.lo,S),F('1e-19'))
            interval=exp_minus(IV.bounds('.2','.4'))
            for value in ('.2','.3','.4'):self.assertTrue(interval.contains(F((-D(value)).exp())))
        with self.assertRaises(ValueError):exp_minus(IV.bounds('-1'))

    def test_cache_is_exact_key_and_immutable(self):
        exp_minus.cache_clear();a=exp_minus(IV.bounds('.25'));b=exp_minus(IV.bounds('.25'))
        self.assertEqual(a,b);self.assertEqual(exp_minus.cache_info().hits,1)
        c=exp_minus(IV.bounds('.2501'));self.assertNotEqual(a,c)
        with self.assertRaises(Exception):a.lo=0

    def test_display_rounds_outward(self):
        for lo,hi in [(F(1,3),F(2,3)),(F(-1,7),F(-1,11))]:
            result=display_bounds(lo,hi)
            self.assertLessEqual(F(result['outer_float'][0]),lo)
            self.assertGreaterEqual(F(result['outer_float'][1]),hi)
            self.assertEqual([F(*x) for x in result['exact']],[lo,hi])

    def test_response_contains_independent_physical_decimal_recurrence(self):
        # Includes uncertain rates, nonzero initial RC/h and current reversals.
        with localcontext() as ctx:
            ctx.prec=100
            amplitude=list(map(F,['.7','.001','-.002','.003','16','.1','.04','.08','.12','.014','.002']))
            for offset in ('0','.009','-.009'):
                actual=[F(x)*(1+F(offset)) for x in DEFAULT_SHAPE]
                response=Response(relative_radius='.01')
                z=decimal(amplitude[0]);v=list(map(decimal,amplitude[1:4]));h=decimal(amplitude[10]/amplitude[9])
                for k in range(120):
                    I=F('.12') if k<40 else F('-.06') if k<90 else F(0)
                    dt=F(float(1/35));beta=response.advance(dt,I)
                    z-=decimal(I*dt*amplitude[4]/3600)
                    for j in range(3):
                        e=(-decimal(dt/actual[j])).exp()
                        v[j]=e*v[j]+decimal(amplitude[6+j]*I)*(1-e)
                    if I:
                        e=(-decimal(actual[3 if I>0 else 4]*abs(I)*dt/3600)).exp()
                        h=e*h+(1 if I>0 else -1)*(1-e)
                    voltage=D(3)+D('1.15')*z+decimal(amplitude[9])*h-decimal(amplitude[5]*I)-sum(v)
                    enclosed=IV.bounds(3)+sum((x*a for x,a in zip(beta,amplitude)),IV.bounds(0))
                    self.assertTrue(enclosed.contains(F(voltage)),(offset,k))
                self.assertEqual(response.A,40*F('.12')*dt/3600-50*F('.06')*dt/3600)


class CertificateTests(unittest.TestCase):
    def test_dual_verifier_sound_for_wrong_and_negative_solver_proposals(self):
        box=[(F(0),F(1))]*11;A=[[F(1)]+[F(0)]*10];b=[F('.7')];c=[F(-1)]+[F(0)]*10
        self.assertEqual(dual_lower(c,A,b,box,[1.]),F('-.7'))
        self.assertEqual(dual_lower(c,A,b,box,[-100.]),F(-1))
        for value in (0.,.5,1.,10.,1e9):
            self.assertLessEqual(dual_lower(c,A,b,box,[value]),F('-.7'))

    def test_initial_public_bounds_are_not_automatically_useful(self):
        c=Certificate('fixture');r=c.query(.6,.06)
        self.assertEqual(r['execution'],'verified_outer_enclosure')
        self.assertFalse(r['SOC']['midpoint_authorized']);self.assertFalse(r['Q']['midpoint_authorized'])
        self.assertEqual([F(*v) for v in r['enclosures']['Q']['exact']],[F('.045'),F('.075')])

    def test_rest_does_not_invent_capacity_information(self):
        c=Certificate('fixture',stride=35)
        rows=np.tile([1/35,0.,25.,3.83,.001],(350,1));c.advance(0,rows);r=c.query()
        self.assertEqual(r['execution'],'verified_outer_enclosure')
        self.assertEqual([F(*v) for v in r['enclosures']['Q']['exact']],[F('.045'),F('.075')])
        self.assertEqual(c.response.count,350);self.assertEqual(c.rows,10)

    def test_certificate_checks_H7_point_separately_from_midpoint(self):
        box=[v.copy() for v in DEFAULT_BOX];box[0]=['.60','.602'];box[4]=[str(1/F('.0601')),str(1/F('.06'))]
        c=Certificate('fixture',box=box);r=c.query(.8,.07)
        self.assertTrue(r['SOC']['midpoint_authorized']);self.assertTrue(r['Q']['midpoint_authorized'])
        self.assertFalse(r['SOC']['H7_point_authorized']);self.assertFalse(r['Q']['H7_point_authorized'])

    def test_invalid_or_gap_input_cannot_advance_response(self):
        c=Certificate('fixture');rows=np.tile([1/35,.12,25.,3.8,.001],(16,1))
        for first,bad in [(1,rows),(0,rows.copy()),(0,rows.copy())]:
            if first==0:
                bad[-1,2]=26 if c.response.count==0 else 25
            with self.assertRaises(ValueError):c.advance(first,bad)
            self.assertEqual(c.response.count,0)
        c.advance(0,rows)
        with self.assertRaises(ValueError):c.advance(0,rows)

    def test_failed_or_unverified_feasibility_never_authorizes(self):
        c=Certificate('fixture')
        for outcome in [SimpleNamespace(success=False),SimpleNamespace(success=True,x=np.r_[np.zeros(11),1.])]:
            with patch('experiments.h7_history_quality_001.certificate.linprog',return_value=outcome):
                r=c.query()
            self.assertEqual(r['authorization'],'unresolved')

    def test_rate_support_and_source_change_identity(self):
        ids={Certificate('a').configuration_id,Certificate('b').configuration_id,
             Certificate('a',rate_radius='.01').configuration_id,Certificate('a',stride=35).configuration_id}
        self.assertEqual(len(ids),4)
        with self.assertRaises(ValueError):Response(relative_radius='1')


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mumble-history-quality-');cls.path=Path(cls.temp.name)
        cls.config=json.loads(Path('experiments/foster_feedback_001/calibration.json').read_text());cls.config['hysteresis_chart']='bounded'
        settings=vars(parser().parse_args([]));settings.update(sample_rate_hz=35,temperature='fixed',temperature_mean_c=25.,field_refresh_seconds=60.)
        cls.settings=settings;cls.scenario=dict(cell='B',load='embedded',load_seed=7,seed=1103,noise_v=.002)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def factory(self):return StimulusStream(self.config,cells()['B'],self.scenario,self.settings)

    def bank(self):return H7Backend(self.path,self.config,'fixture','model',35,SimpleNamespace(**self.settings))

    def test_replay_and_direct_derivatives_match_materialized_stream(self):
        obs,_,_=self.factory().read(256);digest=hashlib.sha256(obs.astype('<f8').tobytes()).hexdigest()
        replay=ReplayRows(self.factory,256,digest);bank=self.bank()
        model=Model(prepare_c(self.path,35,self.config)[0],self.config)
        a=Exact(model,obs,bank.mean,bank.prior_root,chunk=64)(np.zeros(16))
        b=Exact(model,replay,bank.mean,bank.prior_root,chunk=64)(np.zeros(16))
        for left,right in zip(a,b):np.testing.assert_array_equal(left,right)
        self.assertEqual(replay.verified_passes,1)

    def test_replay_integrity_error_is_not_a_domain_rejection(self):
        obs,_,_=self.factory().read(16);bank=self.bank();bank.advance(0,obs)
        model=Model(prepare_c(self.path,35,self.config)[0],self.config)
        with self.assertRaises(ReplayIntegrityError):audit(bank,model,self.factory,'bad-hash')
        replay=ReplayRows(self.factory,16,'bad-hash')
        with self.assertRaises(ReplayIntegrityError):replay[2:4]

    def test_failed_later_probe_integrity_is_not_swallowed(self):
        obs,_,_=self.factory().read(16);bank=self.bank();bank.advance(0,obs)
        model=Model(prepare_c(self.path,35,self.config)[0],self.config)
        original=Exact.__call__;calls=[0]
        def corrupt(self,w):
            calls[0]+=1
            if calls[0]>1:raise ReplayIntegrityError('later probe source changed')
            return original(self,w)
        with patch.object(Exact,'__call__',corrupt):
            with self.assertRaisesRegex(ReplayIntegrityError,'later probe'):
                audit(bank,model,self.factory,hashlib.sha256(obs.tobytes()).hexdigest())

    def test_audit_snapshot_does_not_mutate_active_estimator(self):
        obs,_,_=self.factory().read(16);bank=self.bank();bank.advance(0,obs)
        before=bank.checkpoint_arrays();context=bytes(bank.context);field=field_snapshot(bank)
        self.assertEqual(field.count,16);self.assertEqual(bank.field.count,0)
        self.assertEqual(bytes(bank.context),context)
        for name,value in before.items():np.testing.assert_array_equal(bank.checkpoint_arrays()[name],value)

    def test_summary_remains_unresolved_after_source_verification_failure(self):
        from . import history
        out=self.path/'source_failure'
        argv=['history','--out',str(out),'--prefix-seconds','1','--loads','rest','--noise-v','.002']
        with patch('sys.argv',argv),patch.object(history,'verify_sources',side_effect=ValueError('changed source')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(history.main(),1)
        r=json.loads((out/'summary.json').read_text())
        self.assertEqual(r['status'],'unresolved');self.assertIn('changed source',r['finalization_error'])


if __name__=='__main__':unittest.main()
