import copy,json,unittest
from datetime import datetime,timezone,timedelta
from china_article_diagnostic import evaluate,aggregate,render,scope,requested
NOW=datetime(2026,10,28,18,tzinfo=timezone.utc)
def fact():
 return dict(nm_id=100,article='test-bag',history_checked=True,gaps=[],changes=[],
  stock=dict(observed_at=NOW.isoformat(),available=10,cogs_cny=50),
  price=dict(observed_at=NOW.isoformat(),currency='CNY',seller_cny=500),
  campaign=dict(observed_at=NOW.isoformat(),id=40000001,status=9,currency='CNY',payment_type='cpc',placement='recommendations',bid_minor=28,minimum_minor=28,step_minor=1,maximum_minor=500,budget_cny=100),
  quality=dict(observed_at=NOW.isoformat(),rating=4.8,review_count=20),
  visibility=dict(observed_at=NOW.isoformat(),orderable=True,search_or_ad_rank_verified=False),
  economy=dict(buyout=.8,commission_pct=20,logistics_cny=10,tax_pct=5,handling_cny=10/12),
  daily=[dict(date=d,views=0,clicks=0,baskets=0,orders=0,spend=0,amount=0) for d in ['2026-10-25','2026-10-26','2026-10-27']])
class CoreTests(unittest.TestCase):
 def test_zero_traffic_can_have_a_positive_preliminary_test_not_low_drr(self):
  r=evaluate(fact(),NOW);self.assertEqual(r['stage'],'limited_traffic_test');self.assertEqual(r['action']['target_minor'],31);self.assertIsNone(r['traffic']['drr_pct']);self.assertFalse(r['execution_authorized']);self.assertEqual(r['wb_writes'],0)
 def test_requested_percent_preserved(self):self.assertEqual(evaluate(fact(),NOW,raise_percent=30)['action']['target_minor'],37)
 def test_unknown_not_zero_or_completed(self):
  for kind in ['daily','bid','reserve','price','logistics','buyout','reviews','history']:
   with self.subTest(kind=kind):
    f=fact()
    if kind=='daily':f['daily'].pop()
    if kind=='bid':f['campaign'].pop('bid_minor')
    if kind=='reserve':f['stock']['available']=None
    if kind=='price':f['price']['seller_cny']=None
    if kind=='logistics':f['economy']['logistics_cny']=None
    if kind=='buyout':f['economy']['buyout']=None
    if kind=='reviews':f['quality'].update(rating=0,review_count=None)
    if kind=='history':f['history_checked']=False
    r=evaluate(f,NOW);self.assertEqual(r['recommendation'],'Нет');self.assertIsNone(r['action'])
 def test_missing_app_metric_not_zero(self):
  f=fact();f['daily'][0]['clicks']=None;r=evaluate(f,NOW);self.assertIsNone(r['traffic']['clicks']);self.assertEqual(r['stage'],'incomplete')
 def test_drr_ratio_of_sums_not_mean_and_zero_orders_not_zero_percent(self):
  ds=[dict(views=10,clicks=1,baskets=1,orders=1,spend=10,amount=100),dict(views=10,clicks=1,baskets=0,orders=1,spend=1,amount=100)]
  self.assertEqual(aggregate(ds)['drr_pct'],5.5);ds[1]['amount']=0;ds[1]['orders']=0;self.assertEqual(aggregate(ds)['drr_pct'],11)
  self.assertIsNone(aggregate([dict(views=1,clicks=0,baskets=0,orders=0,spend=0,amount=0)])['drr_pct'])
 def test_today_high_drr_is_observation_not_candidate_rejection(self):
  f=fact();f['today_observation']=dict(date='2026-10-28',counters=dict(spend=1000,orders=0,amount=0));self.assertEqual(evaluate(f,NOW)['stage'],'limited_traffic_test')
 def test_zero_spend_does_not_mean_no_impressions(self):
  f=fact()
  for x in f['daily']:x['views']=100
  r=evaluate(f,NOW);self.assertEqual(r['stage'],'impressions_without_clicks');self.assertEqual(r['traffic']['views'],300)
 def test_clicks_baskets_and_orders_have_distinct_stages(self):
  for baskets,orders,expected in [(0,0,'clicks_without_baskets'),(1,0,'baskets_without_orders'),(1,1,'orders')]:
   f=fact()
   for x in f['daily']:x.update(views=100,clicks=10,baskets=baskets,orders=orders,spend=1,amount=100 if orders else 0)
   self.assertEqual(evaluate(f,NOW)['stage'],expected)
 def test_stockout_reserved_inactive_budget_and_unorderable_are_specific(self):
  for field,value,stage in [('stock',dict(available=0),'stockout'),('campaign',dict(status=11),'inactive_campaign'),('campaign',dict(budget_cny=0),'empty_budget'),('visibility',dict(orderable=False),'unorderable')]:
   f=fact();f[field].update(value);r=evaluate(f,NOW);self.assertEqual(r['stage'],stage);self.assertEqual(r['recommendation'],'Нет')
 def test_no_reviews_is_not_a_bad_rating(self):
  f=fact();f['quality'].update(rating=None,review_count=0);self.assertEqual(evaluate(f,NOW)['stage'],'limited_traffic_test')
 def test_low_rating_is_not_asserted_as_the_proven_cause(self):
  f=fact();f['quality']['rating']=3.3;r=evaluate(f,NOW);self.assertEqual(r['stage'],'low_rating');self.assertIn('не доказанная причина',r['reason'])
 def test_stale_data_does_not_pass(self):
  for source in ['stock','price','campaign','quality','visibility']:
   f=fact();f[source]['observed_at']=(NOW-timedelta(days=2)).isoformat();self.assertIsNone(evaluate(f,NOW)['action'])
 def test_no_repeated_raise_even_in_other_campaign(self):
  f=fact();f['changes']=[dict(kind='bid',cid=40000002,nm=100,verified=True,at=NOW.isoformat())];r=evaluate(f,NOW);self.assertEqual(r['stage'],'observe_change');self.assertEqual(r['review_from'],'2026-10-30')
 def test_full_next_day_after_price_change_not_current_or_change_day(self):
  f=fact();f['changes']=[dict(kind='price',verified=True,at='2026-10-27T09:00:00Z')];self.assertEqual(evaluate(f,NOW)['stage'],'observe_change')
  f['changes'][0]['at']='2026-10-26T09:00:00Z';r=evaluate(f,NOW);self.assertEqual(r['eligible_dates'],['2026-10-27'])
 def test_negative_attribution_revision_is_unknown_not_negative_sales(self):
  f=fact();f['daily'][0]['orders']=-1;self.assertIsNone(evaluate(f,NOW)['traffic']['orders'])
 def test_minimum_cannot_silently_enlarge_requested_raise(self):
  f=fact();f['campaign']['minimum_minor']=40;self.assertEqual(evaluate(f,NOW)['stage'],'bid_limit')
 def test_both_currency_and_actual_unit_cost_matter(self):
  f=fact();f['price']['currency']='RUB';self.assertIsNone(evaluate(f,NOW)['action'])
  f=fact();f['stock']['cogs_cny']=490;self.assertEqual(evaluate(f,NOW)['stage'],'economics_limit')
 def test_scenarios_are_explicitly_not_measured_forecast(self):
  r=evaluate(fact(),NOW);self.assertTrue(r['economics']['scenario_not_measured_forecast']);self.assertEqual([x['click_order_pct'] for x in r['economics']['scenarios']],[1,2,3])
 def test_none_column_is_exactly_none_without_owner_research_tasks(self):
  f=fact();f['stock']['available']=0;r=evaluate(f,NOW);text=render(dict(rows=[r,r],period_from='2026-10-25',period_to='2026-10-27'))
  self.assertEqual(text.count('| Нет |'),2);self.assertNotIn('проверьте',text);self.assertNotIn('получить тариф',text)
class ScopeTests(unittest.TestCase):
 def worker(self):
  class W:
   def catalog(self):return [('100','test-bag'),('101','other-bag')]
  return W()
 def test_latest_topic_not_all_history(self):
  h=[dict(id=1,request_text='test-bag нет показов'),dict(id=2,request_text='other-bag нет показов')]
  self.assertEqual(scope(self.worker(),dict(request_text='Что можем сделать?'),h),[101])
 def test_reply_parent_beats_latest_topic(self):
  j=dict(request_text='Что можем сделать?',tool_trace=[dict(name='china_saved_question',parent_job_id=1)])
  self.assertEqual(scope(self.worker(),j,[dict(id=1,request_text='test-bag'),dict(id=2,request_text='other-bag')]),[100])
 def test_unknown_explicit_sku_never_inherits_old_one(self):
  self.assertEqual(scope(self.worker(),dict(request_text='777-unknown-bag нет показов'),[dict(request_text='test-bag')]),[])
 def test_action_commands_and_raw_counts_are_not_analysis(self):
  for text in ['Делай','Согласен. Делай','Подними цены на 5%','Подними ставки на 30%','Сколько продаж test-bag?','Когда меняли цену?','Следи за test-bag','Спасибо']:
   self.assertFalse(requested(text),text)
if __name__=='__main__':unittest.main()
