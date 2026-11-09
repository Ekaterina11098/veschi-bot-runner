import copy,unittest
from china_budget_ready_model import assess_campaign
from china_budget_reserve import apply
OBS='2026-11-04T05:35:00+00:00'
DAYS=['2026-11-01','2026-11-02','2026-11-03']
def fixture(margin=40,spend=10):
 state=dict(id=7,status=9,timestamps=dict(started='2026-10-20T00:00:00+03:00'),nm_settings=[dict(nm_id=1)])
 raw=dict(advertId=7,days=[dict(date=d+'T00:00:00Z',sum=spend,orders=1,sum_price=100,clicks=20,apps=[dict(nms=[dict(nmId=1,orders=1)])])for d in DAYS])
 e=dict(observed_at=OBS,price_observed_at=OBS,stock_observed_at=OBS,published_stock_observed_at=OBS,sample_size=10,buyout_fallback=False,buyout=.5,own_cogs_rub=100,seller_price_cny=100,fx_rub_per_cny=10,logistics_cny=5,commission_pct=20,expected_margin_before_ads_cny=margin)
 return state,raw,dict(rows={'1':e}),dict(rows=[dict(nm_id=1)]),[]
class CampaignBudgetTests(unittest.TestCase):
 def evaluate(self,*data):return assess_campaign(*data,DAYS,OBS)
 def test_positive_campaign_not_blocked_by_one_zero_direct_order_member(self):
  m=self.evaluate(*fixture())
  c=dict(id=7,status=9,balance=0,budget_period=dict(spend=30,orders=3,amount=300),budget_members=[dict(nm=1,completed_traffic=dict(spend=20,orders=3)),dict(nm=2,completed_traffic=dict(spend=10,orders=0))],campaign_budget_economics=m)
  b=apply(dict(campaigns=[c],budget_days=DAYS,budget_observed_at=OBS,budget_balance_observed_at_iso=OBS))
  self.assertEqual(b['campaigns'][0]['budget_action']['kind'],'topup_campaign')
 def test_above_target_drr_is_not_a_break_even_gate(self):
  m=self.evaluate(*fixture(spend=20))
  c=dict(id=7,status=9,balance=0,budget_period=dict(spend=60,orders=3,amount=300),budget_members=[dict(nm=1)],campaign_budget_economics=m)
  b=apply(dict(campaigns=[c],budget_days=DAYS,budget_observed_at=OBS,budget_balance_observed_at_iso=OBS))
  self.assertIsNotNone(b['campaigns'][0]['budget_action'])
 def test_negative_provisional_model_never_creates_funding(self):
  m=self.evaluate(*fixture(margin=1))
  self.assertFalse(m['ready'])
 def test_no_orders_is_not_zero_drr_or_positive_economics(self):
  data=fixture();data[1]['days'][0]['orders']=0;data[1]['days'][0]['apps'][0]['nms'][0]['orders']=0
  self.assertTrue(self.evaluate(*data)['preliminary'])
 def test_changed_day_excluded_and_waits_for_first_full_day(self):
  data=list(fixture());data[-1]=[dict(cid=7,nm=1,kind='bid',at='2026-11-03T12:00:00+00:00')]
  result=self.evaluate(*data)
  self.assertEqual(result['evaluation_status'],'waiting')
  self.assertFalse(result['post_change_result_available'])
  self.assertEqual(result['funding_basis'],'continuation_historical_traffic_current_economics')
  self.assertTrue(result['ready']) # provisional funding is not proof of post-change growth
 def test_unreconciled_campaign_and_sku_attribution_not_ready(self):
  data=list(fixture());data[1]['days'][0]['orders']=5
  self.assertFalse(self.evaluate(*data)['ready'])
if __name__=='__main__':unittest.main()

