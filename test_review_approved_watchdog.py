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
    def test_final_job_excludes_only_own_run(self):
        self.assertTrue(should_dispatch(self.cfg,[{}],[dict(id=10,status='in_progress')],finishing_run_id='10'))
        self.assertFalse(should_dispatch(self.cfg,[{}],[dict(id=10,status='in_progress'),dict(id=11,status='queued')],finishing_run_id='10'))
    def test_watchdog_does_not_ignore_unidentified_active_run(self):
        self.assertFalse(should_dispatch(self.cfg,[{}],[dict(status='in_progress')]))
    def test_continuation_preserves_disabled_and_empty_guards(self):
        self.assertFalse(should_dispatch(self.cfg,[],[dict(id=10,status='in_progress')],finishing_run_id='10'))
        self.assertFalse(should_dispatch(dict(self.cfg,enabled=False),[{}],[dict(id=10,status='in_progress')],finishing_run_id='10'))
if __name__=='__main__':unittest.main()
