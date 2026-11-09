import unittest,copy
from china_budget_ready_model import assess_campaign
DAYS=['2026-11-06','2026-11-07','2026-11-08'];AT='2026-11-09T07:00:00+00:00'
class ContinuationTests(unittest.TestCase):
 def setUp(self):
  self.state=dict(id=10,status=9,nm_settings=[{'nm_id':1}],timestamps={'started':'2026-10-20T07:00:00+00:00'})
  self.raw={'days':[dict(date=d,sum=10,orders=2,sum_price=200,clicks=30,apps=[{'nms':[{'nmId':1,'orders':2}]}])for d in DAYS]}
  self.e={'rows':{'1':dict(sample_size=20,buyout_fallback=False,expected_margin_before_ads_cny=40,buyout=.5,own_cogs_rub=100,seller_price_cny=200,fx_rub_per_cny=12,logistics_cny=10,commission_pct=20,observed_at=AT,price_observed_at=AT,stock_observed_at=AT,published_stock_observed_at=AT)}}
  self.changes=[dict(cid=10,nm=1,kind='bid',at='2026-11-09T06:00:00+00:00')]
 def assess(self):return assess_campaign(self.state,self.raw,self.e,{'rows':[]},self.changes,DAYS,AT)
 def test_waiting_for_outcome_does_not_starve_test(self):
  r=self.assess();self.assertTrue(r['ready']);self.assertEqual(r['evaluation_status'],'waiting');self.assertFalse(r['post_change_result_available']);self.assertEqual(r['metrics']['spend'],30)
 def test_brand_new_test_does_not_invent_full_reference_days(self):
  self.state['timestamps']['started']='2026-11-08T12:00:00+00:00';r=self.assess();self.assertFalse(r['ready']);self.assertEqual(r['status'],'unknown')
 def test_missing_reference_day_blocks_amount(self):
  self.raw['days'].pop();self.assertFalse(self.assess()['ready'])
 def test_missing_own_costs_not_zero(self):
  del self.e['rows']['1']['own_cogs_rub'];self.assertFalse(self.assess()['ready'])
 def test_negative_current_model_does_not_pass(self):
  self.e['rows']['1']['expected_margin_before_ads_cny']=-1;self.assertFalse(self.assess()['ready'])
 def test_negative_stress_does_not_pass_continuation(self):
  self.e['rows']['1']['expected_margin_before_ads_cny']=6;self.assertFalse(self.assess()['ready'])
 def test_matured_period_keeps_normal_outcome_basis(self):
  self.changes=[];r=self.assess();self.assertTrue(r['ready']);self.assertNotIn('evaluation_status',r)
 def test_no_orders_is_not_successful_model(self):
  for d in self.raw['days']:d.update(orders=0,sum_price=0,apps=[])
  self.assertFalse(self.assess()['ready'])
if __name__=='__main__':unittest.main()

