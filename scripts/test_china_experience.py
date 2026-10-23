import unittest,copy
from datetime import datetime,timezone,date,timedelta
from china_experience import compare_conditions, summarize_comparison, windows, assess_candidate, sync, put_event, observe, evaluate_saved, ROOT

class W:
 now=datetime(2026,10,27,10,tzinfo=timezone.utc)
 def __init__(self):self.data={}
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def save(self,k,v):self.data[k]=copy.deepcopy(v);return True
 def db(self,method,table,params):
  prefix=params['cache_key'][5:-1]
  return [dict(cache_key=k,payload=copy.deepcopy(v)) for k,v in self.data.items() if k.startswith(prefix)]

class ExperienceTests(unittest.TestCase):
 def test_unknown_is_not_unchanged(self):
  result=compare_conditions({}, {})
  self.assertIn('spp',result['unknown'])
  self.assertEqual(result['transferability'],'limited')
  self.assertEqual(result['algorithm_change'],'not_established')
 def test_changed_conditions_do_not_prove_algorithm_change(self):
  result=compare_conditions({'bid':.28,'customer_price':2000},{'bid':.31,'customer_price':2100})
  self.assertEqual(len(result['changes']),2)
  self.assertEqual(result['algorithm_change'],'not_established')
  self.assertTrue(result['repeat_requires_confirmation'])
 def test_missing_profit_is_not_zero(self):
  common=dict(days=3,period_complete=True,profit_method='expected',currency='RUB')
  self.assertEqual(summarize_comparison(dict(common,total_profit=None),dict(common,total_profit=100))['outcome'],'inconclusive')
 def test_both_positive_and_negative_experience(self):
  common=dict(days=3,period_complete=True,profit_method='expected',currency='RUB',orders=5)
  for before,after,outcome in [(10,20,'positive'),(20,10,'negative')]:
   result=summarize_comparison(dict(common,total_profit=before),dict(common,total_profit=after))
   self.assertEqual(result['outcome'],outcome)
   self.assertEqual(result['causality'],'not_established')
 def test_excludes_change_day(self):
  result=windows('2026-10-23T16:31:00+00:00')
  self.assertEqual(result['after_from'],'2026-10-24')
  self.assertEqual(result['evaluate_from'],'2026-10-27')
 def test_negative_experience_is_reviewed_not_permanently_banned(self):
  event=dict(event_id='previous',action=dict(nm_ids=[10]),business_outcome='negative',context=dict(seller_price=100))
  self.assertTrue(assess_candidate([event],10,dict(seller_price=100))['needs_review'])
  revised=assess_candidate([event],10,dict(seller_price=110))
  self.assertFalse(revised['needs_review']);self.assertTrue(revised['requires_confirmation'])
  self.assertTrue(revised['risks'])
 def test_import_bid_receipt_handles_non_campaign_before_fields(self):
  w=W();w.data['china_agent:codex_bid_raise:test:execution']=dict(status='verified',plan=dict(kind='ad_set_bid',nm_id=10,article='bag',campaign_id=1,old_minor=40,target_minor=42),before=dict(id=1,status=9,nm_settings=[]),after=dict(id=1,status=9,nm_settings=[]),submitted_at='2026-10-23T16:00:00Z',verified_at='2026-10-23T16:01:00Z')
  sync(w);event=next(v for k,v in w.data.items() if k.startswith(ROOT))
  self.assertEqual(event['action']['campaign_id'],1);self.assertEqual(event['action']['after'],42)
  self.assertEqual(event['business_outcome'],'pending')
 def test_saved_ad_result_does_not_invent_profit_or_causality(self):
  w=W();event=put_event(w,dict(event_id='x',record_type='verified_action',source_key='execution',started_at='2026-10-23T16:00:00Z',action=dict(nm_ids=[10],campaign_id=1),comparison=windows('2026-10-23T16:00:00Z')))
  for label,spend in [('before',1),('after',6)]:
   first=date.fromisoformat(event['comparison'][label+'_from'])
   for i in range(3):
    day=first+timedelta(days=i);w.data['china_agent:advertising_source:'+str(day+timedelta(days=1))+':v1']=dict(observations=[dict(tool='wbbidder_campaign',arguments=dict(campaign_id=7),data=dict(campaign=dict(wb_id=1))),dict(tool='wbbidder_campaign_stats',status='received',scope_verified=True,arguments=dict(campaign_id=7,report='products',d1=str(day),d2=str(day)),data=dict(data=[dict(nm_id=10,ac_spending_sum=spend,ac_orders_sum=100,ac_orders=1)]))])
  records={'x':event};evaluate_saved(w,['x'],records);updated=w.get(ROOT+'x')
  self.assertEqual(updated['advertising_outcome'],'negative');self.assertEqual(updated['business_outcome'],'inconclusive')
  self.assertIsNone(updated['observations'][0]['after']['total_profit']);self.assertEqual(updated['causality'],'not_established')
  evaluate_saved(w,['x'],records);self.assertEqual(len(w.get(ROOT+'x')['observations']),1)
 def test_reimport_does_not_overwrite_observed_outcomes(self):
  w=W();event=dict(event_id='x',record_type='reported_observation',source_key='facts',business_outcome='negative')
  put_event(w,event);put_event(w,dict(event,business_outcome='positive'))
  self.assertEqual(w.get(ROOT+'x')['business_outcome'],'negative')

if __name__=='__main__':unittest.main()

