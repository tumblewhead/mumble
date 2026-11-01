"""Fused transaction parity, buffer lifetime and failure ownership controls."""
import ctypes as C
import unittest
import numpy as np
from experiments.field_feedback_preservation_001 import test_numerics as fixtures
from .native import Native, build, ptr


class FusedTests(fixtures.Tests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.binary=build(cls.path/'fused')

    def pair(self):
        f=self.field()
        a=Native(self.binary,f,self.mean,self.L)
        b=Native(self.binary,f,self.mean,self.L)
        a.initialize(np.zeros(16));b.initialize(np.zeros(16))
        return f,a,b

    def test_fused_matches_batch_response_and_original_qr_bitwise(self):
        f,a,b=self.pair();state=f.state.copy();expected=f.state.copy()
        observations=self.obs(257);observations[32:50,1]=0
        first=0
        for n in [1,7,16]*11:
            n=min(n,len(observations)-first)
            if not n:break
            rows=observations[first:first+n];lifted=np.empty((n,82))
            self.assertEqual(f.fn(ptr(rows),n,ptr(f.cal),f.n,f.b,ptr(f.rates),ptr(f.p1),ptr(f.p2),ptr(expected),ptr(lifted)),0)
            a.update(first,lifted)
            self.assertEqual(b.step(first,rows,state,1050),21*n)
            np.testing.assert_array_equal(expected,state)
            np.testing.assert_array_equal(a.snapshot(),b.snapshot())
            try:reference=a.query(state=expected,count=first+n)
            except ValueError:
                with self.assertRaises(ValueError):b.query(state=state,count=first+n,reuse=True)
            else:
                actual=b.query(state=state,count=first+n,reuse=True)
                for k in reference:np.testing.assert_array_equal(reference[k],actual[k])
            first+=n
        self.assertEqual(first,257)
        self.assertEqual(b.storage()['native_fused_workspace_B'],3360)

    def test_rejected_window_does_not_commit_context_or_state(self):
        f,_,b=self.pair();state=f.state.copy();before=b.snapshot();old=state.copy()
        for column,value in [(0,-.1),(0,1.01),(1,.251),(2,14.),(2,36.),(3,np.nan),(4,0.),(4,np.inf)]:
            rows=self.obs(16);rows[-1,column]=value
            with self.assertRaises(ValueError):b.step(0,rows,state,1050)
            np.testing.assert_array_equal(b.snapshot(),before);np.testing.assert_array_equal(state,old)
        for first,rows,hz in [(1,self.obs(16),1050),(0,self.obs(16),17),(0,self.obs(17),1050)]:
            with self.assertRaises(ValueError):b.step(first,rows,state,hz)
            np.testing.assert_array_equal(b.snapshot(),before);np.testing.assert_array_equal(state,old)
        b.source+=1
        with self.assertRaises(ValueError):b.step(0,self.obs(16),state,1050)
        np.testing.assert_array_equal(b.snapshot(),before);np.testing.assert_array_equal(state,old)

    def test_actual_intervals_and_zero_time(self):
        for rate,hz in [(35,1050),(50,1050),(100,2100)]:
            f,a,b=self.pair();state=f.state.copy();expected=f.state.copy();rows=self.obs(16)
            rows[:,0]=1/rate;rows[0,0]=0;rows[1,0]=2/rate
            lifted=np.empty((16,82));f.fn(ptr(rows),16,ptr(f.cal),f.n,f.b,ptr(f.rates),ptr(f.p1),ptr(f.p2),ptr(expected),ptr(lifted));a.update(0,lifted)
            self.assertEqual(b.step(0,rows,state,hz),round(16*hz/rate))
            np.testing.assert_array_equal(expected,state);np.testing.assert_array_equal(a.snapshot(),b.snapshot())

    def test_reused_output_is_opt_in_and_restoration_invalidates_it(self):
        f,a,b=self.pair();state=f.state.copy();rows=self.obs(16)
        b.step(0,rows,state,1050)
        owned=b.query(state=state,count=16);saved={k:np.array(v,copy=True) for k,v in owned.items()}
        b.step(16,rows,state,1050)
        for k in saved:np.testing.assert_array_equal(owned[k],saved[k])
        # Same-object mutation must not bypass validation in the public query.
        state[-1]=100
        with self.assertRaises(ValueError):b.query(state=state,count=32)
        b.restore(a.snapshot(),0)
        self.assertIsNone(b._step_cache)
        b.initialize(np.zeros(16));self.assertIsNone(b._step_cache)

    def test_query_domain_failure_keeps_new_evidence_for_recovery(self):
        f,a,b=self.pair();state=f.state.copy();state[-1]=100
        # This historical SOC envelope makes readout invalid, but rows still
        # belong to history. It must not roll back a valid observation update.
        rows=self.obs(16);before=b.snapshot()
        b.step(0,rows,state,1050)
        self.assertEqual(b.count,16);self.assertFalse(np.array_equal(before,b.snapshot()))
        with self.assertRaises(ValueError):b.query(state=state,count=16,reuse=True)

    def test_scheduled_query_is_deferred_to_refresh(self):
        f,_,b=self.pair();state=f.state.copy();rows=self.obs(16)
        b.step(0,rows,state,1050,query=False)
        self.assertIsNone(b._step_cache)
        a=b.query(state=state,count=16,reuse=True);c=b.query(state=state,count=16)
        for k in a:np.testing.assert_array_equal(a[k],c[k])


if __name__=='__main__':unittest.main()
