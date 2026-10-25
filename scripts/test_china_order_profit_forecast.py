import unittest,copy
from china_order_profit_forecast import calculate_inputs
def fixture():
    day='2026-10-23';p=dict(nm_id=1,article='demo',finished=4,paid=2,returned=0,reported_pct=50)
    part=dict(period_from=day,orders=2,order_amount_cny=200)
    b=dict(buyout=dict(rows=[p,dict(p,nm_id=2,article='ad-only')],snapshot_id='own',period_from='2026-09-23',period_to='2026-10-22',observed_at='2026-10-23T10:00:00Z'),
      stock=dict(source_key='stock',observed_at='2026-10-23T10:00:00Z',rows=[dict(article='demo',cost_rub=100)]),history_costs=[],
      funnel=[dict(complete=True,rows=[dict(nm_id=1,selected=part,past=part)])],finance=dict(rows=[]),
      policy=dict(fx_rub_cny=12,tax_pct=5,handling_rub=10,commission_pct=20,logistics_by_nm={'1':dict(delivery_cny=1,delivery_source='own')}))
    e=dict(prices={'rows':[dict(nm_id=1,seller_price=100)]},days=[day],orders_observed_at='2026-10-24T04:00:00Z',
      ad_expenses=dict(observed_at='2026-10-24T04:00:00Z',daily={day:dict(spend_cny=7,by_sku={'1':5,'2':2})}))
    return b,e,[dict(nm_id=1,article='demo',day=day,orders=2)],dict(cabinet='token_3',rub_per_cny=12,rows={})
class ForecastTests(unittest.TestCase):
    def test_costs_tax_and_all_advertising_are_subtracted_once(self):
        r=calculate_inputs(*fixture());self.assertEqual(r['daily'][0]['forecast_profit_rub'],672)
        self.assertEqual(r['daily'][0]['advertising_on_unordered_skus_rub'],24)
        self.assertFalse(r['rows'][0]['is_actual'])
    def test_real_zero_buyout_is_not_fifty(self):
        b,e,o,m=fixture();b['buyout']['rows'][0].update(paid=0,reported_pct=0)
        r=calculate_inputs(b,e,o,m);self.assertEqual(r['rows'][0]['buyout_pct'],0)
        self.assertEqual(r['daily'][0]['forecast_profit_rub'],-128)
    def test_fifty_is_only_disclosed_no_completed_sample(self):
        b,e,o,m=fixture();b['buyout']['rows'][0].update(paid=0,finished=0,reported_pct=0)
        r=calculate_inputs(b,e,o,m);self.assertTrue(r['rows'][0]['buyout_fallback'])
    def test_missing_cost_blocks_full_total_instead_of_zero_fill(self):
        b,e,o,m=fixture();b['stock']['rows']=[]
        r=calculate_inputs(b,e,o,m);self.assertIsNone(r['daily'][0]['forecast_profit_rub']);self.assertTrue(r['gaps'])
    def test_missing_current_cost_uses_sourced_historical_cost(self):
        b,e,o,m=fixture();b['stock']['rows']=[]
        b['history_costs']=[dict(nm_id=1,cost_rub=100,cost_date='2026-10-20',source_key='MoySklad history')]
        self.assertEqual(calculate_inputs(b,e,o,m)['daily'][0]['forecast_profit_rub'],672)
    def test_extra_created_order_price_estimate_is_explicit(self):
        b,e,o,m=fixture();o[0]['orders']=3
        r=calculate_inputs(b,e,o,m);row=r['rows'][0]
        self.assertEqual(row['wb_funnel_order_sum_cny'],200);self.assertEqual(row['model_revenue_cny'],300)
        self.assertEqual(row['price_scenario_units'],1)
    def test_unknown_daily_wb_amount_is_not_zero(self):
        b,e,o,m=fixture();b['funnel']=[]
        r=calculate_inputs(b,e,o,m);self.assertIsNone(r['daily'][0]['forecast_profit_rub'])
if __name__=='__main__':unittest.main()

