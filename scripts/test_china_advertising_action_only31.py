import unittest
from china_advertising_v2_png import recommendations
class ActionOnlyNotes(unittest.TestCase):
 def test_no_action_is_exactly_not_required(self):
  for c in [{},{'notes':['Уже исключены: sku','Сохранить тест'],'attention':[]},{'missing_stats':True},{'never_started':True}]:
   self.assertEqual(recommendations(c),['Не требуется'])
 def test_only_new_action_and_no_reason_or_history(self):
  c={'attention':[{'article':'sku','decision':'Снизить 0,30 → 0,28 CNY.','reason':'old long explanation','action':{'kind':'ad_set_bid'}}],'notes':['Уже исключены: old']}
  self.assertEqual(recommendations(c),['sku: Снизить 0,30 → 0,28 CNY.'])
if __name__=='__main__':unittest.main()
