import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from unittest.mock import patch
from review_auto_five_star import classify
class ChinaRoutingAuditTests(unittest.TestCase):
 def test_explicit_doubt_is_manual_even_if_model_says_positive(self):
  item=dict(productValuation=5,text='Насчет кожи сомневаюсь,но очень красивая и вместительная без изъянов')
  with patch('review_auto_five_star.semantic_fallback',return_value={'eligible':True}) as semantic:
   self.assertFalse(classify(item,cabinet='token_3')['eligible'])
   semantic.assert_not_called()
   self.assertFalse(classify(item,cabinet='token_1')['eligible'])
   self.assertFalse(classify(item,cabinet='token_2')['eligible'])
 def test_resolved_rhetorical_question_uses_semantics_only_for_china(self):
  item=dict(productValuation=5,text='Превосходная сумка. Думала в чем подвох...? Нет, все идеально. Спасибо!')
  with patch('review_auto_five_star.semantic_fallback',return_value={'eligible':True}) as semantic:
   self.assertTrue(classify(item,cabinet='token_3')['eligible'])
   semantic.assert_called_once()
   self.assertFalse(classify(item,cabinet='token_1')['eligible'])
   self.assertFalse(classify(item,cabinet='token_2')['eligible'])
 def test_real_question_stays_manual(self):
  with patch('review_auto_five_star.semantic_fallback',return_value={'eligible':True}) as semantic:
   self.assertFalse(classify(dict(productValuation=5,text='Сумка хорошая. Подойдет ли ноутбук?'),cabinet='token_3')['eligible'])
   semantic.assert_not_called()
 def test_rhetoric_does_not_override_semantic_complaint_or_failure(self):
  item=dict(productValuation=5,text='Думала в чем подвох...? Нет, все идеально. Но порвалась.')
  with patch('review_auto_five_star.semantic_fallback',return_value={'eligible':False}):
   self.assertFalse(classify(item,cabinet='token_3')['eligible'])


