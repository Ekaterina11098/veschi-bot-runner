import unittest
from china_sales_growth_review import attach
class GrowthContractTests(unittest.TestCase):
 def fixture(self):return dict(campaigns=[dict(id=1,budget_action=dict(kind='topup_campaign',amount_cny=100))],growth_review=dict(status='complete'),recommendation_directions={k:dict(status='checked',rows=[])for k in ['raise','add','reduce','exclude']})
 def test_funding_alone_is_not_sales_growth(self):
  s=attach(self.fixture())['sales_growth_review']
  self.assertEqual([],s['growth']);self.assertEqual(1,len(s['budget_support']));self.assertFalse(s['funding_is_growth']);self.assertFalse(s['execution_authorized'])
 def test_missing_inputs_are_not_no_candidates(self):
  b=self.fixture();b['recommendation_directions']['add']['status']='unavailable'
  s=attach(b)['sales_growth_review'];self.assertEqual('incomplete',s['status']);self.assertFalse(s['empty_growth_means_no_ready_proposal'])
 def test_cost_control_and_unready_research_are_not_growth(self):
  b=self.fixture();b['recommendation_directions']['reduce']['rows']=[dict(ready=True,action=dict(kind='ad_set_bid'))]
  b['recommendation_directions']['add']['rows']=[dict(ready=False,action=dict(kind='ad_add_sku'))]
  s=attach(b)['sales_growth_review'];self.assertEqual([],s['growth']);self.assertEqual(1,len(s['cost_control']))
if __name__=='__main__':unittest.main()
