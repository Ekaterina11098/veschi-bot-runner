import copy,unittest
from unittest.mock import patch
from datetime import datetime
from china_budget_reserve import attach_completed_evidence,apply
from china_advertising_v2 import build

def source():
 c=dict(id=12,status=9,currency='CNY',settings=dict(name='Test',payment_type='cpc',placements=dict(search=True)),nm_settings=[dict(nm_id=1,bids_kopecks=dict(search=28))],timestamps=dict(created='2026-10-01T00:00:00+03:00'))
 days=[]
 for day,spend in [('28',100),('29',150),('30',250),('31',9999)]:
  n=dict(nmId=1,sum=spend,sum_price=1000,orders=5,views=100,clicks=10)
  days.append(dict(date='2026-10-'+day,**{k:v for k,v in n.items() if k!='nmId'},apps=[dict(nms=[n])]))
 e=dict(expected_total_profit_rub=123,period_from='2026-10-28',period_to='2026-10-30',basis='preliminary_model',source_ids=['own-fixture'],observed_at='2026-10-31T17:00:00Z',sample_size=4,preliminary=True,own_cogs_rub=490,seller_revenue_rub=1500)
 return dict(ids=[12],period_from='2026-10-24',period_to='2026-10-31',observed_at='2026-10-31T17:54:00Z',catalogue=dict(rows=[dict(nmID=1,vendorCode='test',price=126)]),executions=[],config=dict(minTopUp=10000),economics=dict(status='available',rows={'1':e}),batches={'0':dict(campaigns=dict(adverts=[c]),stats=[dict(advertId=12,days=days)],budgets=dict(adverts=[dict(advertId=12,total=120,currency='CNY')]))})

def result(s=None,**flags):
 b=build(s or source());b.update(flags);return apply(b)

class CompletedBudgetTests(unittest.TestCase):
 def test_evening_uses28to30_not29to31(self):
  b=result();c=b['campaigns'][0]
  self.assertEqual(b['days'],['2026-10-29','2026-10-30','2026-10-31'])
  self.assertEqual(b['budget_days'],['2026-10-28','2026-10-29','2026-10-30'])
  self.assertEqual(c['budget_reference_need'],500);self.assertEqual(c['budget_reserve_amount'],400)
  self.assertEqual(c['budget_average_daily'],500/3)
 def test_partial_day_spike_cannot_change_recommendation(self):
  s=source();a=result(s)['campaigns'][0]
  s['batches']['0']['stats'][0]['days'][-1].update(sum=0,sum_price=0,orders=0)
  b=result(s)['campaigns'][0]
  for k in ['budget_reference_need','budget_cash_gap','budget_reserve_amount','budget_short_note','budget_action']:self.assertEqual(a[k],b[k])
 def test_positive_small_model_does_not_override_owner_five_target(self):
  c=result()['campaigns'][0];self.assertGreater(c['budget_drr'],5)
  self.assertIsNone(c['budget_action']);self.assertIn('малая выборка',c['budget_short_note']);self.assertIn('Пока не пополнять',c['budget_short_note'])
 def test_positive_small_model_below5_can_propose_reserve(self):
  s=source()
  for d in s['batches']['0']['stats'][0]['days']:d['sum_price']=10000
  c=result(s)['campaigns'][0];self.assertLess(c['budget_drr'],5);self.assertIsNotNone(c['budget_action'])
 def test_unready_amount_is_recommendation_only_not_agreement(self):
  c=result()['campaigns'][0];f=c['budget_followup']
  self.assertEqual(f['status'],'recommendation_only');self.assertTrue(f['requires_fresh_review'])
  self.assertFalse(f['execution_authorized']);self.assertIsNone(c['budget_action'])
  self.assertNotIn('can_approve_amount_now',f);self.assertIn('Пока не пополнять',c['budget_short_note'])
 def test_profitable_campaign_cannot_hide_zero_order_member_spend(self):
  s=source();raw=s['batches']['0'];raw['campaigns']['adverts'][0]['nm_settings'].append(dict(nm_id=2,bids_kopecks=dict(search=28)))
  s['economics']['rows']['2']=copy.deepcopy(s['economics']['rows']['1'])
  s['catalogue']['rows'].append(dict(nmID=2,vendorCode='test2',price=126))
  for d in raw['stats'][0]['days']:
   d['sum_price']=100000;d['apps'][0]['nms'].append(dict(nmId=2,sum=10,sum_price=0,orders=0,views=20,clicks=2))
  c=result(s)['campaigns'][0];self.assertLess(c['budget_drr'],5);self.assertIsNone(c['budget_action']);self.assertIn('Пока не пополнять',c['budget_short_note'])
 def test_low_drr_not_profit_proof(self):
  s=source();s['economics']={}
  for d in s['batches']['0']['stats'][0]['days']:d['sum_price']=100000
  c=result(s)['campaigns'][0]
  self.assertIsNone(c['budget_action']);self.assertEqual(c['budget_reserve_amount'],400);self.assertEqual(c['budget_economics_status'],'unknown')
 def test_negative_model_requests_review_not_automatic_refusal(self):
  s=source();s['economics']['rows']['1']['expected_total_profit_rub']=-10
  c=result(s)['campaigns'][0];self.assertIsNone(c['budget_action']);self.assertIn('Проверить выборку',c['budget_short_note'])
 def test_missing_campaign_not_zero(self):
  s=source();s['batches']['0']['stats']=[]
  c=result(s)['campaigns'][0];self.assertIsNone(c['budget_reference_need']);self.assertTrue(c['budget_review_required'])
 def test_missing_amount_not_zero(self):
  s=source();del s['batches']['0']['stats'][0]['days'][0]['sum_price']
  with self.assertRaises(ValueError):result(s)
 def test_zero_orders_drr_undefined_but_test_can_be_reviewed(self):
  s=source()
  for d in s['batches']['0']['stats'][0]['days']:d['sum_price']=0;d['orders']=0
  c=result(s)['campaigns'][0];self.assertIsNone(c['budget_drr']);self.assertIn('не определена',c['budget_short_note'])
  self.assertIsNone(c['budget_action']);self.assertIn('Пока не пополнять',c['budget_short_note'])
 def test_same_day_verified_change_waits(self):
  s=source();s['batches']['0']['campaigns']['adverts'][0]['timestamps']['started']='2026-10-31T10:00:00+03:00'
  c=result(s)['campaigns'][0];self.assertEqual(c['budget_economics_status'],'waiting');self.assertIsNone(c['budget_action'])
 def test_mixed_change_day_economics_not_used(self):
  s=source();s['batches']['0']['campaigns']['adverts'][0]['timestamps']['started']='2026-10-29T10:00:00+03:00'
  c=result(s)['campaigns'][0];self.assertEqual(c['budget_economics_status'],'unknown')
 def test_today_model_is_not_completed(self):
  s=source();s['economics']['rows']['1']['period_to']='2026-10-31'
  self.assertEqual(result(s)['campaigns'][0]['budget_economics_status'],'unknown')
 def test_stale_own_economics_and_balance(self):
  s=source();s['economics']['rows']['1']['observed_at']='2026-10-22T10:00:00Z'
  self.assertEqual(result(s)['campaigns'][0]['budget_economics_status'],'unknown')
  s=source();s['budget_balance_observed_at_iso']='2026-10-31T10:00:00Z'
  self.assertIsNone(result(s)['campaigns'][0]['budget_reference_need'])
 def test_view_only_never_reintroduces_actions(self):
  c=result(view_only=True)['campaigns'][0];self.assertIsNone(c['budget_action']);self.assertEqual(c['budget_reserve_amount'],400)
 def test_incomplete_coverage_and_legacy_bundle_fail_explicitly(self):
  s=source();s['period_from']='2026-10-29'
  self.assertIsNone(result(s)['campaigns'][0]['budget_reference_need'])
  b=build(source());b.pop('budget_days');self.assertIsNone(apply(b)['campaigns'][0]['budget_reference_need'])
 def test_msk_midnight_closes_day(self):
  s=source();s['observed_at']='2026-10-31T21:01:00Z'
  self.assertEqual(result(s)['budget_days'][-1],'2026-10-31')
 def test_input_not_mutated(self):
  s=source();original=copy.deepcopy(s);result(s);self.assertEqual(s,original)
 def test_render_keeps_completed_header_and_no_view_actions(self):
  from china_advertising_v2_png import render
  b=result(view_only=True);b['intraday']=True
  parts=render(b);self.assertTrue(any(f['family']=='budgets' for f in parts))
  self.assertTrue(all(not f['actions'] for f in parts if f['family']=='budgets'))

if __name__=='__main__':unittest.main()


