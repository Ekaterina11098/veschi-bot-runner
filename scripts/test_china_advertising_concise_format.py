import unittest
from china_advertising_v2_png import budget_column,recommendations

class ConciseFormat(unittest.TestCase):
 def test_conditional_amount_does_not_publish_internal_diagnostic(self):
  c=dict(budget_reserve_amount=1650,budget_economics_reason='SKU 1473244339 needs economics',budget_action=None)
  self.assertEqual(budget_column(c),'Пока не пополнять.\nПоложительная экономика РК не подтверждена.')
  self.assertIsNone(c['budget_action'])
 def test_unknown_amount_is_not_zero_or_funding_approval(self):
  self.assertEqual(budget_column({}),'Сумма не рассчитана')
 def test_manual_problem_is_not_labeled_no_action_needed(self):
  c=dict(attention=[],focus=[dict(article='bag',period=dict(spend=80,orders=0,amount=0),candidate_for_manual_review=True)])
  result=' '.join(recommendations(c))
  self.assertIn('bag',result);self.assertIn('Решение не готово',result)
  self.assertNotIn('Не требуется',result)

if __name__=='__main__':unittest.main()

