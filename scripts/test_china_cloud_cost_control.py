import copy, unittest
from datetime import timedelta
from unittest.mock import patch
import sys,types
try:import requests
except ModuleNotFoundError:sys.modules['requests']=types.SimpleNamespace(request=lambda *a,**k:None,post=lambda *a,**k:None,get=lambda *a,**k:None)
import china_cloud_cost_control as m
def counter(spend=0,clicks=0,orders=0,amount=0):return m.zero()|dict(spend=spend,clicks=clicks,orders=orders,amount=amount)
def campaign():
 return dict(id=1,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=False,recommendations=True)),nm_settings=[dict(nm_id=11,bids_kopecks=dict(search=0,recommendations=40)),dict(nm_id=12,bids_kopecks=dict(search=0,recommendations=28))])
class State:
 def __init__(self):self.data={m.POLICY:dict(status='active',cabinet='token_3',executor='github-cloud-v1',allowed=['decrease_bid_above_fresh_WB_minimum','exclude_underperforming_sku'],pause_authorized=False,expires_at=(m.now()+timedelta(days=1)).isoformat())};self.notices=[]
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.data:return False
  self.put(k,v);return True
 def notice(self,*x):self.notices.append(x)
class WB:
 def __init__(self,b,expected,fail=False):self.b=b;self.expected=expected;self.writes=0;self.reads=0;self.fail=fail
 def campaigns(self,ids):
  self.reads+=1
  return {'1':copy.deepcopy(self.expected if self.writes else self.b)}
 def req(self,*a,**kw):
  self.writes+=1
  if self.fail:raise TimeoutError()
  return {}
class Tests(unittest.TestCase):
 def test_shared_snapshot_contract(self):
  p=m.shared_payload(dict(slot='hour',observed_at='time',campaigns={'1':campaign()},stats=[dict(advertId=1)],budgets={}))
  self.assertEqual(p['ad_batches'][0]['data'][0]['advertId'],1)
 def test_ratio_of_sums_and_zero(self):
  self.assertIsNone(m.drr(counter(4)));self.assertEqual(m.drr(counter(20,orders=2,amount=400)),5)
 def test_negative_attribution_not_clamped(self):
  x=m.delta(counter(4,4,1,100),counter(5,5,2,200))
  self.assertEqual(x['orders'],-1);self.assertIsNone(m.risk(x,100,counter()))
 def test_no_order_threshold_with_volume(self):
  self.assertEqual(m.risk(counter(6,30),100,None),'no_orders')
  self.assertIsNone(m.risk(counter(4.99,100),100,None))
  self.assertIsNone(m.risk(counter(6,12),100,None))
 def test_two_distinct_slices(self):
  self.assertEqual(m.risk(counter(6,12),100,counter(5,10)),'no_orders')
 def test_improving_test_preserved(self):
  self.assertIsNone(m.risk(counter(20,60,5,300),100,counter(19,50,4,200)))
 def test_sustained_high_drr(self):
  self.assertEqual(m.risk(counter(30,90,2,300),100,counter(20,60,1,200)),'high_drr')
 def test_sum_apps_only(self):
  stats=[dict(advertId=1,sum=4,orders=2,sum_price=200,days=[dict(apps=[dict(nms=[dict(nmId=11,sum=1,orders=1,sum_price=100)]),dict(nms=[dict(nmId=11,sum=3,orders=1,sum_price=100)])])])]
  cc,ss=m.counts(stats);self.assertEqual(ss['1:11']['spend'],4);self.assertEqual(cc['1']['spend'],4)
 def test_reject_increases_and_unknown_actions(self):
  b=campaign()
  with self.assertRaises(AssertionError):m.expected_campaign(b,[dict(kind='lower',nm=11,target=50,placement='recommendations')])
  with self.assertRaises(ValueError):m.expected_campaign(b,[dict(kind='fund')])
 def test_exclusion_preserves_others(self):
  b=campaign();a=m.expected_campaign(b,[dict(kind='exclude',nm=11)])
  self.assertEqual(a['nm_settings'],[b['nm_settings'][1]]);self.assertEqual(b['nm_settings'][0]['bids_kopecks']['recommendations'],40)
 def test_empty_campaign_not_allowed(self):
  with self.assertRaises(AssertionError):m.expected_campaign(campaign(),[dict(kind='exclude',nm=11),dict(kind='exclude',nm=12)])
 def test_pause_retains_composition(self):
  b=campaign();a=m.expected_campaign(b,[dict(kind='pause')]);self.assertEqual(a['status'],11);self.assertEqual(a['nm_settings'],b['nm_settings'])
 def test_expiry(self):
  self.assertFalse(m.authorized(dict(status='active',cabinet='token_3',expires_at=(m.now()-timedelta(seconds=1)).isoformat()),m.now()))
 def test_single_write_verified_receipt(self):
  c=State();b=campaign();items=[dict(kind='lower',nm=11,article='A',old=40,target=28,placement='recommendations')];w=WB(b,m.expected_campaign(b,items))
  e=m.execute(c,w,'slot',b,items,dict(stats=[],observed_at=m.stamp()))
  self.assertEqual(e['status'],'verified');self.assertEqual(w.writes,1)
  m.execute(c,w,'slot',b,items,dict(stats=[],observed_at=m.stamp()));self.assertEqual(w.writes,1)
 def test_uncertain_never_repeated(self):
  c=State();b=campaign();items=[dict(kind='exclude',nm=11,article='A')];w=WB(b,m.expected_campaign(b,items),True)
  for i in range(2):
   with self.assertRaises(RuntimeError):m.execute(c,w,'slot',b,items,dict(stats=[],observed_at=m.stamp()))
  self.assertEqual(w.writes,1);self.assertTrue(c.get(m.ROOT+'inflight:v1')['key'])
 def test_funding_unknown_economics_no_send(self):
  with patch.object(m.requests,'post',side_effect=AssertionError('Must not send')):
   self.assertFalse(m.telegram_funding(State(),dict(telegram_budget_requests=dict(enabled=True)),'1',counter(1,orders=1,amount=100),1,100,'day',{}))
 def test_funding_no_orders_no_send(self):
  self.assertFalse(m.telegram_funding(State(),dict(telegram_budget_requests=dict(enabled=True)),'1',counter(10),1,100,'day',dict(all_costs_confirmed=True,expected_total_profit_cny=5)))
 def test_budget_endpoint_cannot_be_write(self):
  with self.assertRaises(ValueError):m.WB().req('/adv/v1/budget/deposit','POST',{},write=True)
 def test_pause_endpoint_cannot_be_read(self):
  with self.assertRaises(ValueError):m.WB().req('/adv/v0/pause?id=1')

 def test_pause_revoked_before_any_wb_write(self):
  c=State();b=campaign();items=[dict(kind='pause',nm=0,article='all')];w=WB(b,m.expected_campaign(b,items))
  with self.assertRaises(RuntimeError):m.execute(c,w,'slot',b,items,dict(stats=[],observed_at=m.stamp()))
  self.assertEqual(w.writes,0)
 def test_observed_hour_not_order_cohort(self):
  p=dict(last_observed_at='2026-10-25T22:10:00+00:00',previous_campaign_counters={'1':counter(10,20,2,100)},campaigns={'1':campaign()})
  s=dict(slot='hour',observed_at='2026-10-25T23:10:00+00:00',campaigns={'1':campaign()})
  v=m.observed_interval(p,s,{'1':counter(15,30,2,100)})
  self.assertEqual(v['phase'],'night_00_06');self.assertEqual(v['campaigns']['1']['delta']['orders'],0);self.assertFalse(v['automatic_actions_allowed'])
 def test_negative_hourly_revision_excluded_not_zeroed(self):
  p=dict(last_observed_at='2026-10-25T22:10:00+00:00',previous_campaign_counters={'1':counter(10,20,2,100)},campaigns={'1':campaign()})
  s=dict(slot='hour',observed_at='2026-10-25T23:10:00+00:00',campaigns={'1':campaign()})
  r=m.observed_interval(p,s,{'1':counter(15,30,1,50)})['campaigns']['1']
  self.assertEqual(r['delta']['orders'],-1);self.assertFalse(r['comparable'])
 def test_one_night_never_a_pattern(self):
  v=dict(msk_date='2026-10-26',duration_hours=1,phase='night_00_06',campaigns={'1':dict(delta=counter(30,100),comparable=True)})
  r=m.summarize_time([v])['1'];self.assertFalse(r['enough_repeated_observations']);self.assertFalse(r['hypothesis_for_owner_only'])
 def test_pattern_requires_repeated_equal_window_observation(self):
  intervals=[]
  for day in ['2026-10-26','2026-10-27']:
   for i in range(4):
    for phase,total in [('night_00_06',counter(10,30)),('day_12_18',counter(2,10,1,100))]:
     intervals.append(dict(msk_date=day,duration_hours=1,phase=phase,campaigns={'1':dict(delta=total,comparable=True)}))
  r=m.summarize_time(intervals)['1']
  self.assertTrue(r['hypothesis_for_owner_only']);self.assertIsNone(r['night']['drr_pct']);self.assertEqual(r['day']['drr_pct'],2)

if __name__=='__main__':unittest.main()
