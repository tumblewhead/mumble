#!/usr/bin/env python3
"""Small fabricated scoring fixtures; no generator, RNG or learner is called."""
from __future__ import annotations

import importlib.util
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('continuous_scoring', ROOT/'tools/score_continuous_learning.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def tiny_plan():
    return {'measurements': {'targets': {'SOC_error_pp': {'hard': 10., 'preferred': .5},
             'capacity_error_percent': {'hard': 5., 'preferred': .5}}},
            'B_continuous_4h': {
                'analysis_windows': {'prompt_SOC': [0, 2/35], 'initial_acquisition': [0, 5/35],
                    'first_retention': [2/35, 4/35], 'renewed_excitation': [4/35, 5/35],
                    'final_retention': [4/35, 5/35]},
                'phases': [{'id': 'initial_learning', 'start_index': 0, 'end_index': 2},
                           {'id': 'retention_weak', 'start_index': 2, 'end_index': 4},
                           {'id': 'final_weak_retention', 'start_index': 4, 'end_index': 5}],
                'checkpoint_times_s': [0, 2/35, 4/35, 5/35]}}


def vector(z=.5, q=.06):
    return [math.log(.05), math.log(.5), math.log(5), math.log(220), math.log(370),
            math.log(q), .12, .18, .22, .28, .025, z, .003, -.002, .004, -.45]


def entity(z, q, available, *, provisional=True):
    mean=vector(z,q)
    return {'mean': mean, 'coordinate_sd': [.001]*16,
            # Deliberately incorrect placeholders when unavailable: the scorer
            # must use mean[] rather than these finite convenience zeros.
            'current_soc': z if available else 0.0, 'capacity_Ah': q if available else 0.0,
            'point_available': int(available), 'capacity_available': int(available),
            'prediction_available': int(available), 'local_ranges_available': int(available),
            'soc_local_lower': z-.001 if available else 0,
            'soc_local_upper': z+.001 if available else 0,
            'capacity_local_lower_Ah': q-.00001 if available else 0,
            'capacity_local_upper_Ah': q+.00001 if available else 0,
            'soc_status': 'provisional' if provisional else 'unexcited',
            'capacity_status': 'provisional' if provisional else 'unexcited',
            'flags': 0, 'excitation': int(available), 'evidence_next_index': 1 if available else 0,
            'evidence_age_samples': 0, 'limited_gain_count': 0, 'zero_gain_count': 0}


def fixture(path, *, metric_count=5, query_count=None, invalid_at=None):
    if query_count is None:
        query_count=metric_count
    metrics=[]
    zerr=[1., .25, .1, .2, .1]
    qerr=[8., 4., 2., .3, .2]
    truth=[]
    observations=[]
    fulltruth=[]
    queries=[]
    initial=entity(.68,.06,False,provisional=False)
    initial['elapsed_s']=0.;initial['epoch_begin']=0
    elapsed=0.0
    for n in range(6):
        fulltruth.append({'next_index': n, 'nominal_time_s':n/35,
                          'mean':vector(), 'SOC':.5, 'Q_Ah':.06,
                          'clean_voltage_V':None if n==0 else 3.7,
                          'current_A':None if n==0 else .003, 'prediction_observed':n>0})
        if n==0:
            es=[initial,entity(.67,.05,False,provisional=False),entity(.69,.07,False,provisional=False)]
        else:
            elapsed += S.DT
            z=.5+zerr[n-1]/100;q=.06*(1+qerr[n-1]/100)
            available=n!=3
            es=[entity(z,q,available),entity(.62 if n==1 else z,q,available),entity(z,q,available)]
            for e in es:
                e.update(elapsed_s=elapsed,epoch_begin=0)
            mask=15 if available else 12
            flags=16 if n==invalid_at else 0
            if n<=metric_count:
                metrics.append(S.METRIC.pack(n,elapsed,z,q,3.702,3.7001,-math.log(2),-math.log(2),mask,0,flags))
            truth.append(S.TRUTH.pack(n,.06,.5,3.7))
            observations.append(S.OBSERVATION.pack(n-1,S.DT,.003,3.701))
        if n<=query_count:
            queries.append({'event':'query','schema':'mumble_continuous_query_v1','next_index':n,
                'epoch_begin':0,'reason':'initial' if n==0 else 'scheduled','aggregate':es[0],
                'components':es[1:],'log_weights':[-math.log(2)]*2,
                'all_component_hull':[.4,.8,.03,.1], 'bank_evidence_next_index':n,
                'last_rejection_stage':'none'})
    for name,rows in [('metrics.bin',metrics),('truth.bin',truth),('observations.bin',observations)]:
        (path/name).write_bytes(b''.join(rows))
    for name,rows in [('truth.jsonl',fulltruth),('queries.jsonl',queries)]:
        (path/name).write_text(''.join(json.dumps(x)+'\n' for x in rows))
    (path/'plan.json').write_text(json.dumps(tiny_plan()))
    return dict(metrics=path/'metrics.bin',truth=path/'truth.bin',queries=path/'queries.jsonl',
                full_truth=path/'truth.jsonl',plan=path/'plan.json',cell='cell_b',arm='fabricated',
                start_index=0,end_index=5,observations=path/'observations.bin',
                observations_start_index=0,output=path/'scores.json',required_query_indices=list(range(6)))


def change_metric(path, index, **fields):
    names=['next_index','elapsed','SOC','Q','forecast','fit','old0','old1','mask','rc','flags']
    data=bytearray(path.read_bytes())
    offset=(index-1)*S.METRIC.size
    values=list(S.METRIC.unpack_from(data,offset))
    for name,value in fields.items():values[names.index(name)]=value
    data[offset:offset+S.METRIC.size]=S.METRIC.pack(*values)
    path.write_bytes(data)


def change_json(path, modify):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    modify(rows)
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))


class ScoreTests(unittest.TestCase):
    def test_weighted_error_statistics_and_first_tied_peak(self):
        st=S.ErrorStats()
        st.add(2.,1.,S.stamp(1));st.add(-2.,3.,S.stamp(2))
        result=st.result()
        self.assertEqual(result['signed_mean'],-1.)
        self.assertEqual(result['RMS'],2.)
        self.assertEqual(result['first_peak']['next_index'],1)

    def test_unavailable_breaks_sustained_attainment_and_counts_in_denominator(self):
        t=S.Target(.5)
        for n,error,available in [(1,.1,True),(2,.1,False),(3,.2,True),(4,.3,True)]:
            t.add(error,available,S.stamp(n))
        r=t.result(4,True)
        self.assertEqual(r['first_observed_hit']['next_index'],1)
        self.assertEqual(r['all_later_required_samples_pass_from']['next_index'],3)
        self.assertEqual(r['pass_fraction_all_required_intervals'],.75)
        self.assertEqual(r['unavailable_samples'],1)
        self.assertEqual(r['longest_unavailable_duration_s'],S.DT)

    def test_partial_window_cannot_claim_sustained_retention(self):
        t=S.Target(.5)
        for n in range(1,4):t.add(.1,True,S.stamp(n))
        r=t.result(5,False,{'available':True,'error':.1,'at':S.stamp(0)},True)
        self.assertIsNone(r['all_later_required_samples_pass_from'])
        self.assertEqual(r['classification'],'incomplete_window')
        self.assertEqual(r['unobserved_interval_samples'],2)

    def test_retention_entry_and_within_preferred_drift(self):
        t=S.Target(.5)
        t.add(.2,True,S.stamp(1));t.add(.4,True,S.stamp(2))
        r=t.result(2,True,{'available':True,'error':.1,'at':S.stamp(0)},True)
        self.assertEqual(r['classification'],'retained')
        self.assertEqual(r['all_later_required_samples_pass_from']['next_index'],0)
        self.assertEqual(r['first_observed_hit']['next_index'],0)
        self.assertEqual(r['first_interval_end_hit']['next_index'],1)
        r2=t.result(2,True,{'available':True,'error':1.,'at':S.stamp(0)},True)
        self.assertEqual(r2['classification'],'not_acquired_at_entry')
        prior=t.result(2,True,{'available':True,'error':.1,'at':S.stamp(0),'learned':False})
        self.assertEqual(prior['first_observed_hit']['next_index'],1)

    def test_complete_stream_raw_prior_forecast_uncertainty_and_natural_vector(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d))
            r=S.score_arm(**args)
            self.assertTrue(r['completed_valid_arm'])
            self.assertAlmostEqual(r['initial_raw_point']['raw_SOC'],.68)
            self.assertAlmostEqual(r['initial_raw_point']['raw_Q_Ah'],.06)
            self.assertFalse(r['initial_raw_point']['available']['SOC_pp'])
            q=r['windows']['whole_arm']['quantities']
            self.assertEqual(q['SOC_pp']['targets']['preferred']['all_later_required_samples_pass_from']['next_index'],4)
            self.assertEqual(q['SOC_pp']['targets']['preferred']['pass_fraction_all_required_intervals'],3/5)
            self.assertEqual(r['windows']['first_retention']['quantities']['SOC_pp']['targets']['preferred']['classification'],'retention_failed')
            self.assertEqual(r['windows']['final_retention']['quantities']['SOC_pp']['targets']['preferred']['classification'],'retained')
            voltage=r['windows']['whole_arm']['voltage']
            self.assertAlmostEqual(voltage['causal_clean_mV']['RMS'],2.)
            self.assertAlmostEqual(voltage['noisy_innovation_mV']['signed_mean'],-1.)
            self.assertAlmostEqual(voltage['filtered_fit_clean_mV']['RMS'],.1)
            audit=r['full_query_audit']
            self.assertEqual(audit['uncertainty']['component0']['SOC_pp']['raw_local_provisional_hard_error_breaches'],1)
            self.assertEqual(audit['natural_vector_errors']['aggregate']['tau1_s']['maximum_absolute_error'],0.)
            self.assertEqual(audit['saved_queries_scored'],6)
            self.assertTrue(args['output'].with_suffix('.full_scores.jsonl.gz').is_file())
            self.assertAlmostEqual(r['windows']['whole_arm']['charge']['signed_Ah'],5*.003*S.DT/3600)

    def test_partial_stream_keeps_frozen_endpoint_and_missing_tail(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d),metric_count=3)
            r=S.score_arm(**args,expected_complete=False)
            self.assertFalse(r['completed_valid_arm'])
            self.assertEqual(r['intended_end_index'],5)
            self.assertEqual(r['last_scored_consumed_index'],3)
            t=r['windows']['whole_arm']['quantities']['Q_percent']['targets']['hard']
            self.assertIsNone(t['all_later_required_samples_pass_from'])
            self.assertEqual(t['unobserved_interval_samples'],2)
            self.assertEqual(t['classification'],'incomplete_window')

    def test_rejected_flag_even_return_zero_cannot_pass_target(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d),metric_count=5,invalid_at=5)
            r=S.score_arm(**args,expected_complete=False)
            self.assertFalse(r['completed_valid_arm'])
            self.assertEqual(r['invalid_transaction_records'],1)
            t=r['windows']['final_retention']['quantities']['Q_percent']['targets']['preferred']
            self.assertEqual(t['classification'],'incomplete_window')
            self.assertIsNone(t['all_later_required_samples_pass_from'])

    def test_exclusive_outputs_and_truncated_metric_flag(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d))
            with args['metrics'].open('ab') as f:f.write(b'!')
            r=S.score_arm(**args,expected_complete=False)
            self.assertFalse(r['completed_valid_arm'])
            self.assertTrue(any(x['kind']=='partial_metric_record' for x in r['input_or_accounting_issues']))
            with self.assertRaises(FileExistsError):S.score_arm(**args)

    def test_nonzero_global_suffix_joins_correct_truth(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);args=fixture(path)
            data=(path/'metrics.bin').read_bytes()[2*S.METRIC.size:]
            (path/'metrics.bin').write_bytes(data)
            rows=[json.loads(x) for x in (path/'queries.jsonl').read_text().splitlines()]
            rows=[x for x in rows if x['next_index']>=2]
            rows[0]['reason']='cold_reset';rows[0]['epoch_begin']=2
            for ent in [rows[0]['aggregate'],*rows[0]['components']]:
                ent['point_available']=ent['capacity_available']=0
            (path/'queries.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
            args.update(start_index=2,cell='cell_a',arm='suffix',required_query_indices=list(range(2,6)))
            r=S.score_arm(**args)
            self.assertEqual(r['consumed_intervals_scored'],3)
            self.assertEqual(r['epoch_begin'],2)
            self.assertEqual(r['last_scored_consumed_index'],5)
            self.assertEqual(r['windows']['whole_arm']['quantities']['SOC_pp']['targets']['preferred']['first_observed_hit']['nominal_time_since_epoch_s'],2/35)

    def test_asserted_available_nonfinite_voltage_and_exact_clock_invalidate(self):
        for fields,kind in [({'forecast':float('nan')},'nonfinite_asserted_available_output'),
                            ({'fit':float('nan')},'nonfinite_asserted_available_output'),
                            ({'elapsed':.06},'metric_clock_recurrence_mismatch')]:
            with self.subTest(fields=fields),tempfile.TemporaryDirectory() as d:
                args=fixture(Path(d));change_metric(args['metrics'],2,**fields)
                r=S.score_arm(**args)
                self.assertFalse(r['completed_valid_arm'])
                self.assertEqual(r['invalid_transaction_records'],1)
                self.assertTrue(any(i['kind']==kind for i in r['input_or_accounting_issues']))
                self.assertEqual(r['windows']['whole_arm']['quantities']['SOC_pp']['targets']['hard']['classification'],'incomplete_window')
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d));change_metric(args['metrics'],2,mask=3,forecast=float('nan'),fit=float('nan'))
            r=S.score_arm(**args)
            self.assertTrue(r['completed_valid_arm'])
            self.assertEqual(r['windows']['whole_arm']['voltage']['causal_clean_mV']['finite_samples'],4)

    def test_required_query_grid_missing_future_duplicate_and_absent_contract(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d),query_count=0);r=S.score_arm(**args)
            self.assertFalse(r['completed_valid_arm'])
            self.assertEqual(r['full_query_audit']['missing_required_query_indices'],[1,2,3,4,5])
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d),metric_count=3,query_count=5);r=S.score_arm(**args,expected_complete=False)
            self.assertFalse(r['completed_valid_arm'])
            self.assertTrue(any(i['kind']=='query_beyond_scalar_prefix' for i in r['input_or_accounting_issues']))
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d));change_json(args['queries'],lambda rows:rows.insert(2,rows[1]))
            with self.assertRaises(S.ScoringError):S.score_arm(**args)
            self.assertEqual(json.loads(args['output'].read_text())['schema'],'mumble_continuous_scoring_failure_v1')
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d));args.pop('required_query_indices');r=S.score_arm(**args)
            self.assertFalse(r['completed_valid_arm'])
            self.assertFalse(r['full_query_audit']['query_grid_verified'])

    def test_nonfinite_required_vectors_and_asserted_ranges_invalidate(self):
        mutations=[('queries',lambda rows:rows[2]['components'][0]['mean'].__setitem__(0,None),
                    'invalid_required_full16_estimate'),
                   ('full_truth',lambda rows:rows[2]['mean'].__setitem__(0,None),
                    'missing_or_invalid_full16_truth'),
                   ('queries',lambda rows:rows[2]['aggregate'].__setitem__('soc_local_lower',.9),
                    'invalid_asserted_available_local_range_or_sd'),
                   ('queries',lambda rows:rows[2]['aggregate']['coordinate_sd'].__setitem__(0,None),
                    'invalid_asserted_available_local_range_or_sd')]
        for field,mutation,kind in mutations:
            with self.subTest(kind=kind,field=field),tempfile.TemporaryDirectory() as d:
                args=fixture(Path(d));change_json(args[field],mutation);r=S.score_arm(**args)
                self.assertFalse(r['completed_valid_arm'])
                self.assertTrue(any(i['kind']==kind for i in r['input_or_accounting_issues']))
                self.assertFalse(r['windows']['final_retention']['completed_declared_window'])
                if field=='full_truth':self.assertEqual(r['full_query_audit']['missing_full16_truth_indices'],[2])
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d))
            def unavailable(rows):
                e=rows[3]['aggregate'];e['soc_local_lower']=None;e['coordinate_sd']=[None]*16
            change_json(args['queries'],unavailable);r=S.score_arm(**args)
            self.assertTrue(r['completed_valid_arm'])

    def test_supplemental_truth_stream_merge_and_conflicting_duplicate(self):
        for conflict in (False,True):
            with self.subTest(conflict=conflict),tempfile.TemporaryDirectory() as d:
                path=Path(d);args=fixture(path)
                rows=[json.loads(line) for line in args['full_truth'].read_text().splitlines()]
                supplemental=path/'supplemental.jsonl'
                extra=[rows[2],json.loads(json.dumps(rows[4]))]
                if conflict:extra[1]['SOC']=.4
                supplemental.write_text(''.join(json.dumps(row)+'\n' for row in extra))
                args['full_truth'].write_text(''.join(json.dumps(row)+'\n' for row in rows if row['next_index']!=2))
                if conflict:
                    with self.assertRaises(S.ScoringError):S.score_arm(**args,supplemental_full_truth=supplemental)
                else:
                    r=S.score_arm(**args,supplemental_full_truth=supplemental)
                    self.assertTrue(r['completed_valid_arm'])
                    self.assertEqual(r['full_query_audit']['missing_full16_truth_indices'],[])
                    self.assertEqual(r['full_query_audit']['saved_queries_scored'],6)

    def test_shared_compressed_and_json_output_cap_preserves_failure(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(Path(d));cap=8192
            with self.assertRaises(S.OutputLimitError):S.score_arm(**args,max_output_bytes=cap)
            detail=args['output'].with_suffix('.full_scores.jsonl.gz')
            self.assertLessEqual(args['output'].stat().st_size+detail.stat().st_size,cap)
            failure=json.loads(args['output'].read_text())
            self.assertEqual(failure['error_type'],'OutputLimitError')
            self.assertTrue(failure['partial_outputs_preserved'])


if __name__=='__main__':
    unittest.main(verbosity=2)
