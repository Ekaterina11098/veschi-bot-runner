"""Synthetic examples only; no live commercial fixtures or network."""
import copy,unittest
from datetime import date,datetime,timezone
from unittest.mock import patch
import china_change_observation as c

def event(kind='price_change',day='2026-01-10',eid='demo'):
 return dict(event_id=eid,record_type='verified_action',source_key='synthetic-receipt',started_at=day+'T12:00:00Z',action=dict(kind=kind,nm_ids=[1],article='DEMO',before=10,after=11,campaign_id=2),comparison=dict(days=3))
def raw(**kw):
 return dict(nm_id=1,api_id=10026946,sa_name='DEMO',order_dt='2026-01-09T12:00:00',gnumber='demo-ref',is_canceled_order=0,billed_times=0,refunded_times=0,backlogistic_times=0,retail_price_withdisc_rub=120,**kw)
def pair(value=100,orders=10,cr=10,sample=10,full=False):
 p=dict(value=value,method='expected_accounted_order_date_v2',buyout_sample=sample,all_expenses_confirmed=full,missing_costs=[] if full else ['unknown'])
 return dict(orders=orders,click_order_pct=cr,expected=p,actual=dict(value=None))
class ObservationTests(unittest.TestCase):
 def test_price_four_days_excludes_changed_and_today(self):
  w=c.window(event(),date(2026,1,14));self.assertEqual(w['days'],3);self.assertFalse(w['final']);self.assertEqual(w['after_to'],'2026-01-13');self.assertEqual(w['evaluate_from'],'2026-01-15')
  w=c.window(event(),date(2026,1,15));self.assertTrue(w['final']);self.assertEqual(w['before_from'],'2026-01-06');self.assertEqual(w['after_from'],'2026-01-11')
 def test_specific_ad_window_preserved(self):self.assertEqual(c.window(event('bid_change'),date(2026,1,14))['target_days'],3)
 def test_pending_is_not_refusal_and_zero_is_actual(self):
  rows=[raw(),raw(billed_times=1)] if False else [raw(),dict(raw(),is_canceled_order=1)]
  o,_=c.outcomes(rows,1,'DEMO','2026-01-09','2026-01-09');self.assertEqual(o['pending'],1);self.assertEqual(o['completed'],1);self.assertEqual(o['buyout_pct'],0)
 def test_gnumber_multiplicity_not_merged(self):
  o,_=c.outcomes([raw(),raw()],1,'DEMO','2026-01-09','2026-01-09');self.assertEqual(o['orders'],2)
 def test_only_srid_deduplicates(self):
  r=dict(raw(),srid='unique');o,_=c.outcomes([r,r],1,'DEMO','2026-01-09','2026-01-09');self.assertEqual(o['orders'],1)
 def test_return_not_kept_buyout(self):
  r=dict(raw(),billed_times=1,refunded_times=1);o,_=c.outcomes([r],1,'DEMO','2026-01-09','2026-01-09');self.assertEqual(o['returned'],1);self.assertEqual(o['paid'],0)
 def test_unknown_cost_is_not_closed_profit(self):self.assertIsNone(c.closed_profit(None,'a','b')['value'])
 def test_closed_ledger_rejects_missing_tax_and_duplicate_costs(self):
  p=dict(period_from='a',period_to='b',closed=True,reconciled=True,tax_confirmed=True,cogs_confirmed=True,all_logistics_confirmed=True,all_shared_costs_confirmed=True,advertising_reconciled=True,source_ids=['evidence'],expense_ids=['ad','ad'],currency='RUB',net_profit_rub=5)
  with self.assertRaises(ValueError):c.closed_profit(p,'a','b')
  p['expense_ids']=['ad'];self.assertEqual(c.closed_profit(p,'a','b')['value'],5)
  p['tax_confirmed']=False;self.assertIsNone(c.closed_profit(p,'a','b')['value'])
 def test_rollback_requires_profit_quality_and_final_window(self):
  w=dict(final=True,evaluate_from='2026-01-15');b=pair(100);a=pair(20,6,5)
  self.assertFalse(c.verdict(b,a,w,[],True)['rollback_recommended'])
  b['actual']=dict(value=100);a['actual']=dict(value=20)
  self.assertTrue(c.verdict(b,a,w,[],True)['rollback_recommended'])
  self.assertFalse(c.verdict(b,a,w,['another-change'],True)['rollback_recommended'])
  self.assertFalse(c.verdict(b,a,w,[],False)['rollback_recommended'])
  self.assertFalse(c.verdict(b,a,dict(w,final=False),[],True)['rollback_recommended'])
 def test_sample_and_no_orders_cannot_claim_earnings_growth(self):
  r=c.verdict(pair(-20),pair(0,0),dict(final=True),[],True);self.assertEqual(r['status'],'mixed')
  r=c.verdict(pair(100,sample=1,full=True),pair(0,1,sample=1,full=True),dict(final=True),[],True);self.assertFalse(r['rollback_recommended'])
 def test_expected_ad_cost_not_multiplied_by_buyout(self):
  own=dict(nm_id=1,finished_orders=10,is_payed=5,_period_advertising_rub=20)
  policy=dict(fx_rub_cny=12,handling_rub=1,tax_pct=0,commission_pct=20,logistics_by_nm={'1':dict(delivery_cny=1)})
  cohort=dict(completed=10,paid=5);one=c.expected([raw()],cohort,own,dict(price=100),policy)
  none=c.expected([raw()],cohort,dict(own,_period_advertising_rub=0),dict(price=100),policy)
  self.assertEqual(none['value']-one['value'],20);self.assertFalse(one['all_expenses_confirmed'])
 def test_fallback50_only_without_own_sample(self):
  own=dict(nm_id=1,finished_orders=1,is_payed=0,_period_advertising_rub=0);policy=dict(fx_rub_cny=12,handling_rub=1,tax_pct=0,commission_pct=20,logistics_by_nm={'1':dict(delivery_cny=1)})
  v=c.expected([raw()],dict(completed=0,paid=0),own,dict(price=100),policy);self.assertEqual(v['buyout_probability'],0)
  v=c.expected([raw()],dict(completed=0,paid=0),dict(own,finished_orders=0),dict(price=100),policy);self.assertEqual(v['buyout_probability'],.5)
 def test_reader_checks_order_filter_and_paginated_total(self):
  r=c.Reader(None);calls=[]
  def read(tool,args):
   calls.append(args);body=dict(data=[dict(raw(),n=i) for i in range(300)] if args['start_row']==0 else [raw()],total=301,filterModel=dict(product_id=dict(filter='55'),order_dt=dict(dateFrom='2026-01-09',dateTo='2026-01-09')))
   return dict(data=body),'key'
  r.read=read;rows,keys=r.table('lk_wb_card_orders',dict(type='products',value='55',date_from='2026-01-09',date_to='2026-01-09'),1)
  self.assertEqual(len(rows),301);self.assertEqual(calls[1]['start_row'],300)
 def test_no_informative_waiting_rows_in_daily_png(self):
  class W:
   def get(self,k):return {'event_ids':['demo']} if k==c.MANIFEST else {'window':{'final':False},'rows':[{}]} if k==c.ROOT+'demo' else {}
  self.assertEqual(c.compact(W()),[])
 def test_general_does_not_reuse_advertising_views(self):
  class W:
   def get(self,key):return None
  self.assertIsNone(c.general_traffic(W(),1,'a','b',dict(views=100))['total_impressions'])
 def test_total_does_not_double_count_ads_and_organic_requires_disjointness(self):
  class W:
   value=dict(cabinet='token_3',nm_id=1,period_from='a',period_to='b',source_id='synthetic-ui',semantics_verified=True,total_impressions=100,advertising_impressions=40,total_clicks=10)
   def get(self,key):return self.value
  w=W();v=c.general_traffic(w,1,'a','b',{});self.assertEqual(v['total_impressions'],100);self.assertIsNone(v['organic_impressions']);self.assertEqual(v['total_ctr_pct'],10)
  w.value=dict(w.value,components_disjoint=True,same_unit_and_period=True);self.assertEqual(c.general_traffic(w,1,'a','b',{})['organic_impressions'],60)
 def test_only_verified_disjoint_components_can_be_added(self):
  class W:
   value=dict(cabinet='token_3',nm_id=1,period_from='a',period_to='b',source_id='synthetic',semantics_verified=True,organic_impressions=60,advertising_impressions=40)
   def get(self,key):return self.value
  w=W();self.assertIsNone(c.general_traffic(w,1,'a','b',{})['total_impressions'])
  w.value=dict(w.value,components_disjoint=True,same_unit_and_period=True);self.assertEqual(c.general_traffic(w,1,'a','b',{})['total_impressions'],100)
 def test_ad_ctr_matches_ad_scope_and_empty_is_unknown(self):
  r=dict(nm_id=1,date='2026-01-01',views=100,clicks=10,orders=2,spend_cny=1)
  v=c.ad_funnel([r],1,'2026-01-01','2026-01-01');self.assertEqual(v['ctr_pct'],10);self.assertEqual(v['click_order_pct'],20)
  self.assertIsNone(c.ad_funnel([],1,'a','b')['views'])

if __name__=='__main__':unittest.main()

