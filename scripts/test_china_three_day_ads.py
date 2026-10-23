import unittest,copy
from china_three_day_ads import build,periods,requested_days
def source(day,rows):
 obs=[dict(tool='wbbidder_campaigns',status='received',scope_verified=True,arguments=dict(report='state',tokens=[939742]),data=dict(total=1,returned=1,data=[dict(id=1,wb_id=100)])),
 dict(tool='wbbidder_campaign_stats',status='received',scope_verified=True,arguments=dict(campaign_id=1,report='products',d1=day,d2=day),data=dict(period=dict(from_=day),returned=len(rows),data=rows))]
 obs[1]['data']['period']={'from':day,'to':day}
 return dict(status='complete',cabinet='token_3',identity=dict(id=939742,info=dict(currency='CNY')),observations=obs)
def row(spend,orders,amount):return dict(nm_id=1,ac_spending_sum=spend,ac_orders=orders,ac_orders_sum=amount)
def fixture():
 return [source(d,[row(*v)]) for d,v in zip(periods('2026-10-23'),[(10,2,100),(20,1,50),(30,3,300)])]
class ThreeDays(unittest.TestCase):
 def test_dates_exclude_today(self):self.assertEqual(periods('2026-10-23'),['2026-10-20','2026-10-21','2026-10-22'])
 def test_weighted_cost_and_drr(self):
  r=build(fixture(),'2026-10-23')['rows'][0]
  self.assertEqual([v['cpa'] for v in r['daily']],[5,20,10])
  self.assertEqual(r['cpa'],10);self.assertAlmostEqual(r['drr'],100*60/450)
  self.assertEqual(r['cpa_first_last_percent'],100)
  self.assertEqual(r['cpa_latest_percent'],-50)
 def test_zero_orders_undefined(self):
  s=[source(d,[row(10,0,0)]) for d in periods('2026-10-23')]
  r=build(s,'2026-10-23')['rows'][0];self.assertIsNone(r['cpa']);self.assertIsNone(r['drr']);self.assertIsNone(r['cpa_first_last_percent'])
 def test_missing_day_is_not_zero(self):
  with self.assertRaises(ValueError):build(fixture()[:2],'2026-10-23')
 def test_wrong_date_rejected(self):
  s=fixture();s[0]['observations'][1]['data']['period']['from']='2026-10-19'
  with self.assertRaises(ValueError):build(s,'2026-10-23')
 def test_pagination_rejected(self):
  s=fixture();s[0]['observations'][1]['data']['returned']=2
  with self.assertRaises(ValueError):build(s,'2026-10-23')
 def test_other_cabinet_rejected(self):
  s=fixture();s[0]['identity']['id']=1
  with self.assertRaises(ValueError):build(s,'2026-10-23')
 def test_postclick_not_added(self):
  s=fixture()
  for p in s:p['observations'][1]['data']['data'][0]['ac_orders_associated']=100
  self.assertEqual(build(s,'2026-10-23')['rows'][0]['orders'],6)
 def test_consecutive_growth_required(self):
  r=build(fixture(),'2026-10-23')['rows'][0]
  self.assertFalse(r['rising_all_days'])
  s=[source(d,[row(v,1,100)]) for d,v in zip(periods('2026-10-23'),[5,10,20])]
  self.assertTrue(build(s,'2026-10-23')['rows'][0]['rising_all_days'])
 def test_flat_or_missing_point_not_trend(self):
  for costs in ([5,5,20],[5,10,10]):
   s=[source(d,[row(v,1,100)]) for d,v in zip(periods('2026-10-23'),costs)]
   self.assertFalse(build(s,'2026-10-23')['rows'][0]['rising_all_days'])
  s=fixture();s[1]=source('2026-10-21',[row(10,0,0)])
  self.assertFalse(build(s,'2026-10-23')['rows'][0]['rising_all_days'])
class SelectedPeriods(unittest.TestCase):
 def test_requested_count_precedence(self):
  self.assertEqual(requested_days('За 5 полных дней',[{'request_text':'За 3 дня'}]),5)
  self.assertEqual(requested_days('Давай',[{'request_text':'За 7 дней'}]),7)
  self.assertEqual(requested_days('За неделю'),7)
 def test_variable_dates_and_strict_growth(self):
  for n in (2,5,7):
   days=periods('2026-10-23',n)
   self.assertEqual(len(days),n);self.assertEqual(days[-1],'2026-10-22')
   sources=[source(d,[row(i+1,1,100)]) for i,d in enumerate(days)]
   r=build(sources,'2026-10-23',count=n)['rows'][0]
   self.assertTrue(r['rising_all_days']);self.assertEqual(r['orders'],n)
   if n>2:
    sources[1]=source(days[1],[row(1,1,100)])
    self.assertFalse(build(sources,'2026-10-23',count=n)['rows'][0]['rising_all_days'])
 def test_invalid_count(self):
  for n in (0,1,-3,91,True):
   with self.assertRaises(ValueError):periods('2026-10-23',n)
if __name__=='__main__':unittest.main()
