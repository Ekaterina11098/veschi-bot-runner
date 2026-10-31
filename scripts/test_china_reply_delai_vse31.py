import unittest
from china_loss_control import is_all
class DelaiVseConfirmation(unittest.TestCase):
 def test_exact_owner_variants(self):
  for text in ['Делай все','Делай всё','делай','Сделай всё','Выполни все']:
   with self.subTest(text=text):self.assertTrue(is_all(text))
 def test_negated_and_discussion_not_approval(self):
  for text in ['Не делай все','не делай','Почему делай все','Делай все завтра']:
   with self.subTest(text=text):self.assertFalse(is_all(text))
if __name__=='__main__':unittest.main()
