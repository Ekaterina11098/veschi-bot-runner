import unittest
from china_price_experiment_result import experiment_result,conversion_test
class ResultTests(unittest.TestCase):
 def test_zero_baseline_has_no_percentage_growth(self):
  r=experiment_result(0,100,100,10,100,10,1,20);self.assertIsNone(r['profit_delta_percent']);self.assertEqual(r['status'],'positive')
 def test_profit_growth_and_conversion_drop_is_mixed(self):
  self.assertEqual(experiment_result(100,200,100,20,100,3,4,20)['status'],'mixed')
 def test_early_decline_does_not_recommend_rollback(self):
  r=experiment_result(200,50,100,30,100,2,1,20);self.assertEqual(r['status'],'watch_decline');self.assertFalse(r['execution_authorized'])
 def test_missing_profit_blocks_result(self):
  self.assertEqual(experiment_result(None,None,100,3,100,2,1,20,('не подтверждена обратная логистика',))['status'],'incomplete')
 def test_low_counts_do_not_claim_significant_drop(self):
  self.assertGreater(conversion_test(20,1,20,0),.05)
if __name__=='__main__':unittest.main()
