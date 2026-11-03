import copy,unittest
from datetime import datetime,timedelta,timezone
from china_advertising_economic_review import apply,model_rows
from china_morning_readiness import current_prices

def fixture(spend=50,orders=0,amount=0,clicks=180,bid=28):
 at=datetime.now(timezone.utc).isoformat()
 e=dict(observed_at=at,stock_observed_at=at,price_observed_at=at,stock_free=8,own_cogs_rub=120,seller_price_cny=100,expected_margin_before_ads_cny=20)
 row=dict(nm=10,article='bag',period=dict(spend=spend,orders=orders,amount=amount,clicks=clicks,views=1000),decision='old',action=None)
 b=dict(campaigns=[dict(id=1,status=9,payment='cpc',focus=[row])])
 s=dict(economics=dict(rows={'10':e}),batches={'0':dict(campaigns=dict(adverts=[dict(id=1,settings=dict(placements=dict(search=True)),nm_settings=[dict(nm_id=10,bids_kopecks=dict(search=bid)),dict(nm_id=11)],restrictions=dict(can_change_nms=True))]))})
 return b,s,{'1:10':28}

class Review(unittest.TestCase):
 def test_spending_without_orders_at_minimum_proposes_exact_sku_exclusion(self):
  b,s,m=fixture();r=apply(b,s,m)['campaigns'][0]['focus'][0]
  self.assertEqual(r['action']['kind'],'ad_exclude_sku');self.assertEqual(r['action']['nm_id'],10)
  self.assertNotIn('0.00%',r['reason']);self.assertIsNone(b['campaigns'][0]['focus'][0]['action'])
 def test_above_minimum_reduces_before_exclusion(self):
  b,s,m=fixture(bid=34);r=apply(b,s,m)['campaigns'][0]['focus'][0]
  self.assertEqual(r['action']['target_minor'],28)
 def test_minor_exceedance_is_explicit_separate_exception_not_automatic_test(self):
  b,s,m=fixture(spend=5.1,orders=1,amount=100);r=apply(b,s,m)['campaigns'][0]['focus'][0]
  self.assertIsNone(r['action']);self.assertIn('отдельно согласованный',r['decision'])
 def test_first_complete_day_after_latest_change_is_required(self):
  b,s,m=fixture();b['campaigns'][0]['focus'][0]['pending_first_day']=True
  self.assertIsNone(apply(b,s,m)['campaigns'][0]['focus'][0]['action'])
 def test_low_traffic_not_automatically_excluded(self):
  b,s,m=fixture(spend=2,clicks=7);r=apply(b,s,m)['campaigns'][0]['focus'][0]
  self.assertIsNone(r['action']);self.assertIn('Сохранить',r['decision'])
 def test_negative_pre_ad_model_does_not_require_spending_to_hundred_clicks(self):
  b,s,m=fixture(spend=10,clicks=35);s['economics']['rows']['10'].update(expected_margin_before_ads_cny=-5,sample_size=20)
  r=apply(b,s,m)['campaigns'][0]['focus'][0];self.assertEqual(r['action']['kind'],'ad_exclude_sku')
 def test_stale_stock_blocks_action_and_report_completion(self):
  b,s,m=fixture();s['economics']['rows']['10']['stock_observed_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
  result=apply(b,s,m);self.assertFalse(result['economic_review_complete']);self.assertIsNone(result['campaigns'][0]['focus'][0]['action'])
 def test_no_stock_is_not_a_zero_cogs_profit_model(self):
  b,s,m=fixture();s['economics']['rows']['10'].update(stock_free=0,expected_margin_before_ads_cny=None,own_cogs_rub=None)
  r=apply(b,s,m)['campaigns'][0]['focus'][0];self.assertIn('до возврата',r['decision']);self.assertNotIn('model_profit_for_attributed_orders_cny',r)
 def test_bulk_prices_ignore_unrelated_currency_but_validate_selected(self):
  class IO:
   def wb(self,path):return dict(listGoods=[dict(nmID=99,currencyIsoCode4217='RUB',sizes=[]),dict(nmID=10,vendorCode='bag',currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=100)])])
  self.assertEqual(current_prices(IO(),[10])['rows'][0]['seller_price'],100)

 def test_positive_own_economics_does_not_hit_artificial_six_percent_cliff(self):
  for spend in (59.9,60.3,100):
   for bid in (28,34):
    b,s,m=fixture(spend=spend,orders=10,amount=1000,bid=bid)
    s['economics']['rows']['10'].update(sample_size=12,buyout_fallback=False,commission_policy_fallback=False)
    row=apply(b,s,m)['campaigns'][0]['focus'][0]
    self.assertIsNone(row['action'])
    self.assertGreater(row['model_profit_for_attributed_orders_cny'],0)
 def test_loss_still_allows_exclusion_with_orders(self):
  b,s,m=fixture(spend=250,orders=10,amount=1000)
  s['economics']['rows']['10'].update(sample_size=12,buyout_fallback=False)
  self.assertEqual('ad_exclude_sku',apply(b,s,m)['campaigns'][0]['focus'][0]['action']['kind'])

 def test_small_zero_order_exposure_above_minimum_is_not_automatic_cut(self):
  b,s,m=fixture(spend=13.33,orders=0,clicks=43,bid=31)
  s['economics']['rows']['10'].update(expected_margin_before_ads_cny=35.64,sample_size=6)
  self.assertIsNone(apply(b,s,m)['campaigns'][0]['focus'][0]['action'])
 def test_two_unpaid_orders_do_not_prove_negative_unit_economics(self):
  b,s,m=fixture(spend=11.48,orders=0,clicks=41)
  s['economics']['rows']['10'].update(expected_margin_before_ads_cny=-15.8,sample_size=2,commission_policy_fallback=True)
  self.assertIsNone(apply(b,s,m)['campaigns'][0]['focus'][0]['action'])
 def test_positive_completed_economics_clears_inherited_cut_even_under_drr_target(self):
  b,s,m=fixture(spend=30,orders=10,amount=1000,bid=34)
  s['economics']['rows']['10'].update(sample_size=20)
  b['campaigns'][0]['focus'][0]['action']=dict(kind='ad_set_bid',old_minor=34,target_minor=28)
  self.assertIsNone(apply(b,s,m)['campaigns'][0]['focus'][0]['action'])
if __name__=='__main__':unittest.main()

