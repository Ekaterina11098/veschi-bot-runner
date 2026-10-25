import unittest,copy
from datetime import datetime,date,timezone
from types import SimpleNamespace
from china_shared_advertising import shared
from china_analytic_dialog import Analyst
from china_experience import ROOT,put_event
class ReplayRegressions(unittest.TestCase):
 def fixture(self,missing=False):
  n=dict(nmId=1,sum=5,sum_price=100,orders=1,clicks=10,views=100,atbs=2)
  n2=dict(nmId=1,sum=3,sum_price=0,orders=0,clicks=6,views=50,atbs=4)
  if missing:n2.pop('atbs')
  d=dict(date='2026-10-25T00:00:00Z',sum=8,sum_price=100,orders=1,clicks=16,views=150,atbs=6,apps=[dict(nms=[n]),dict(nms=[n2])])
  base=dict(status='complete',period_from='2026-10-19',period_to='2026-10-24',observed_at='2026-10-25T10:00:00+00:00',batches={'0':dict(campaigns=dict(adverts=[dict(id=42,status=9,settings={},nm_settings=[dict(nm_id=1)])]),stats=[])})
  current=dict(observed_at='2026-10-25T17:00:00+00:00',ad_batches=[dict(data=[dict(advertId=42,days=[d])])])
  cache={'china_agent:advertising_source:2026-10-25:v2':base,'china_agent:advertising_intraday:2026-10-25:v1':current}
  return SimpleNamespace(now=datetime(2026,10,25,17,tzinfo=timezone.utc),get=lambda k:copy.deepcopy(cache.get(k)))
 def test_baskets_sum_apps_once(self):
  r=shared(self.fixture(),date(2026,10,25),date(2026,10,25),[1]);m=r['products']['1']['42']['2026-10-25']
  self.assertEqual(m['basket_events'],6);self.assertEqual(m['spend_cny'],8);self.assertEqual(m['orders'],1)
  self.assertEqual(r['totals_by_day']['2026-10-25']['spend_cny'],8);self.assertEqual(r['wb_reads'],0)
 def test_missing_baskets_are_unknown(self):
  r=shared(self.fixture(True),date(2026,10,25),date(2026,10,25),[1])
  self.assertIsNone(r['products']['1']['42']['2026-10-25']['basket_events'])
 def test_missing_profit_is_not_zero(self):
  w=SimpleNamespace(now=datetime(2026,10,25,tzinfo=timezone.utc),get=lambda k:None)
  r=Analyst(w,{},[]).profit('2026-10-24','2026-10-25')
  self.assertFalse(r['available']);self.assertNotIn('expected_rub',r)
 def test_saved_forecast_preserves_uncertainty(self):
  value=dict(status='available_preliminary',all_expenses_confirmed=False,is_closed_net_profit=False,summary=[dict(expected_rub=100)])
  w=SimpleNamespace(now=datetime(2026,10,25,tzinfo=timezone.utc),get=lambda k:copy.deepcopy(value))
  r=Analyst(w,{},[]).profit('2026-10-24','2026-10-25')
  self.assertEqual(r['summary'][0]['expected_rub'],100);self.assertFalse(r['is_closed_net_profit']);self.assertFalse(r['all_expenses_confirmed']);self.assertEqual(r['wb_reads'],0)
 def test_profit_future_date_rejected(self):
  w=SimpleNamespace(now=datetime(2026,10,25,tzinfo=timezone.utc),get=lambda k:None)
  with self.assertRaises(ValueError):Analyst(w,{},[]).profit('2026-10-25','2026-10-26')
 def test_prefetched_event_does_not_read_or_overwrite(self):
  original=dict(event_id='known',record_type='verified_action',source_key='receipt',business_outcome='negative')
  w=SimpleNamespace(_experience_prefetched={ROOT+'known':original},get=lambda k:(_ for _ in ()).throw(AssertionError('Unnecessary per-event read')))
  result=put_event(w,dict(original,business_outcome='pending'));self.assertEqual(result['business_outcome'],'negative')
 def test_new_event_is_added_to_prefetched_view(self):
  saved=[];w=SimpleNamespace(_experience_prefetched={},get=lambda k:None,save=lambda k,v:saved.append((k,v)))
  event=dict(event_id='new',record_type='verified_action',source_key='receipt')
  first=put_event(w,event);second=put_event(w,event)
  self.assertEqual(first,second);self.assertEqual(sum(k==ROOT+'new' for k,v in saved),1)

 def test_rating_comes_from_saved_source_with_unknown_review_count(self):
  source=dict(observed_at='2026-10-25T17:05:00+00:00',products=[dict(nm_id=1,sa_name='one-bag',commentsvaluation=5)])
  w=SimpleNamespace(now=datetime(2026,10,25,17,tzinfo=timezone.utc),catalog=lambda:[('1','one-bag')],get=lambda k:copy.deepcopy(source) if k.startswith('china_agent:new_ad_source:') else None)
  r=Analyst(w,{},[]).card_quality(['one-bag'])
  self.assertEqual(r['rows'][0]['rating'],5);self.assertIsNone(r['rows'][0]['review_count']);self.assertEqual(r['wb_reads'],0)
 def test_basket_followup_uses_advertising_not_general_product_funnel(self):
  w=self.fixture();w.catalog=lambda:[('1','one-bag')]
  r=Analyst(w,{},[]).baskets(['one-bag'],'2026-10-25','2026-10-25')
  self.assertEqual(r['products']['1']['42']['2026-10-25']['basket_events'],6);self.assertEqual(r['wb_reads'],0)
 def test_one_campaign_context_keeps_all_member_metrics(self):
  w=self.fixture();w.catalog=lambda:[('1','one-bag')]
  r=Analyst(w,{},[]).campaign(42,'2026-10-25','2026-10-25')
  self.assertEqual(r['articles']['1'],'one-bag');self.assertEqual(r['products']['1']['42']['2026-10-25']['spend_cny'],8)
 def test_execution_time_stays_separate_from_verification_time(self):
  from unittest.mock import patch
  source=dict(period_from='2026-09-25',period_to='2026-10-24',products=[dict(nm_id=1,sa_name='one-bag',is_payed=2,finished_orders=3)])
  prices=dict(observed_at='2026-10-25T15:00:00+00:00',rows=[dict(nmID=1,vendorCode='one-bag',sizes=[dict(discountedPrice=100)])])
  w=SimpleNamespace(now=datetime(2026,10,25,17,tzinfo=timezone.utc),catalog=lambda:[('1','one-bag')],get=lambda k:copy.deepcopy(prices if k=='china_agent:prices:v1' else source))
  event=dict(event_id='e',record_type='verified_action',action=dict(nm_ids=[1],kind='bid_change'),started_at='2026-10-23T10:00:00+00:00',verified_at='2026-10-23T16:00:00+00:00',comparison={})
  with patch('china_experience.search',return_value=dict(experiences=[event])):r=Analyst(w,{},[]).product_context(['one-bag'])
  c=r['rows'][0]['changes'][0]
  self.assertEqual(c['executed_at'],event['started_at']);self.assertEqual(c['verification_at'],event['verified_at'])
  self.assertEqual(r['rows'][0]['own_statistics_period'],['2026-09-25','2026-10-24'])


 def test_exact_period_product_snapshot_is_reused(self):
  from china_saved_products import saved_products
  product=dict(nm_id=1,sa_name='one-bag',finished_orders=2,is_payed=1)
  obs=dict(tool='lk_wb_products',status='received',scope_verified=True,arguments=dict(date_from='2026-10-24',date_to='2026-10-24'),data=dict(data=dict(data=[product],need_update=0,total=1)))
  w=SimpleNamespace(db=lambda *a,**kw:[dict(id=1,collected_at='2026-10-25T10:00:00+00:00',payload=[obs])])
  r=saved_products(w,date(2026,10,24),date(2026,10,24),[1])
  self.assertEqual(r['rows'][0]['buyout_pct'],50);self.assertEqual(r['wb_reads'],0);self.assertEqual(r['mpstats_reads'],0)
 def test_grounded_answer_keeps_sku_and_fx(self):
  from china_saved_products import ground_answer
  trace=[dict(name='get_saved_product_context',result=dict(rows=[dict(article='one-bag')])),dict(name='get_saved_profit_comparison',result=dict(assumptions=dict(fx_rub_per_cny=12,tax_pct=5,handling_rub_per_order=10)))]
  result=ground_answer('Предварительная оценка',trace)
  self.assertIn('one-bag',result);self.assertIn('12 ₽/¥',result);self.assertIn('допущения',result)

 def test_saved_profit_answer_does_not_trigger_fresh_orders(self):
  a=Analyst(SimpleNamespace(),{},[])
  a.cached_profit_context_supplied=True
  r=a.live('orders',[],'2026-10-24','2026-10-25')
  self.assertEqual(r['wb_reads'],0);self.assertTrue(r['cached_context_available']);self.assertFalse(r['available'])

if __name__=='__main__':unittest.main()
