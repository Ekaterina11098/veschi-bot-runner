import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import select_task as selector

class RecoverySelectorTests(unittest.TestCase):
    def test_pending_requests_use_a_separate_serialized_worker(self):
        now=datetime(2026,10,8,6,tzinfo=timezone.utc)
        with patch.object(selector,'database',side_effect=[[{'payload':{'requests':[{'key':'x'}]}}],[]]):
            self.assertEqual(selector.mpstats_work(now),[{'task':'mpstats_recovery','group':'mpstats-data'}])
    def test_cooldown_and_resume_delay_prevent_requests(self):
        now=datetime(2026,10,8,6,tzinfo=timezone.utc)
        for state,pause in (({'requests':[1]},[{'payload':{}}]),({'requests':[1],'next_retry_at':(now+timedelta(minutes=3)).isoformat()},[])):
            with patch.object(selector,'database',side_effect=[[{'payload':state}],pause]):
                self.assertEqual(selector.mpstats_work(now),[])
    def test_completed_day_has_no_worker_but_next_day_collects(self):
        for now,due in ((datetime(2026,10,8,6,tzinfo=timezone.utc),False),(datetime(2026,10,9,6,tzinfo=timezone.utc),True)):
            with patch.object(selector,'database',side_effect=[[{'payload':{'requests':[],'planned_day':'2026-10-08'}}],[]]):
                self.assertEqual(bool(selector.mpstats_work(now)),due)
    def test_missing_connection_state_does_not_start_a_worker(self):
        with patch.object(selector,'database',return_value=[]):
            self.assertEqual(selector.mpstats_work(),[])
if __name__=='__main__':unittest.main()
