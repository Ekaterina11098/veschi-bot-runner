import unittest,copy
from china_advertising_v2 import guard_sku_exclusion
class Guard(unittest.TestCase):
 def row(self):return dict(action=dict(kind='ad_exclude_sku'),period=dict(clicks=180,spend=50,orders=0))
 def test_missing_economy_cannot_exclude(self):self.assertIsNone(guard_sku_exclusion(self.row(),{}, {},'2026-10-27')['action'])
 def test_postclick_unknown_cannot_exclude(self):
  e=dict(observed_at='2026-10-27T07:00:00+03:00',stock_observed_at='2026-10-27T07:00:00+03:00',stock_free=70,expected_margin_before_ads_cny=30,sample_reliable=True)
  self.assertIsNone(guard_sku_exclusion(self.row(),e,dict(other_sku_orders=10),'2026-10-27')['action'])
 def test_low_traffic_cannot_exclude(self):
  r=self.row();r['period']['clicks']=38
  e=dict(observed_at='2026-10-27T07:00:00+03:00',stock_observed_at='2026-10-27T07:00:00+03:00',stock_free=70,expected_margin_before_ads_cny=30,sample_reliable=True)
  self.assertIsNone(guard_sku_exclusion(r,e,{},'2026-10-27')['action'])
 def test_verified_context_preserves_candidate(self):
  e=dict(observed_at='2026-10-27T07:00:00+03:00',stock_observed_at='2026-10-27T07:00:00+03:00',stock_free=70,expected_margin_before_ads_cny=30,sample_reliable=True,entry_sku_attribution_verified=True)
  self.assertIsNotNone(guard_sku_exclusion(self.row(),e,{},'2026-10-27')['action'])
if __name__=='__main__':unittest.main()



class MissingEconomicsTimestampTests(unittest.TestCase):
 def test_missing_or_invalid_economics_dates_block_exclusion_without_crashing(self):
  from china_advertising_v2 import guard_sku_exclusion
  evidence=dict(observed_at='2026-10-29T12:00:00+03:00',stock_observed_at='2026-10-29T12:00:00+03:00',stock_free=12,expected_margin_before_ads_cny=10,sample_reliable=True)
  for field in ('observed_at','stock_observed_at'):
   for missing in (None,'',17,{},[],True,'invalid','2026-10-29T12:00:00'):
    with self.subTest(field=field,value=missing):
     row=dict(action=dict(kind='ad_exclude_sku'),period=dict(spend=100,amount=0,orders=0,clicks=200))
     current=dict(evidence);current[field]=missing
     result=guard_sku_exclusion(row,current,dict(other_sku_orders=0,orders_on_this_sku_other_campaigns=0),'2026-10-29')
     self.assertIsNone(result['action'])
     self.assertTrue(result['candidate_for_manual_review'])
     self.assertIn('нет свеж',result['reason'])
 def test_valid_economics_dates_keep_eligible_exclusion(self):
  from china_advertising_v2 import guard_sku_exclusion
  row=dict(action=dict(kind='ad_exclude_sku'),period=dict(spend=100,amount=0,orders=0,clicks=200))
  evidence=dict(observed_at='2026-10-29T12:00:00+03:00',stock_observed_at='2026-10-29T12:00:00+03:00',stock_free=12,expected_margin_before_ads_cny=10,sample_reliable=True)
  result=guard_sku_exclusion(row,evidence,dict(other_sku_orders=0,orders_on_this_sku_other_campaigns=0),'2026-10-29')
  self.assertEqual(result['action']['kind'],'ad_exclude_sku')
