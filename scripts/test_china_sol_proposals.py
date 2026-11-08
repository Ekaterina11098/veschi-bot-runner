import unittest
from unittest.mock import patch
from china_codex_cloud import envelope
from china_new_ad_reports import proposal_lines

class ProposalTests(unittest.TestCase):
 def test_model_can_queue_calculations_not_marketplace_actions(self):
  import json
  p=dict(kind='prepare_advertising',subject_ids=[50],nm_ids=[],maximum_count=20)
  self.assertEqual(envelope(json.dumps(p)),p)
  for bad in [dict(p,maximum_count=0),dict(p,subject_ids=[True]),dict(p,nm_ids=[1,1]),dict(p,execute=True),dict(p,maximum_count=100)]:
   with self.assertRaises(ValueError):envelope(json.dumps(bad))
 def test_preparation_completion_persists_only_calculation_request(self):
  import china_codex_cloud as cloud
  from test_china_codex_cloud import inbox,FakeDB,FakeWorker
  i=inbox();db=FakeDB(i)
  worker=FakeWorker(db,dict(kind='prepare_advertising',subject_ids=[50],nm_ids=[],maximum_count=20))
  self.assertEqual(worker.process(cloud.ROOT+'inbox:231',i),'ready')
  request=db.get('china_agent:new_ad_report_request:v1:231')
  self.assertEqual(request['subject_ids'],[50]);self.assertFalse(request['grants_action_permission'])
  self.assertEqual(request['reply_message_id'],i['input_message_id'])
  self.assertFalse(any('approval:' in k or 'execution:' in k for k in db.values))
 def test_visible_proposal_contains_actual_economics_and_campaign(self):
  camp=dict(name='Сумки тест',budget_cny=100,daily_limit_minor=10000)
  item=dict(nm_id=1,bid_minor=28)
  row=dict(article='Bag',subject_id=50,price_cny=200,paid=4,finished=10,stock=6,expected_rub_per_order=17.5,minimum_reference_campaign_id=40933588,economics_detail=dict(cogs_rub=850,delivery_cny=13))
  text='\n'.join(proposal_lines(camp,item,row,'2026-11-04 — 2026-11-07'))
  for fragment in ['Сумки тест','0.28','40933588','200.00 CNY','850.00 RUB','13.00 CNY','4/10','17.50 RUB','100 CNY','неизвестны']:
   self.assertIn(fragment,text)
  row['economics_detail']={}
  self.assertIn('COGS нет данных', '\n'.join(proposal_lines(camp,item,row,'полные дни')))
if __name__=='__main__':unittest.main()
