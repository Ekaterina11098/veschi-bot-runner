import unittest
from china_expected_order_profit import expected_profit,buyout_probability,resolved_buyout_rate
class ExpectedTests(unittest.TestCase):
 def test_nonbuyout_costs_and_ads_are_not_scaled_as_profit(self):
  result=expected_profit([dict(order_id='1',buyout_profit=100,nonbuyout_profit=-40)],.5,10,0)
  self.assertEqual(result['expected_profit'],20);self.assertFalse(result['is_actual'])
 def test_no_completed_orders_is_not_zero_probability(self):
  self.assertIsNone(buyout_probability(0,0,0));self.assertEqual(buyout_probability(0,4,0),0)
 def test_returns_adjust_numerator(self):
  self.assertEqual(buyout_probability(2,4,50),.5)
 def test_missing_reverse_cost_is_not_zero(self):
  with self.assertRaises(ValueError):expected_profit([dict(order_id='1',buyout_profit=100,nonbuyout_profit=None)],.5,10,0)
 def test_fallback_is_labeled(self):
  result=resolved_buyout_rate(0,0,0);self.assertEqual(result['percent'],50);self.assertEqual(result['source'],'fallback')
 def test_confirmed_zero_is_not_replaced(self):
  result=resolved_buyout_rate(0,4,0);self.assertEqual(result['percent'],0);self.assertEqual(result['source'],'own_article')
 def test_absent_statistics_use_fallback(self):
  self.assertEqual(resolved_buyout_rate(None,None)['percent'],50)
if __name__=='__main__':unittest.main()

