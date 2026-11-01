import copy,unittest
from china_morning_readiness import assess,ensure,PendingAdvertisingDay
def stats(spend=100,day='2026-10-31',views=100,clicks=10):return [dict(advertId=1,days=[dict(date=day,sum=spend,views=views,clicks=clicks)])]
def source(spend=100,views=100,clicks=10):return dict(ids=[1],batches={'0':dict(stats=stats(spend,views=views,clicks=clicks),campaigns={'keep':True},budgets={'keep':True})})
class IO:
 def __init__(self):self.mem={'china_agent:owner_profit_now:2026-10-31:v1:collection':dict(cabinet='token_3',inputs=dict(advertising=dict(rows=stats())))}
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def put(self,k,v):self.mem[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.mem:return False
  self.put(k,v);return True
class Quality(unittest.TestCase):
 def test_valid_day(self):self.assertTrue(assess(source(),'2026-10-31',[('prior',stats())])['usable'])
 def test_collapsed_midnight_counters_rejected(self):
  r=assess(source(0,0,0),'2026-10-31',[('prior',stats())]);self.assertFalse(r['usable']);self.assertEqual(r['regressed_campaigns'],[1])
 def test_true_zero_without_prior_positive_is_not_fabricated(self):self.assertTrue(assess(source(0,0,0),'2026-10-31',[])['usable'])
 def test_other_day_not_substituted(self):self.assertTrue(assess(source(0,0,0),'2026-10-31',[('prior',stats(day='2026-10-30'))])['usable'])
 def test_small_financial_revision_not_false_outage(self):self.assertTrue(assess(source(99),'2026-10-31',[('prior',stats())])['usable'])
 def test_missing_previously_spending_campaign_is_unknown(self):
  s=source();s['batches']['0']['stats']=[];self.assertFalse(assess(s,'2026-10-31',[('prior',stats())])['usable'])
 def test_retry_only_removes_invalid_stats_and_archives_raw(self):
  io=IO();s=source(0,0,0)
  with self.assertRaises(PendingAdvertisingDay):ensure(io,s,'2026-11-01','source')
  saved=io.get('source');self.assertEqual(saved['status'],'waiting_correct_daily_stats');self.assertNotIn('stats',saved['batches']['0']);self.assertTrue(saved['batches']['0']['campaigns']['keep']);self.assertTrue(saved['batches']['0']['budgets']['keep'])
  archived=[v for k,v in io.mem.items() if ':rejected:' in k];self.assertEqual(len(archived),1);self.assertEqual(archived[0]['stats']['0'][0]['days'][0]['sum'],0)
 def test_next_valid_scheduled_read_can_complete(self):
  io=IO();s=source(0,0,0)
  with self.assertRaises(PendingAdvertisingDay):ensure(io,s,'2026-11-01','source')
  s=io.get('source');s['batches']['0']['stats']=stats(110)
  self.assertTrue(ensure(io,s,'2026-11-01','source')['usable'])
 def test_no_previous_date_result_as_today(self):
  io=IO();io.mem['china_agent:owner_profit_now:2026-10-31:v1:collection']['cabinet']='token_1'
  self.assertTrue(ensure(io,source(0,0,0),'2026-11-01','source')['usable'])
class EconomicsRefresh(unittest.TestCase):
 def test_own_buyouts_current_seller_price_and_stock_refresh_without_per_sku_price_calls(self):
  from unittest.mock import patch
  from china_morning_readiness import enrich_economics
  io=IO();io.mem['china_agent:new_ad_economics_policy:v1']=dict(tax_pct=5,handling_rub=10,logistics_by_nm={'10':dict(delivery_cny=3)})
  s=dict(catalogue=dict(rows=[dict(nmID=10,vendorCode='bag')]))
  rough=dict(campaigns=[dict(focus=[dict(nm=10,period=dict(spend=20))])])
  calls=[]
  queries=[]
  io.db=lambda path:queries.append(path) or []
  def live(self,topic,ids,first,last):
   if topic=='products':self.w.db('GET','analytics_snapshots',params={'cabinet':'eq.token_3','period_from':'eq.'+first})
   calls.append((topic,ids,first,last))
   data={'products':[dict(nm_id=10,is_payed=10,finish_as_return=2,finished_orders=20,total_commission_without_spp_in_sales=20)],'prices':[dict(nm_id=10,article='bag',seller_price=100)],'stock':[dict(article='bag',cost_rub=120,available=8)]}
   return dict(observed_at='2026-11-01T04:15:00Z',rows=data[topic])
  price_input=dict(observed_at='2026-11-01T04:15:00Z',rows=[dict(nm_id=10,article='bag',seller_price=100)])
  with patch.dict('os.environ',dict(WB_TOKEN_3='fixture',MPSTATS_API_TOKEN='fixture',MOYSKLAD_API_TOKEN='fixture')),patch('china_analytic_dialog.Analyst.live',live),patch('china_analytic_dialog.Analyst.collect',lambda self,topic,ids,first,last:live(self,topic,ids,str(first),str(last))),patch('china_morning_readiness.current_prices',return_value=price_input) as prices_read,patch('china_intraday_analysis.rate',return_value=dict(rub_per_cny='12')):
   result=enrich_economics(io,s,rough,'2026-11-01')
  r=result['economics']['rows']['10']
  prices_read.assert_called_once_with(io,[10])
  self.assertEqual([c for c in calls if c[0]=='products'],[('products',[],'2026-10-02','2026-10-31')])
  self.assertEqual(r['stock_free'],8);self.assertEqual(r['sample_size'],20)
  self.assertAlmostEqual(r['expected_margin_before_ads_cny'],28.6666666667)
  self.assertTrue(r['unknown_reverse_and_shared_costs'])
  self.assertEqual(result['morning_fresh_inputs']['wb_writes'],0)
  self.assertEqual(queries,['analytics_snapshots?cabinet=eq.token_3&period_from=eq.2026-10-02'])
if __name__=='__main__':unittest.main()

