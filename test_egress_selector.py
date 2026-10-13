import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import select_task
class SlimSelectors(unittest.TestCase):
    def test_due_state_projection_does_not_request_full_payload(self):
        now=datetime(2026,10,13,6,tzinfo=timezone.utc)
        with patch.object(select_task,'database',side_effect=[[dict(requests={'key':'x'},planned_day='2026-10-13')],[]]) as db:
            self.assertTrue(select_task.mpstats_work(now))
            self.assertNotEqual(db.call_args_list[0].args[1]['select'],'payload')
            self.assertIn('requests:payload->requests->0',db.call_args_list[0].args[1]['select'])
    def test_recovery_due_projection_keeps_future_and_elapsed_behavior(self):
        now=datetime(2026,10,13,6,tzinfo=timezone.utc)
        for retry,due in [('2026-10-13T05:00:00+00:00',True),('2026-10-13T07:00:00+00:00',False)]:
            with patch.object(select_task,'database',return_value=[dict(next_retry_at=retry)]) as db:
                self.assertEqual(bool(select_task.recovery_work(now)),due)
                self.assertEqual(db.call_args.args[1]['select'],'next_retry_at:payload->next_retry_at')
