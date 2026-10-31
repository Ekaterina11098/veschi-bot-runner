import sys,types,unittest,importlib
from unittest.mock import patch
class ImportIsolation(unittest.TestCase):
 def test_unrelated_dialog_does_not_import_diagnostic_inputs(self):
  stub=types.ModuleType('china_article_diagnostic')
  with patch.dict(sys.modules,{'china_article_diagnostic':stub}):
   sys.modules.pop('china_ad_expense_table',None)
   module=importlib.import_module('china_ad_expense_table')
   self.assertIsNone(module.handle(object(),{'chat_id':-1,'request_text':'Сколько заказов сегодня?'},[]))
   self.assertIsNone(module.handle(object(),{'chat_id':-1004342917488,'request_text':'Как приготовить суп?'},[]))
if __name__=='__main__':unittest.main()
