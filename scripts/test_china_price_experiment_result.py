import unittest
from china_price_experiment_result import experiment_result,conversion_test,zero_buyout_signal
class ResultTests(unittest.TestCase):
 def test_zero_baseline_has_no_percentage_growth(self):
  r=experiment_result(0,100,100,10,100,10,1,20);self.assertIsNone(r['profit_delta_percent']);self.assertEqual(r['status'],'positive')
 def test_profit_growth_and_conversion_drop_is_mixed(self):
  self.assertEqual(experiment_result(100,200,100,20,100,3,4,20)['status'],'mixed')
 def test_confirmed_early_decline_can_recommend_rollback(self):
  r=experiment_result(200,50,100,30,100,2,1,20);self.assertEqual(r['status'],'rollback_review');self.assertFalse(r['execution_authorized'])
 def test_missing_profit_blocks_result(self):
  self.assertEqual(experiment_result(None,None,100,3,100,2,1,20,('не подтверждена обратная логистика',))['status'],'incomplete')
 def test_low_counts_do_not_claim_significant_drop(self):
  self.assertGreater(conversion_test(20,1,20,0),.05)
 def test_unfinished_orders_are_not_product_fault(self):
  result=zero_buyout_signal(3,0,0,3,0,0);self.assertFalse(result['attention']);self.assertEqual(result['status'],'awaiting_outcomes')
 def test_completed_refusals_raise_alert(self):
  result=zero_buyout_signal(13,0,4,9,4,0);self.assertTrue(result['attention']);self.assertIn('невыкупы/отказы 4',result['message'])
 def test_refunds_are_distinct_from_initial_refusals(self):
  result=zero_buyout_signal(2,0,2,0,0,2);self.assertTrue(result['attention']);self.assertIn('возвраты после выкупа 2',result['message'])
 def test_unknown_outcomes_do_not_create_false_alert(self):
  self.assertFalse(zero_buyout_signal(2,None,0,2,0,0)['attention'])
 def test_fallback_buyout_does_not_hide_conversion_decline(self):
  self.assertEqual(experiment_result(200,50,100,30,100,2,1,0)['status'],'watch_decline')
if __name__=='__main__':unittest.main()

