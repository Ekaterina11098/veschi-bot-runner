import os
import unittest
from unittest.mock import patch
import fbs_wb_cabinets as runner

class FakeCache:
    saved = {}
    def __init__(self, *args): pass
    def get(self, key): return {'writes_enabled': True, 'status': 'active'}
    def put(self, key, value): self.saved[key] = value

class LateStartTests(unittest.TestCase):
    def run_fake(self, kind, status):
        FakeCache.saved = {}
        class FakeWorker:
            def __init__(self, *args): pass
            def run(self, mode): return {'status': status, 'writes': 0}
        with patch.dict(os.environ, {'WB_TOKEN_1':'fake1','WB_TOKEN_2':'fake2','WB_TOKEN_3':'fake3','FBS_EXECUTION_KIND':kind}), patch.object(runner.m, 'Transport'), patch.object(runner, 'ScopedCache', FakeCache), patch.object(runner.m, 'Worker', FakeWorker), patch('builtins.print'):
            runner.main('run')

    def test_late_daily_run_is_failure_and_requests_owner_attention(self):
        with self.assertRaises(SystemExit) as result:
            self.run_fake('daily', 'waiting_for_daily_time')
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(len(FakeCache.saved), 3)
        self.assertTrue(all(v['owner_confirmation_required'] for v in FakeCache.saved.values()))

    def test_successful_daily_run_remains_successful(self):
        self.run_fake('daily', 'done')
        self.assertEqual(FakeCache.saved, {})

    def test_unconfirmed_manual_request_is_not_marked_completed(self):
        self.run_fake('manual', 'owner_approval_required')
        self.assertEqual(FakeCache.saved, {})

if __name__ == '__main__': unittest.main()
