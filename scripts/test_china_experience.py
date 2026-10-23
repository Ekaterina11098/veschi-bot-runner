import unittest
from china_experience import compare_conditions, summarize_comparison, windows, assess_candidate

class ExperienceTests(unittest.TestCase):
 def test_unknown_is_not_unchanged(self):
  result=compare_conditions({}, {})
  self.assertIn('spp',result['unknown'])
  self.assertEqual(result['transferability'],'limited')
  self.assertEqual(result['algorithm_change'],'not_established')
 def test_changed_conditions_do_not_prove_algorithm_change(self):
  result=compare_conditions({'bid':.28,'customer_price':2000},{'bid':.31,'customer_price':2100})
  self.assertEqual(len(result['changes']),2)
  self.assertEqual(result['algorithm_change'],'not_established')
  self.assertTrue(result['repeat_requires_confirmation'])
 def test_missing_profit_is_not_zero(self):
  common=dict(days=3,period_complete=True,profit_method='expected',currency='RUB')
  self.assertEqual(summarize_comparison(dict(common,total_profit=None),dict(common,total_profit=100))['outcome'],'inconclusive')
 def test_both_positive_and_negative_experience(self):
  common=dict(days=3,period_complete=True,profit_method='expected',currency='RUB',orders=5)
  for before,after,outcome in [(10,20,'positive'),(20,10,'negative')]:
   result=summarize_comparison(dict(common,total_profit=before),dict(common,total_profit=after))
   self.assertEqual(result['outcome'],outcome)
   self.assertEqual(result['causality'],'not_established')
 def test_excludes_change_day(self):
  result=windows('2026-10-23T16:31:00+00:00')
  self.assertEqual(result['after_from'],'2026-10-24')
  self.assertEqual(result['evaluate_from'],'2026-10-27')
 def test_negative_experience_is_reviewed_not_permanently_banned(self):
  event=dict(event_id='previous',action=dict(nm_ids=[10]),business_outcome='negative',context=dict(seller_price=100))
  self.assertTrue(assess_candidate([event],10,dict(seller_price=100))['needs_review'])
  revised=assess_candidate([event],10,dict(seller_price=110))
  self.assertFalse(revised['needs_review']);self.assertTrue(revised['requires_confirmation'])
  self.assertTrue(revised['risks'])

if __name__=='__main__':unittest.main()
