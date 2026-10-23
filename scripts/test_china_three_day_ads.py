import unittest,copy
from china_three_day_ads import build,periods
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
if __name__=='__main__':unittest.main()
