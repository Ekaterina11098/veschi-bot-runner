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

