import json,os,tempfile,unittest
from unittest.mock import patch
import select_task as s
class AnalyticsPauseTests(unittest.TestCase):
    def output(self,event,schedule='',task=''):
        with tempfile.NamedTemporaryFile() as f:
            with patch.dict(os.environ,{'GITHUB_EVENT_NAME':event,'EVENT_SCHEDULE':schedule,
                'REQUESTED_TASK':task,'SCHEDULE_ANALYTICS_PAUSED':'true','GITHUB_OUTPUT':f.name}):
                s.main()
            f.seek(0);values=dict(l.split('=',1) for l in f.read().decode().splitlines())
        return values,json.loads(values['matrix'])['include']
    def test_scheduled_daily_ads_and_mpstats_pause_without_database(self):
        with patch.object(s,'database',side_effect=AssertionError('No database check')):
            for cron in ('17 4 * * *','0 7 * * *','27 7,11,15,19 * * *'):
                output,work=self.output('schedule',cron)
                self.assertEqual(work,[]);self.assertEqual(output['run'],'false')
            self.assertEqual(self.output('push')[1],[])
    def test_nonanalytic_schedules_and_explicit_dispatch_unchanged(self):
        self.assertEqual(self.output('schedule','45 4 * * *')[1][0]['task'],'reviews')
        self.assertEqual(self.output('schedule','30 13 * * *')[1][0]['task'],'stock')
        self.assertEqual(self.output('workflow_dispatch',task='analytics')[1][0]['task'],'analytics')
    def test_queue_preserves_operational_siblings_without_analytics_selectors(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in ('evening_recovery_work','finance_retry_work','research_work','mpstats_work','recovery_work','budget_work'):
                stack.enter_context(patch.object(s,name,side_effect=AssertionError('Analytic selector called')))
            stack.enter_context(patch.object(s,'database',side_effect=[
                [{'id':1}],[{'feedback_id':1}],[{'payload':{'pending':True,'due':0}}]]))
            stack.enter_context(patch.object(s,'agent_due',return_value=True))
            stack.enter_context(patch.object(s,'business_due',return_value=True))
            stack.enter_context(patch.object(s,'review_inbox_work',return_value=[{'task':'review_inbox_retry','group':'review-replies'}]))
            output,work=self.output('schedule','3-58/5 * * * *')
        self.assertEqual({i['task'] for i in work},{'telegram_queue','review_queue','stock_retry','agent','business_agent','review_inbox_retry'})
        self.assertEqual(output['run'],'true')
