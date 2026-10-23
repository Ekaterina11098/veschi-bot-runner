import copy,unittest
from china_advertising_normalize import normalize,arithmetic_drr
def fixture():
 rows=[dict(id=1,wb_id=2,campaign_name='A',status_id=9,create_date='2026-10-01 00:00:00')]
 metric=dict(id=1,wb_id=2,ac_spending_sum=10,ac_orders_sum=200,ac_orders=2,ac_orders_associated=1,ac_orders_sum_associated=100)
 def obs(tool,args,data):return dict(tool=tool,arguments=args,data=data,status='received',scope_verified=True,observed_at='2026-10-20T04:30:00+00:00')
 def catalog(report,a=None,b=None):
  args=dict(report=report,tokens=[939742])
  data=dict(data=copy.deepcopy(rows if report=='state' else [metric]),total=1,returned=1)
  if a:args.update(d1=a,d2=b);data['period']={'from':a,'to':b}
  return obs('wbbidder_campaigns',args,data)
 prod=dict(nm_id=3,ac_spending_sum=10,ac_orders_sum=100,ac_orders=1)
 observations=[catalog('state'),catalog('stats','2026-10-19','2026-10-19'),catalog('stats','2026-10-13','2026-10-19'),
 obs('wbbidder_campaign',dict(campaign_id=1),dict(campaign=dict(wb_id=2),budget=dict(budget=100,currency='CNY'))),
 obs('wbbidder_campaign_stats',dict(campaign_id=1,report='days',d1='2026-10-13',d2='2026-10-19'),dict(period={'from':'2026-10-13','to':'2026-10-19'},data=[dict(date='2026-10-19',ac_spending_sum=10)],returned=1)),
 obs('wbbidder_campaign_stats',dict(campaign_id=1,report='products',d1='2026-10-19',d2='2026-10-19'),dict(period={'from':'2026-10-19','to':'2026-10-19'},data=[prod],returned=1,totals=dict(ac_spending_sum=10)))]
 return dict(status='complete',cabinet='token_3',identity=dict(id=939742,info=dict(currency='CNY')),observations=observations)
class NormalizeTests(unittest.TestCase):
 def test_arithmetic_mean_available_days_not_weighted(self):
  rows=[dict(date='2026-10-17',ac_spending_sum=10,ac_orders_sum=100),dict(date='2026-10-18',ac_spending_sum=90,ac_orders_sum=300),dict(date='2026-10-19',ac_spending_sum=0,ac_orders_sum=100)]
  x=arithmetic_drr(rows,'2026-10-19');self.assertAlmostEqual(x['drr_mean_3d'],40/3);self.assertEqual(x['drr_mean_3d_count'],3)
  rows[1]['ac_orders_sum']=0
  x=arithmetic_drr(rows,'2026-10-19');self.assertEqual(x['drr_mean_3d'],5);self.assertEqual(x['drr_mean_3d_count'],2);self.assertEqual(x['drr_3d_no_orders_days'],1);self.assertEqual(x['drr_3d_no_orders_spend'],90)
 def test_archive_summary_fills_missing_row(self):
  x=arithmetic_drr([],'2026-10-19',[dict(date='2026-10-18',ac_spending_sum=20,ac_orders_sum=100)])
  self.assertEqual(x['drr_mean_3d'],20);self.assertEqual(x['drr_mean_3d_count'],1)
 def test_missing_duplicate_or_undefined_days(self):
  self.assertIsNone(arithmetic_drr([],'2026-10-19')['drr_mean_3d'])
  self.assertEqual(arithmetic_drr([dict(date='2026-10-19',ac_spending_sum=10)],'2026-10-19')['drr_mean_3d_count'],0)
  with self.assertRaises(ValueError):arithmetic_drr([{'date':'2026-10-19'},{'date':'2026-10-19'}],'2026-10-19')
 def test_campaign_postclick_not_added_again(self):
  b=normalize(fixture(),'2026-10-20',{'3':'SKU'})
  self.assertEqual(b['campaigns'][0]['drr'],5);self.assertEqual(b['campaigns'][0]['above5'][0]['drr'],10)
  self.assertEqual(b['total_day'],10);self.assertEqual(b['campaigns'][0]['balance_hours'],240)
 def test_zero_orders_not_zero_drr(self):
  p=fixture();p['observations'][1]['data']['data'][0]['ac_orders_sum']=0
  self.assertIsNone(normalize(p,'2026-10-20',{})['campaigns'][0]['drr'])
 def test_missing_money_not_zero(self):
  p=fixture();del p['observations'][1]['data']['data'][0]['ac_spending_sum']
  with self.assertRaises(ValueError):normalize(p,'2026-10-20',{})
 def test_wrong_cabinet_or_currency_blocked(self):
  p=fixture();p['identity']['info']['currency']='RUB'
  with self.assertRaises(ValueError):normalize(p,'2026-10-20',{})
 def test_partial_catalogue_blocked(self):
  p=fixture();p['observations'][0]['data']['total']=2
  with self.assertRaises(ValueError):normalize(p,'2026-10-20',{})
 def test_wrong_period_blocked(self):
  p=fixture();p['observations'][1]['data']['period']['from']='2026-10-18'
  with self.assertRaises(ValueError):normalize(p,'2026-10-20',{})
 def test_new_campaign_has_no_duration(self):
  p=fixture();p['observations'][0]['data']['data'][0]['create_date']='2026-10-20 00:00:00'
  c=normalize(p,'2026-10-20',{})['campaigns'][0]
  self.assertTrue(c['is_new']);self.assertIsNone(c['balance_hours'])
 def test_absent_budget_preserved_unknown(self):
  p=fixture();p['observations'][3]['data']['budget']=None
  c=normalize(p,'2026-10-20',{})['campaigns'][0]
  self.assertIsNone(c['balance']);self.assertIsNone(c['balance_hours'])
 def test_product_rounding_not_promoted_to_campaign_cost(self):
  p=fixture();p['observations'][5]['data']['data'][0]['ac_spending_sum']=11
  b=normalize(p,'2026-10-20',{})
  self.assertEqual(b['total_day'],10);self.assertEqual(b['campaigns'][0]['sku_spend_sum'],11)
if __name__=='__main__':unittest.main()
