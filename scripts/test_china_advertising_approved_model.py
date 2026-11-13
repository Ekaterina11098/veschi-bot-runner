import unittest
from datetime import datetime,timezone
from china_advertising_economic_review import model_rows
class ApprovedModelTests(unittest.TestCase):
 def fixture(self,own=None):
  at=datetime.now(timezone.utc).isoformat()
  inputs=dict(products=dict(rows=[]if own is None else[dict(nm_id=1,**own)],observed_at=at,period_from='2026-10-14',period_to='2026-11-12'),prices=dict(rows=[dict(nm_id=1,article='fur',seller_price=425)],observed_at=at),stock=dict(rows=[dict(article='fur',stock=10,reserve=2,price=123600)],observed_at=at),fx=dict(rub_per_cny=12))
  policy=dict(commission_pct=20,tax_pct=5,payment_reserve_pct=3,handling_rub=0,planned_buyout_by_nm={'1':dict(probability=.3,source_ref='owner30')},logistics_by_nm={'1':dict(delivery_cny=38,route='Moscow_FBS',delivery_source='approvedoffer')})
  return inputs,policy
 def test_approved_absent_own30_and_current_costs(self):
  i,p=self.fixture();r=model_rows(i,p,{})['rows']['1'];self.assertEqual(r['buyout'],.3);self.assertTrue(r['buyout_fallback']);self.assertEqual(r['sample_size'],0);self.assertAlmostEqual(r['expected_margin_before_ads_cny'],.3*(425*.72-103)-38);self.assertEqual(r['payment_reserve_pct'],3)
 def test_actual_zero_is_never_replaced(self):
  i,p=self.fixture(dict(is_payed=0,finish_as_return=0,finished_orders=2,is_payed_percent_after_returns=0));r=model_rows(i,p,{})['rows']['1'];self.assertEqual(r['buyout'],0);self.assertFalse(r['buyout_fallback']);self.assertEqual(r['expected_margin_before_ads_cny'],-38)
 def test_own_small_sample_wins(self):
  i,p=self.fixture(dict(is_payed=1,finish_as_return=0,finished_orders=2,is_payed_percent_after_returns=50));self.assertEqual(model_rows(i,p,{})['rows']['1']['buyout'],.5)
 def test_missing_unapproved_stays_missing(self):
  i,p=self.fixture();p.pop('planned_buyout_by_nm');r=model_rows(i,p,{});self.assertFalse(r['rows']);self.assertIn('1',r['missing'])
 def test_partial_own_counters_not_hidden(self):
  i,p=self.fixture(dict(is_payed=1,finished_orders=2));r=model_rows(i,p,{});self.assertIn('1',r['missing'])
 def test_missing_tariff_not_zero(self):
  i,p=self.fixture();p['logistics_by_nm']={};self.assertIn('1',model_rows(i,p,{})['missing'])
if __name__=='__main__':unittest.main()
