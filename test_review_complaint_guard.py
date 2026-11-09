import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from unittest.mock import patch
from review_auto_five_star import classify
import review_semantic_positive as semantic
class ComplaintGuardTests(unittest.TestCase):
 def test_concerns_in_every_field_even_if_model_says_positive(self):
  cases=['Пока нравится фасон дизайн мягкий материал , но это не кожа','Красивая, но не натуральная кожа','Ремень не кожаный','Сомневаюсь в качестве','Не уверена, что кожа','Похоже на кожзам','Сумка неплохая, отказ по браку.','Все понравилось но было пятно от клея','Сумка испачкала одежду','Цвет вообще другой!','Красивая, но неудобная']
  for text in cases:
   for field in ('text','pros','cons'):
    with self.subTest(text=text,field=field),patch.object(semantic,'request_assessment') as api:
     item=dict(productValuation=5,text='',pros='',cons='');item[field]=text
     self.assertFalse(classify(item,cabinet='token_3')['eligible'])
     self.assertFalse(semantic.classify_fields(item['text'],item['pros'],item['cons'])['eligible'])
     api.assert_not_called()
 def test_clean_positives_still_automatic(self):
  for text in ('Отличная сумка','Маленькая, но вместительная','Внешне соответствует описанию, упаковка супер. Без дефектов.',''):
   with self.subTest(text=text):
    self.assertTrue(classify(dict(productValuation=5,text=text),cabinet='token_3')['eligible'])
