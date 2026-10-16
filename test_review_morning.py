import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_morning import target_day,eligible
class MorningTests(unittest.TestCase):
    def test_local_moscow_day_and_manual_catchup(self):
        self.assertEqual(target_day(datetime(2026,10,16,5,tzinfo=timezone.utc)),'2026-10-16')
        self.assertIsNone(target_day(datetime(2026,10,16,1,tzinfo=timezone.utc)))
        self.assertEqual(target_day(datetime(2026,10,16,1,tzinfo=timezone.utc),manual=True),'2026-10-16')
    def test_all_three_scopes_and_duplicate_hold_and_journal(self):
        item={'id':'same'}
        for cabinet in ('token_1','token_2','token_3'):
            source=Mock();source.was_notified.return_value=False;source.journal.return_value=None
            repo=Mock();repo.get.return_value=None
            hold=Mock(return_value=None)
            self.assertTrue(eligible(item,cabinet,source,repo,hold))
            source.was_notified.assert_called_with(cabinet,'feedbacks','same')
            source.was_notified.return_value=True
            self.assertFalse(eligible(item,cabinet,source,repo,hold))
            source.was_notified.return_value=False;source.journal.return_value={'state':'pending'}
            self.assertFalse(eligible(item,cabinet,source,repo,hold))
            source.journal.return_value=None;hold.return_value={'active':True}
            self.assertFalse(eligible(item,cabinet,source,repo,hold))
            hold.return_value=None;repo.get.return_value={'status':'held'}
            self.assertFalse(eligible(item,cabinet,source,repo,hold))
    def test_answered_and_missing_id_never_notify(self):
        for item in ({},{'id':'x','isAnswered':True},{'id':'x','answer':{'text':'already'}}):
            self.assertFalse(eligible(item,'token_1',Mock(),Mock(),Mock()))
    def test_no_publication_or_dispatch_entry_points(self):
        text=(Path(__file__).parent/'review_morning.py').read_text(encoding='utf-8')
        for forbidden in ('process_due(', 'send_feedback_reply(', 'send_question_reply(', 'run_private.main(', 'select_task.queue_work('):
            self.assertNotIn(forbidden,text)
        self.assertIn("if '/rpc/' in url:raise",text)
if __name__=='__main__':unittest.main()

