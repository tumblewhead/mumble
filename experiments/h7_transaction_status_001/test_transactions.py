"""Finite synchronous H7 transaction witnesses; no coverage/lifetime certificate.

Run with OPENBLAS_NUM_THREADS=1 python3 -B -m unittest
experiments.h7_transaction_status_001.test_transactions -v.
Only public calibration and deterministic sensor rows enter these fixtures.
"""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from experiments.foster_campaign_001.h7_backend import H7Backend


class TransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='mumble-h7-transactions-')
        cls.path = Path(cls.temp.name)
        cls.config = json.loads(Path('experiments/foster_feedback_001/calibration.json').read_text())
        cls.config['hysteresis_chart'] = 'bounded'
        i = np.arange(16)
        cls.rows = np.c_[np.where(i % 13 == 0, 0., 1 / 35),
                         np.where(i < 8, .04, -.06),
                         np.full(16, 25.), 3.7 + .001 * np.sin(i),
                         np.full(16, .004)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def bank(self):
        return H7Backend(self.path, self.config, 'transaction-source',
                         'transaction-model', 35,
                         SimpleNamespace(field_refresh_seconds=1000))

    def test_numpy_integer_indices_remain_serializable_and_exact(self):
        for dtype in (np.int64, np.uint64):
            with self.subTest(dtype=dtype):
                bank = self.bank()
                control = self.bank()
                for first in (0, 16):
                    bank.advance(dtype(first), self.rows)
                    control.advance(first, self.rows)
                    self.assertEqual(bytes(bank.context), bytes(control.context))
                    self.assertEqual(type(bank.live_count), int)
                    self.assertEqual(type(bank.failure_index), int)
                    json.dumps(bank.publication_status(), allow_nan=False)
                    json.dumps(bank.counts(), allow_nan=False)
                    saved = bank.checkpoint_arrays()
                    bank.restore_arrays(saved)
                with patch.object(bank, '_publish', side_effect=ValueError('late failure')):
                    with self.assertRaises(ValueError):
                        bank.advance(dtype(32), self.rows)
                self.assertEqual(type(bank.publication_status()['failure']['input_first']), int)
                json.dumps(bank.counts(), allow_nan=False)

    def test_configuration_identity_binds_representation_clock_and_cadence(self):
        from experiments.foster_campaign_001.tangent_backend import TangentBackend
        def make(cls, rate=35, cadence=17):
            return cls(self.path, self.config, 'transaction-source', 'transaction-model',
                       rate, SimpleNamespace(field_refresh_seconds=cadence))
        reference = make(H7Backend)
        variants = [make(TangentBackend), make(H7Backend, rate=100),
                    make(H7Backend, cadence=1000)]
        ids = {bank.configuration_id for bank in [reference, *variants]}
        self.assertEqual(len(ids), 4)
        self.assertEqual(reference.configuration_id, make(H7Backend).configuration_id)
        for bank in variants:
            with self.assertRaisesRegex(ValueError, 'identity/configuration'):
                bank.restore_arrays(reference.checkpoint_arrays())
            self.assertTrue(bank.failed)

    def test_invalid_index_cannot_poison_later_restore_diagnostics(self):
        for invalid in (np.float32(0), object(), '0', np.bool_(False)):
            with self.subTest(type=type(invalid).__name__):
                bank = self.bank()
                saved = bank.checkpoint_arrays()
                previous = bank.failure_index
                with self.assertRaisesRegex(ValueError, 'source/order'):
                    bank.advance(invalid, self.rows)
                self.assertEqual(bank.failure_index, previous)
                with patch.object(bank.native, 'query', side_effect=ValueError('restore query fault')):
                    with self.assertRaisesRegex(ValueError, 'restore query fault'):
                        bank.restore_arrays(saved)
                status = bank.publication_status()
                self.assertEqual(status['failure']['operation'], 'restore')
                self.assertIsNone(status['failure']['input_first'])
                self.assertEqual(status['readout'], 'unavailable')
                json.dumps(bank.counts(), allow_nan=False)
                bank.restore_arrays(saved)
                self.assertEqual(bank.publication_status()['readout'], 'current')

    def field_snapshot(self, field):
        return (field.root.copy(), field.state.copy(), field.count, field.noise)

    def assert_field_equal(self, field, before):
        np.testing.assert_array_equal(field.root, before[0])
        np.testing.assert_array_equal(field.state, before[1])
        self.assertEqual(field.count, before[2])
        self.assertEqual(field.noise, before[3])

    def assert_quarantined(self, bank, consumed, published, message):
        status = bank.publication_status()
        self.assertEqual(status['execution'], 'quarantined')
        self.assertEqual(status['readout'], 'unavailable')
        self.assertEqual(status['consumed_records'], consumed)
        self.assertEqual(status['published_records'], published)
        self.assertEqual(status['authorization'], 'unresolved')
        self.assertEqual(bank.counts()['pending_records'], consumed - published)
        np.testing.assert_array_equal(bank.last_message(), message)
        np.testing.assert_array_equal(bank.publication()['message'], message)
        for operation in (bank.full_message, bank.checkpoint_arrays,
                          lambda: bank.readout(self.rows)):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                operation()
        with self.assertRaisesRegex(ValueError, 'already unresolved'):
            bank.advance(published, self.rows)
        self.assertTrue(bank.failed)

    def test_mixed_qr_exception_preserves_all_committed_fields(self):
        field = self.bank().field
        field.update(0, self.rows)
        before = self.field_snapshot(field)
        with patch('numpy.linalg.qr', side_effect=np.linalg.LinAlgError('injected QR')):
            with self.assertRaisesRegex(np.linalg.LinAlgError, 'injected QR'):
                field.update(16, self.rows)
        self.assert_field_equal(field, before)
        field.update(16, self.rows)
        self.assertEqual(field.count, 32)

    def test_mixed_nonfinite_qr_preserves_all_committed_fields(self):
        field = self.bank().field
        field.update(0, self.rows)
        before = self.field_snapshot(field)
        with patch('numpy.linalg.qr', return_value=np.full_like(field.root, np.nan)):
            with self.assertRaisesRegex(ValueError, 'nonfinite likelihood root'):
                field.update(16, self.rows)
        self.assert_field_equal(field, before)

    def test_mixed_failed_response_preserves_all_committed_fields(self):
        field = self.bank().field
        before = self.field_snapshot(field)
        # Response callback may alter its output buffer before signaling failure.
        def fail(*args):
            args[-2][0] = 123.
            return 1
        with patch.object(field, 'fn', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'response recurrence failed'):
                field.update(0, self.rows)
        self.assert_field_equal(field, before)

    def test_mixed_nonfinite_response_preserves_all_committed_fields(self):
        field = self.bank().field
        before = self.field_snapshot(field)
        response = field.fn
        def nonfinite(*args):
            result = response(*args)
            args[-2][0] = np.nan
            return result
        with patch.object(field, 'fn', side_effect=nonfinite):
            with self.assertRaisesRegex(ValueError, 'response recurrence failed'):
                field.update(0, self.rows)
        self.assert_field_equal(field, before)

    def test_flush_qr_exception_preserves_field_and_pending_rows(self):
        bank = self.bank()
        bank.advance(0, self.rows)
        before = self.field_snapshot(bank.field)
        pending = bank.pending_rows[:bank.buffered].copy()
        with patch('numpy.linalg.qr', side_effect=MemoryError('injected allocation')):
            with self.assertRaises(MemoryError):
                bank._flush_field()
        self.assert_field_equal(bank.field, before)
        self.assertEqual(bank.buffered, 16)
        np.testing.assert_array_equal(bank.pending_rows[:bank.buffered], pending)
        bank._flush_field()
        self.assertEqual(bank.field.count, 16)
        self.assertEqual(bank.buffered, 0)
        np.testing.assert_array_equal(bank.field.state, bank.live_state)

    def test_flush_parity_failure_preserves_field(self):
        bank = self.bank()
        bank.advance(0, self.rows)
        before = self.field_snapshot(bank.field)
        bank.live_state[0] += 1
        with self.assertRaisesRegex(ValueError, 'transport mismatch'):
            bank._flush_field()
        self.assert_field_equal(bank.field, before)
        self.assertEqual(bank.buffered, 16)

    def test_consumption_then_flush_failure_is_not_input_rejection(self):
        bank = self.bank()
        message = bank.full_message()
        before = self.field_snapshot(bank.field)
        with patch('experiments.foster_campaign_001.tangent_backend.BUFFER_RECORDS', 16), \
             patch('numpy.linalg.qr', side_effect=np.linalg.LinAlgError('flush fault')):
            with self.assertRaisesRegex(np.linalg.LinAlgError, 'flush fault'):
                bank.advance(0, self.rows)
        self.assertEqual(bank.native.count, 16)
        self.assert_field_equal(bank.field, before)
        self.assertEqual(bank.buffered, 16)
        self.assert_quarantined(bank, 16, 0, message)

    def test_native_consumption_then_wrapper_failure_reports_native_count(self):
        bank = self.bank()
        message = bank.full_message()
        step = bank.native.step
        def consume_then_fail(*args, **kwargs):
            step(*args, **kwargs)
            raise MemoryError('after native commit')
        with patch.object(bank.native, 'step', side_effect=consume_then_fail):
            with self.assertRaises(MemoryError):
                bank.advance(0, self.rows)
        self.assertEqual(bank.live_count, 0)
        self.assertEqual(bank.native.count, 16)
        self.assert_quarantined(bank, 16, 0, message)

    def test_consumption_then_query_exception_quarantines(self):
        bank = self.bank()
        message = bank.full_message()
        with patch.object(bank.native, 'query', side_effect=MemoryError('query allocation')):
            with self.assertRaises(MemoryError):
                bank.advance(0, self.rows)
        self.assert_quarantined(bank, 16, 0, message)

    def test_consumption_then_failed_query_recovery_quarantines(self):
        bank = self.bank()
        message = bank.full_message()
        with patch.object(bank.native, 'query', side_effect=ValueError('query domain')), \
             patch('experiments.foster_campaign_001.tangent_backend.solve', side_effect=ValueError('fit unresolved')):
            with self.assertRaisesRegex(ValueError, 'recovery unresolved'):
                bank.advance(0, self.rows)
        self.assertEqual(bank.field.count, 16)
        self.assertEqual(bank.audit['rejected'], 1)
        self.assert_quarantined(bank, 16, 0, message)

    def test_consumption_then_nonfinite_publication_preserves_old_payload(self):
        bank = self.bank()
        message = bank.full_message()
        old_w = bank.w.copy()
        query = bank.native.query
        def malformed(*args, **kwargs):
            result = query(*args, **kwargs)
            result['endpoint_root'] = np.full((16, 16), np.nan)
            return result
        with patch.object(bank.native, 'query', side_effect=malformed):
            with self.assertRaisesRegex(ValueError, 'nonfinite tangent readout'):
                bank.advance(0, self.rows)
        np.testing.assert_array_equal(bank.w, old_w)
        self.assert_quarantined(bank, 16, 0, message)

    def test_failure_after_publication_still_revokes_readout(self):
        bank = self.bank()
        with patch.object(bank, 'readout', side_effect=MemoryError('formatting allocation')):
            with self.assertRaises(MemoryError):
                bank.advance(0, self.rows)
        self.assert_quarantined(bank, 16, 16, bank.last_message())

    def test_invalid_admission_does_not_change_valid_state(self):
        bank = self.bank()
        bank.advance(0, self.rows)
        before = bank.checkpoint_arrays()
        carrier = bytes(bank.context)
        status = bank.publication_status()
        cases = [(15, self.rows), (16., self.rows), (True, self.rows),
                 (16, self.rows[:0]), (16, np.zeros((16, 4))),
                 (16, np.tile(self.rows, (2, 1)))]
        for column, value in [(0, -.1), (0, 1.1), (0, .000123), (1, .26),
                              (2, 14.), (2, 36.), (3, np.nan), (4, 0.)]:
            invalid = self.rows.copy()
            invalid[0, column] = value
            cases.append((16, invalid))
        for first, rows in cases:
            with self.subTest(first=first, shape=rows.shape, first_row=rows[:1]):
                with self.assertRaises(ValueError):
                    bank.advance(first, rows)
                self.assertEqual(bytes(bank.context), carrier)
                self.assertEqual(bank.publication_status(), status)
                for key, value in before.items():
                    np.testing.assert_array_equal(bank.checkpoint_arrays()[key], value)
        bank.advance(16, self.rows)
        self.assertEqual(bank.publication_status()['consumed_records'], 32)

    def test_publication_is_provisional_and_snapshots_do_not_alias(self):
        bank = self.bank()
        read, _ = bank.advance(0, self.rows)
        status = read['estimate_status']
        self.assertEqual(status['readout'], 'current')
        self.assertEqual(status['authorization'], 'unresolved')
        self.assertEqual(status['guarantee'], 'provisional_local_precision')
        self.assertEqual(status['source_id'], 'transaction-source')
        self.assertEqual(status['model_id'], 'transaction-model')
        self.assertEqual(status['published_records'], 16)
        expected = bank.full_message()
        snapshots = bank.checkpoint_arrays()
        originals = {key: value.copy() for key, value in snapshots.items()}
        bank.last_message()[:] = 0
        bank.full_message()[:] = 0
        publication = bank.publication()
        publication['message'][:] = 0
        publication['status']['source_id'] = 'changed'
        for value in snapshots.values():
            if value.flags.writeable:
                value[...] = 0
        np.testing.assert_array_equal(bank.full_message(), expected)
        for key, value in originals.items():
            np.testing.assert_array_equal(bank.checkpoint_arrays()[key], value)

    def test_admission_counter_overflow_does_not_consume(self):
        for counter in ('tokens', 'ticks', 'sequence'):
            with self.subTest(counter=counter):
                bank = self.bank()
                setattr(bank.carrier, counter, 2**64 - 1)
                first = int(bank.carrier.sequence)
                if counter == 'sequence':
                    bank.field.count = first
                carrier = bytes(bank.context)
                native = bank.native.snapshot()
                before = self.field_snapshot(bank.field)
                with self.assertRaisesRegex(ValueError, 'counter range'):
                    bank.advance(first, self.rows)
                self.assertEqual(bytes(bank.context), carrier)
                np.testing.assert_array_equal(bank.native.snapshot(), native)
                self.assert_field_equal(bank.field, before)
                self.assertFalse(bank.failed)

    def test_failure_metadata_copy_does_not_alias(self):
        bank = self.bank()
        with patch.object(bank, '_publish', side_effect=MemoryError('publish allocation')):
            with self.assertRaises(MemoryError):
                bank.advance(0, self.rows)
        expected = bank.publication_status()
        status = bank.publication_status()
        status['failure']['reason'] = 'changed'
        bank.publication()['status']['failure']['reason'] = 'also changed'
        self.assertEqual(bank.publication_status(), expected)

    def test_bad_restore_quarantines_and_valid_restore_recovers(self):
        bank = self.bank()
        bank.advance(0, self.rows)
        saved = bank.checkpoint_arrays()
        message = bank.full_message()
        bad = {key: value.copy() for key, value in saved.items()}
        meta = json.loads(bad['metadata'].tobytes())
        meta['source_id'] = 'wrong-source'
        bad['metadata'] = np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, 'identity/configuration'):
            bank.restore_arrays(bad)
        self.assert_quarantined(bank, 16, 16, message)
        # Another rejected restore must not clear quarantine.
        with self.assertRaises(ValueError):
            bank.restore_arrays(bad)
        self.assertTrue(bank.failed)
        bank.restore_arrays(saved)
        self.assertFalse(bank.failed)
        self.assertIsNone(bank.publication_status()['failure'])
        np.testing.assert_array_equal(bank.full_message(), message)
        bank.advance(16, self.rows)
        self.assertEqual(bank.publication_status()['published_records'], 32)

    def test_restore_after_native_consumption_replays_gap_once(self):
        bank = self.bank()
        control = self.bank()
        saved = bank.checkpoint_arrays()
        with patch.object(bank, '_publish', side_effect=MemoryError('publish allocation')):
            with self.assertRaises(MemoryError):
                bank.advance(0, self.rows)
        self.assertEqual(bank.native.count, 16)
        bank.restore_arrays(saved)
        self.assertEqual(bank.native.count, 0)
        bank.advance(0, self.rows)
        control.advance(0, self.rows)
        np.testing.assert_array_equal(bank.full_message(), control.full_message())
        np.testing.assert_array_equal(bank.native.snapshot(), control.native.snapshot())
        np.testing.assert_array_equal(bank.live_state, control.live_state)

    def test_restore_native_query_failure_quarantines(self):
        bank = self.bank()
        bank.advance(0, self.rows)
        saved = bank.checkpoint_arrays()
        message = bank.full_message()
        with patch.object(bank.native, 'query', side_effect=MemoryError('restore query allocation')):
            with self.assertRaises(MemoryError):
                bank.restore_arrays(saved)
        self.assert_quarantined(bank, 16, 16, message)
        bank.restore_arrays(saved)
        np.testing.assert_array_equal(bank.full_message(), message)

    def test_restore_rejects_malformed_state_and_metadata(self):
        for problem in ('count', 'ticks', 'tokens', 'noise', 'model_id',
                        'configuration_id', 'hz', 'interval', 'failed',
                        'root', 'state', 'live_state', 'w', 'pending', 'native'):
            with self.subTest(problem=problem):
                bank = self.bank()
                bank.advance(0, self.rows)
                saved = bank.checkpoint_arrays()
                bad = {key: value.copy() for key, value in saved.items()}
                message = bank.full_message()
                meta = json.loads(bad['metadata'].tobytes())
                if problem in ('root', 'state', 'live_state', 'pending'):
                    bad[problem].flat[0] = np.nan
                elif problem == 'w':
                    bad['w'][0] += 1
                elif problem == 'native':
                    bad['native'] = bad['native'][:-1]
                else:
                    replacements = dict(count=1, ticks=meta['ticks'] + 1,
                                        tokens=meta['tokens'] + 1, noise=float('nan'),
                                        model_id='another-model', configuration_id='another-config',
                                        hz=meta['hz'] + 1, interval=meta['interval'] + 16, failed=True)
                    meta[problem] = replacements[problem]
                    bad['metadata'] = np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8)
                with self.assertRaises(ValueError):
                    bank.restore_arrays(bad)
                self.assert_quarantined(bank, 16, 16, message)
                bank.restore_arrays(saved)
                np.testing.assert_array_equal(bank.full_message(), message)


if __name__ == '__main__':
    unittest.main()
