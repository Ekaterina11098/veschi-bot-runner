import unittest
from china_midday_completed_review import merge_completed
from china_advertising_midday import only_completed_day_actions,recommendations
class CompletedMidday(unittest.TestCase):
 def test_new_placement_carries_completed_own_economics_without_fake_ad_cpa(self):
  r=self.review();row=r['campaigns'][0]['focus'][0]
  row.update(period=None,action=dict(kind='ad_add_sku',nm_id=2,growth_evidence=dict(period_from='2026-10-01',period_to='2026-10-31',ad_cpa_unknown=True)))
  out=merge_completed(dict(day='2026-11-01',campaigns=[dict(id=1)]),r,'source')
  a=out['campaigns'][0]['attention'][0]
  self.assertIsNone(a['spend']);self.assertIsNone(a['closed_day_evidence']['metrics']);self.assertTrue(a['closed_day_evidence']['ad_cpa_unknown'])
 def review(self):
  return dict(days=['2026-10-31'],campaigns=[dict(id=1,focus=[dict(nm=2,article='Bag',period=dict(spend=10,clicks=50,orders=2,amount=100),decision='Снизить 0,34 → 0,28',action=dict(kind='ad_set_bid',nm_id=2))])])
 def test_completed_recommendation_survives_filter_with_real_order_count(self):
  b=dict(day='2026-11-01',campaigns=[dict(id=1,attention=[])])
  out=only_completed_day_actions(merge_completed(b,self.review(),'private_closed_source'))
  self.assertEqual(1,len(out['campaigns'][0]['attention']))
  text=recommendations(out['campaigns'][0])[0];self.assertEqual('Bag: Снизить 0,34 → 0,28',text);self.assertEqual(2,out['campaigns'][0]['attention'][0]['closed_day_evidence']['metrics']['orders'])
 def test_incomplete_day_cannot_become_action_evidence(self):
  r=self.review();r['days']=['2026-11-01']
  with self.assertRaises(ValueError):merge_completed(dict(day='2026-11-01',campaigns=[dict(id=1)]),r,'source')
 def test_pending_history_remains_private_and_not_recommended(self):
  r=self.review();r['campaigns'][0]['focus'][0].update(pending_first_day=True,done='Ставка снижена · 01.11')
  out=merge_completed(dict(day='2026-11-01',campaigns=[dict(id=1)]),r,'source')
  self.assertEqual([],out['campaigns'][0]['attention']);self.assertEqual(['Нет новых действий.'],recommendations(out['campaigns'][0]));self.assertTrue(out['campaigns'][0]['completed_actions'])
 def test_old_midday_source_is_archived_and_recollected(self):
  import copy
  from datetime import datetime,timedelta,timezone
  from unittest.mock import patch
  import china_advertising_v2 as v
  day=str(datetime.now(v.MSK).date());key='china_agent:advertising_midday_source:'+day+':v2'
  class IO:
   def __init__(self,age):
    self.d={v.FORMAT:dict(status='approved',version=v.VERSION),key:dict(status='complete',period_from=day,period_to=day,observed_at=(datetime.now(timezone.utc)-timedelta(minutes=age)).isoformat(),batches={})}
   def get(self,k):return self.d.get(k)
   def create(self,k,x):self.d[k]=copy.deepcopy(x);return True
   def put(self,k,x):self.d[k]=copy.deepcopy(x)
  fresh=IO(1)
  with patch.object(v,'http',side_effect=AssertionError('Unexpected request')):
   self.assertEqual('complete',v.collect(fresh,day,current=True)['status'])
  stale=IO(3)
  with patch.object(v,'http',side_effect=RuntimeError('fresh collection requested')):
   with self.assertRaisesRegex(RuntimeError,'fresh collection requested'):v.collect(stale,day,current=True)
  archives=[x for k,x in stale.d.items()if ':rejected_stale:'in k]
  self.assertEqual(1,len(archives));self.assertEqual('complete',archives[0]['status'])
  self.assertEqual('collecting',stale.d[key]['status'])
 def test_all_four_directions_and_unready_addition_do_not_become_execution(self):
  r=self.review()
  r['recommendation_directions']={k:dict(status='checked',count=0,rows=[])for k in ['raise','add','reduce','exclude']}
  r['recommendation_directions']['add']['rows']=[dict(campaign_id=1,article='Other',bid_verified=True,ready=False)]
  out=merge_completed(dict(day='2026-11-01',campaigns=[dict(id=1)]),r,'source')
  self.assertEqual(4,len(out['recommendation_directions']))
  self.assertEqual(1,len(out['campaigns'][0]['attention']))
  self.assertIn('отдельный точный план',recommendations(out['campaigns'][0])[-1])

if __name__=='__main__':unittest.main()


