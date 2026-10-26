import unittest
from review_approved_watchdog import should_dispatch
class WatchdogTests(unittest.TestCase):
    cfg=dict(enabled=True,publication_enabled=True,destination_verified=True)
    def test_completion_resumes_pending(self):
        for conclusion in ('success','failure','cancelled','timed_out'):
            self.assertTrue(should_dispatch(self.cfg,[{}],[dict(status='completed',conclusion=conclusion)]))
    def test_active_or_queued_never_duplicates(self):
        for status in ('queued','in_progress','waiting','pending','requested'):
            self.assertFalse(should_dispatch(self.cfg,[{}],[dict(status=status)]))
    def test_empty_queue_stops(self):self.assertFalse(should_dispatch(self.cfg,[],[]))
    def test_each_kill_switch_stops(self):
        for key in self.cfg:self.assertFalse(should_dispatch(dict(self.cfg,**{key:False}),[{}],[]))
if __name__=='__main__':unittest.main()
