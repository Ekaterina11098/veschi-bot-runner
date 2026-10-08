import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import select_task as s

class DailyFinanceSelectorTests(unittest.TestCase):
    def test_any_cabinet_pending_is_retried_after_deadline(self):
        now=datetime(2026,10,8,7,tzinfo=timezone.utc)
        for cabinet in ('token_1','token_2','token_3'):
            state={'cabinet':cabinet,'status':'pending','next_retry_at':(now-timedelta(seconds=1)).isoformat()}
            with patch.object(s,'database',return_value=[{'payload':state}]):
                self.assertEqual(s.finance_retry_work(now),[{'task':'finance_retry','group':'advertising-and-finance'}])
    def test_active_pause_does_not_query_or_reset_legacy_state(self):
        now=datetime(2026,10,8,7,tzinfo=timezone.utc)
        with patch.object(s,'database',return_value=[{'payload':{'status':'pending','next_retry_at':(now+timedelta(hours=1)).isoformat()}}]) as db:
            self.assertEqual(s.finance_retry_work(now),[])
        self.assertEqual(db.call_count,1)
    def test_running_worker_is_recovered_after_lease(self):
        now=datetime(2026,10,8,7,tzinfo=timezone.utc)
        with patch.object(s,'database',return_value=[{'payload':{'status':'running','next_retry_at':(now-timedelta(minutes=1)).isoformat()}}]):
            self.assertTrue(s.finance_retry_work(now))
    def test_pending_work_survives_moscow_midnight(self):
        now=datetime(2026,10,8,21,tzinfo=timezone.utc)
        with patch.object(s,'database',return_value=[{'payload':{'status':'pending','next_retry_at':'2026-10-08T20:59:00+00:00'}}]):
            self.assertTrue(s.finance_retry_work(now))
    def test_complete_and_auth_errors_do_not_repeat_requests(self):
        for state in ('complete','error','unavailable'):
            with patch.object(s,'database',return_value=[{'payload':{'status':state}}]):
                self.assertEqual(s.finance_retry_work(),[])
    def test_migration_keeps_legacy_cooldown_fallback(self):
        now=datetime(2026,10,8,7,tzinfo=timezone.utc)
        with patch.object(s,'database',side_effect=[[],[{'status':'deferred','collected_at':'2026-10-08T06:00:00Z','detail':'Finance API 429; retry_after=60'}]]):
            self.assertTrue(s.finance_retry_work(now))
if __name__=='__main__':unittest.main()
