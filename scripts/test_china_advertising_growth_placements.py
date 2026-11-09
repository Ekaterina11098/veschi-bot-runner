import copy,unittest
from unittest.mock import patch
from china_growth_placements import placement_candidates,addition_key
from china_advertising_full_growth import addition_actions

class PlacementTests(unittest.TestCase):
 def fixture(self):
  def cp(cid,zone,nm=9,subject=50):
   return dict(id=cid,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements={zone:True}),restrictions=dict(can_change_nms=True),nm_settings=[dict(nm_id=nm,subject=dict(id=subject))])
  e=dict(expected_margin_before_ads_cny=20,stock_free=10,published_stock=10,sample_size=10,buyout_fallback=False,commission_policy_fallback=False,seller_price_cny=100)
  v=dict(screened_nm_ids=[1],excluded_nm_ids=[],campaigns=[cp(10,'recommendations',1),cp(20,'search')],economics=dict(rows={'1':e}),own=dict(rows=[dict(nm_id=1,subject_id=50,is_payed=6,open_card_count=100,funnel_orders_count=5)],period_from='2026-10-10'),prices=dict(rows=[dict(nm_id=1,article='bag')]),observed_at='2026-11-09T13:00:00+00:00',budgets=dict(adverts=[dict(advertId=20,total=200)]),config=dict(cpcStep=1,cpcMaxBid=100))
  s=dict(period_to='2026-11-08',executions=[],full_growth_inputs=v,batches={'0':dict(stats=[dict(advertId=20,days=[dict(date='2026-11-08',sum=100)])])})
  return s,v,cp
 def candidates(self,s,v,changes=[]):
  with patch('china_advertising_v2.history',return_value=changes):return placement_candidates(s,v)
 def test_advertised_product_can_enter_absent_search_placement(self):
  s,v,_=self.fixture();self.assertEqual([dict(nm_id=1,campaign_id=20,placement='search',subject_id=50)],self.candidates(s,v))
 def test_category_mismatch_or_paused_target_is_rejected(self):
  s,v,_=self.fixture();v['campaigns'][1]['nm_settings'][0]['subject']['id']=136
  self.assertEqual([],self.candidates(s,v));v['campaigns'][1]['status']=11
  self.assertEqual([],self.candidates(s,v))
 def test_existing_paused_search_is_not_duplicated(self):
  s,v,cp=self.fixture();paused=cp(30,'search',1);paused['status']=11;v['campaigns'].append(paused)
  self.assertEqual([],self.candidates(s,v))
 def test_hold_removal_and_unfinished_change_day_are_rejected(self):
  s,v,_=self.fixture()
  for change in [dict(nm=1,kind='excluded',at='2026-10-20T00:00:00+00:00'),dict(nm=1,kind='bid',at='2026-11-08T00:00:00+00:00'),dict(nm=1,kind='price',at='2026-11-09T00:00:00+00:00')]:
   self.assertEqual([],self.candidates(s,v,[change]))
  v['excluded_nm_ids']=[1];self.assertEqual([],self.candidates(s,v))
 def test_unknown_stock_or_own_economics_cannot_be_ready(self):
  for key,val in [('published_stock',None),('stock_free',0),('expected_margin_before_ads_cny',-1),('buyout_fallback',True)]:
   s,v,_=self.fixture();v['economics']['rows']['1'][key]=val
   self.assertEqual([],self.candidates(s,v))
 def action_source(self):
  s,v,_=self.fixture();v['addition_candidates']=self.candidates(s,v);r=v['addition_candidates'][0]
  s['addition_bid_quotes']={addition_key(r):dict(campaign_id=20,placement='search',bid_verified=True,target_minor=28)}
  return s,v
 def test_exact_search_quote_is_kept_and_cpa_remains_unknown(self):
  s,v=self.action_source();a=addition_actions(s,[])
  self.assertEqual(1,len(a));self.assertEqual('search',a[0]['placement']);self.assertTrue(a[0]['growth_evidence']['ad_cpa_unknown'])
  self.assertTrue(a[0]['growth_evidence']['forecast_not_a_spend_cap'])
 def test_quote_from_other_campaign_cannot_leak(self):
  s,v=self.action_source();next(iter(s['addition_bid_quotes'].values()))['campaign_id']=99
  self.assertEqual([],addition_actions(s,[]))
 def test_three_day_reserve_includes_new_traffic_not_just_topup(self):
  s,v=self.action_source();v['budgets']['adverts'][0]['total']=100
  self.assertEqual([],addition_actions(s,[]))
 def test_raise_and_new_placement_cannot_compound_same_sku(self):
  s,v=self.action_source()
  a=dict(nm_id=1,campaign_id=20,old_minor=28,target_minor=30,growth_evidence=dict(metrics=dict(clicks=30),decision_days=['2026-11-08']))
  self.assertEqual([],addition_actions(s,[a]))

if __name__=='__main__':unittest.main()
