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

class VerifiedUiFundingTests(unittest.TestCase):
 def test_verified_ui_funding_is_campaign_scoped_and_fails_closed(self):
  from china_advertising_v2 import verified_ui_funding
  receipt=dict(status='verified',kind='owner_oneoff_budget_topup',before=dict(id=12,budget_cny=33.72),after=dict(id=12,budget_cny=533.16),amount_cny=500,verified_at='2026-10-30T05:09:01Z')
  self.assertEqual(verified_ui_funding(receipt,12),('2026-10-30T05:09:01Z',500))
  self.assertIsNone(verified_ui_funding(receipt,13))
  for field,value in [('status','accepted'),('kind','proposal'),('amount_cny',None),('amount_cny',True),('amount_cny',0),('verified_at',None)]:
   with self.subTest(field=field,value=value):
    changed=dict(receipt);changed[field]=value
    self.assertIsNone(verified_ui_funding(changed,12))

class CompactUiFundingTests(unittest.TestCase):
 def test_compact_history_preserves_verified_ui_funding_evidence(self):
  from china_advertising_v2 import compact_execution_records,verified_ui_funding
  payload=dict(status='verified',kind='owner_oneoff_budget_topup',before=dict(id=12),after=dict(id=12),amount_cny=500,verified_at='2026-10-30T05:09:01Z')
  compact=compact_execution_records([dict(cache_key='receipt',payload=payload)])[0]['payload']
  self.assertEqual(verified_ui_funding(compact,12),('2026-10-30T05:09:01Z',500))

class ExplicitUtcReceiptTests(unittest.TestCase):
 def test_clock_utc_timestamps_normalize_without_guessing_timezone(self):
  from china_advertising_v2 import event_time
  self.assertEqual(event_time('2026-10-30 04:53:42 UTC').isoformat(),'2026-10-30T04:53:42+00:00')
  with self.assertRaises(ValueError):event_time('2026-10-30 04:53:42')
 def test_verified_bid_and_exclusion_history_keep_explicit_utc_events(self):
  from china_advertising_v2 import history
  before=dict(id=12,nm_settings=[dict(nm_id=1,bids_kopecks=dict(recommendations=36)),dict(nm_id=2,bids_kopecks=dict(recommendations=28))])
  after=dict(id=12,nm_settings=[dict(nm_id=1,bids_kopecks=dict(recommendations=28))])
  changes=history([dict(status='verified',verified_at='2026-10-30 04:53:42 UTC',before=before,after=after)])
  self.assertEqual({x['kind'] for x in changes},{'bid','excluded'})
  self.assertTrue(all(x['at']=='2026-10-30T04:53:42+00:00' for x in changes))
 def test_ui_funding_with_explicit_utc_date_is_caption_safe(self):
  from china_advertising_v2 import verified_ui_funding
  receipt=dict(status='verified',kind='owner_oneoff_budget_topup',before=dict(id=12),after=dict(id=12),amount_cny=100,verified_at='2026-10-30 04:53:42 UTC')
  self.assertEqual(verified_ui_funding(receipt,12),('2026-10-30T04:53:42+00:00',100))
