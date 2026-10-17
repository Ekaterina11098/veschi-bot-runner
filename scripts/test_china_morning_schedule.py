import unittest
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from china_morning_schedule import select,SOURCE
from test_china_daily_worker import DailyWorkerTests
from china_agent.morning_pair import PairWorker

class Schedule(unittest.TestCase):
 def test_schedule_ignores_old_manual_date_uses_current_day(self):
  self.assertEqual(select('schedule','',{'source_commit':SOURCE,'report_date':'2026-10-16','action':'verify'},'2026-10-18'),{'allowed':True,'action':'run','report_date':'2026-10-18','mode':'morning'})
 def test_manual_defaults_to_no_sends(self):self.assertEqual(select('workflow_dispatch','',{'source_commit':SOURCE},'2026-10-18')['action'],'verify')
 def test_push_cannot_replay_old_day(self):self.assertFalse(select('push','',{'source_commit':SOURCE,'report_date':'2026-10-17','mode':'morning','action':'run','nonce':'abcdefgh'},'2026-10-18')['allowed'])
 def test_pin_and_action_remain_required(self):
  self.assertFalse(select('schedule','',{'source_commit':'other'},'2026-10-18')['allowed'])
  self.assertFalse(select('workflow_dispatch','other',{'source_commit':SOURCE},'2026-10-18')['allowed'])
 def pair(self,section,day):
  from china_agent.coverage_worker import CoverageWorker
  def init(w,mode):w.day=day;w.audit={}
  with patch.object(CoverageWorker,'__init__',init):return PairWorker(section)
 def test_separate_ids_for_both_reports_and_days(self):
  a=self.pair('candidates',date(2026,10,18));b=self.pair('control',date(2026,10,18));c=self.pair('candidates',date(2026,10,19))
  self.assertEqual(len({a.update_id,b.update_id,c.update_id}),3)
  self.assertNotEqual(a.command,b.command)
 def test_retry_skips_each_delivered_report_without_reads_or_send(self):
  for section in ('candidates','control'):
   pair=self.pair(section,date(2026,10,18));w=DailyWorkerTests().worker();w.day=pair.day;w.command=pair.command;w.update_id=pair.update_id;w.earliest=(10,30)
   w.now=datetime(2026,10,18,10,30,tzinfo=timezone(timedelta(hours=3)))
   def db(method,table,**kw):
    self.assertEqual(method,'GET')
    if table=='business_agent_config':return [{'agent_id':'china','chat_id':101,'owner_user_id':202}]
    if kw['params'].get('select')=='chat_id':return [{'chat_id':101}]
    return [{'id':33,'request_text':w.command,'chat_id':101,'sender_id':202,'status':'done','answer':'report','tool_trace':[{'name':'china_report_delivery','sent_parts':1}]}]
   w.db=db;w.prepare=lambda **kw:self.fail('Already delivered report must not collect')
   for _ in range(4):w.run();self.assertEqual(w.audit['status'],'already_delivered')
   self.assertEqual(w.audit['telegram_message_ids'],[])

if __name__=='__main__':unittest.main()
