import copy
import os
import unittest
from unittest.mock import patch
import fbs_document_chain as m


class MemoryCache:
    def __init__(self):
        self.data = {}
        self.claims = set()
    def get(self, key):
        return copy.deepcopy(self.data.get(key))
    def put(self, key, value):
        self.data[key] = copy.deepcopy(value)
    def claim(self, key, value):
        if key in self.claims:
            return False
        self.claims.add(key)
        self.put(key, value)
        return True
    def pending(self):
        return []


class NoNetwork:
    def request(self, *args, **kwargs):
        raise AssertionError('Unexpected API call')


class DailyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryCache()
        self.config = {'cabinet': 'token_2', 'writes_enabled': True, 'status': 'active',
                       'scope_confirmed': True, 'execution_policy': {'forbid_negative_stock': True}}
        self.worker = m.Worker(NoNetwork(), self.db, self.config)
        self.db.put(m.STATE, {'activated_at': '2026-11-01T00:00:00Z', 'baseline_done_ids': []})
        self.worker.supplies = lambda: []

    def at(self, utc, kind='poll'):
        return patch.multiple(m, now=lambda: utc), patch.dict(os.environ, {'FBS_EXECUTION_KIND': kind, 'FBS_OWNER_APPROVAL_ID': ''})

    def test_before_1900_has_no_execution_or_claim(self):
        a, b = self.at('2026-11-04T15:59:59+00:00')
        with a, b:
            self.assertEqual(self.worker.run('run')['status'], 'waiting_for_daily_time')
        self.assertFalse(self.db.claims)

    def test_1900_runs_once_even_with_duplicate_invocation(self):
        a, b = self.at('2026-11-04T16:00:00+00:00')
        with a, b:
            self.assertEqual(self.worker.run('run')['status'], 'done')
            self.assertEqual(self.worker.run('run')['status'], 'daily_run_already_claimed')
            other = m.Worker(NoNetwork(), self.db, self.config)
            self.assertEqual(other.run('run')['status'], 'daily_run_already_claimed')
        self.assertEqual(len(self.db.claims), 1)

    def test_next_day_gets_new_daily_claim(self):
        for day in ('04', '05'):
            a, b = self.at(f'2026-11-{day}T16:00:00+00:00')
            with a, b:
                self.assertEqual(self.worker.run('run')['status'], 'done')
        self.assertEqual(len(self.db.claims), 2)

    def test_after_daily_window_waits(self):
        a, b = self.at('2026-11-04T17:00:00+00:00')
        with a, b:
            self.assertEqual(self.worker.run('run')['status'], 'waiting_for_daily_time')

    def test_manual_run_always_requires_confirmation(self):
        a, b = self.at('2026-11-04T16:00:00+00:00', 'manual')
        with a, b:
            self.assertEqual(self.worker.run('run')['status'], 'owner_approval_required')
        self.assertTrue(self.db.get('fbs_document_chain:china:owner_approval_request:v1')['owner_confirmation_required'])

    def test_direct_process_cannot_bypass_schedule(self):
        a, b = self.at('2026-11-04T16:00:00+00:00')
        with a, b, self.assertRaises(m.Stop):
            self.worker.process({'supply': {'id': 'supply-1'}})

    def test_confirmation_is_one_time_and_supply_scoped(self):
        self.db.put('fbs_document_chain:china:owner_approval:v1:approved', {
            'owner_confirmed': True, 'cabinet': 'token_2', 'expires_at': '2026-11-04T20:00:00Z',
            'supply_ids': ['supply-1']})
        with patch.object(m, 'now', return_value='2026-11-04T12:00:00+00:00'), patch.dict(os.environ, {'FBS_EXECUTION_KIND': 'manual', 'FBS_OWNER_APPROVAL_ID': 'approved'}):
            self.assertIsNone(self.worker.execution_permission())
            self.worker.require_execution_permission('supply-1')
            with self.assertRaises(m.Stop):
                self.worker.require_execution_permission('different-supply')
            other = m.Worker(NoNetwork(), self.db, self.config)
            self.assertEqual(other.execution_permission()['status'], 'owner_approval_already_used')

    def test_expired_or_wrong_cabinet_confirmation_is_denied(self):
        for cabinet, expiry in [('token_1', '2026-11-05T00:00:00Z'), ('token_2', '2026-11-03T00:00:00Z')]:
            self.db.put('fbs_document_chain:china:owner_approval:v1:bad', {'owner_confirmed': True,
                'cabinet': cabinet, 'expires_at': expiry, 'supply_ids': ['supply-1']})
            with patch.object(m, 'now', return_value='2026-11-04T12:00:00+00:00'), patch.dict(os.environ, {'FBS_EXECUTION_KIND': 'manual', 'FBS_OWNER_APPROVAL_ID': 'bad'}):
                self.assertEqual(self.worker.execution_permission()['status'], 'owner_approval_required')

    def test_shortage_blocks_creation_and_records_owner_question(self):
        ref = lambda kind, ident: {'meta': {'href': m.MS+'entity/'+kind+'/'+ident}}
        payload = {'store': ref('store', 'warehouse'), 'positions': [
            {'quantity': 3, 'price': 0, 'assortment': ref('product', 'product')} ]}
        self.worker.ms_rows = lambda *a, **k: []
        self.worker._execution_permit = {'kind': 'daily'}
        state = {'supply': {'id': 'supply-1'}}
        with self.assertRaisesRegex(m.Stop, 'Insufficient'):
            self.worker.ensure('demand', payload, state, 'supply-state')
        self.assertNotIn('inflight', state)
        self.assertTrue(self.db.get('fbs_document_chain:china:stock_approval_request:v1')['owner_confirmation_required'])

    def test_atomic_claim_requests_ignore_conflicts(self):
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://private.example'}):
            transport = m.Transport()
            with patch.object(transport, '_request_once', return_value=[]) as call:
                self.assertFalse(transport.insert_cache_once({'cache_key': 'slot'}))
                self.assertEqual(call.call_args.kwargs['cache_prefer'], 'resolution=ignore-duplicates,return=representation')


if __name__ == '__main__':
    unittest.main()
