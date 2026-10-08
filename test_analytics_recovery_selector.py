import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import select_task as selector

class AnalyticsRecoverySelectorTests(unittest.TestCase):
    def test_due_work_uses_finance_lock_and_cooldown_is_respected(self):
        now=datetime(2026,10,8,11,tzinfo=timezone.utc)
        for delta,due in ((-1,True),(5,False)):
            with patch.object(selector,'database',return_value=[{'payload':{'next_retry_at':(now+timedelta(minutes=delta)).isoformat()}}]):
                self.assertEqual(bool(selector.recovery_work(now)),due)
                if due:self.assertEqual(selector.recovery_work(now)[0]['group'],'advertising-and-finance')
    def test_new_completed_recovery_can_start_mpstats_rank_collection(self):
        now=datetime(2026,10,8,11,tzinfo=timezone.utc)
        state={'planned_day':'2026-10-08','requests':[],'last_recovery_ingested_at':'2026-10-08T10:00:00Z'}
        requests=[{'updated_at':'2026-10-08T11:00:00Z','payload':{'mpstats_requests':[{'key':'rank'}]}}]
        with patch.object(selector,'database',side_effect=[[{'payload':state}],[],requests]):
            self.assertEqual(selector.mpstats_work(now),[{'task':'mpstats_recovery','group':'mpstats-data'}])

if __name__=='__main__':unittest.main()
