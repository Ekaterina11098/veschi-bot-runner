"""Offline transport regression: only safe cache GET may be retried."""
import ast,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import requests
tree=ast.parse(Path('advertising_budgets_owner.py').read_text())
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='cached_read_request')
ns={'time':__import__('time')}
exec(compile(ast.Module(body=[node],type_ignores=[]),'retry-function','exec'),ns)
call=ns['cached_read_request']
class RetryTests(unittest.TestCase):
 def invoke(self,native,method='GET',host='cache.test'):
  return call(native,None,method,'https://'+host+'/rest/v1/analytics_snapshots','cache.test')
 def test_recovers_read_timeout(self):
  n=Mock(side_effect=[requests.exceptions.ReadTimeout(),Mock(status_code=200)])
  with patch('time.sleep') as sleep:self.assertEqual(self.invoke(n).status_code,200);sleep.assert_called_once_with(5)
 def test_bounded(self):
  n=Mock(side_effect=requests.exceptions.ReadTimeout())
  with patch('time.sleep') as sleep:
   with self.assertRaises(requests.exceptions.ReadTimeout):self.invoke(n)
  self.assertEqual(n.call_count,4);self.assertEqual([x.args[0] for x in sleep.call_args_list],[5,15,30])
 def test_no_wb_replay(self):
  n=Mock(side_effect=requests.exceptions.ReadTimeout())
  with self.assertRaises(requests.exceptions.ReadTimeout):self.invoke(n,host='advert-api.wildberries.ru')
  self.assertEqual(n.call_count,1)
 def test_no_write_replay(self):
  for method in ('POST','PATCH','PUT','DELETE'):
   n=Mock(side_effect=requests.exceptions.ReadTimeout())
   with self.assertRaises(requests.exceptions.ReadTimeout):self.invoke(n,method)
   self.assertEqual(n.call_count,1)
 def test_transient_gateway(self):
  bad=Mock(status_code=503);n=Mock(side_effect=[bad,Mock(status_code=200)])
  with patch('time.sleep'):self.assertEqual(self.invoke(n).status_code,200)
  bad.close.assert_called_once()
 def test_no_429_or_permanent_replay(self):
  for code in (400,401,403,404,429):
   n=Mock(return_value=Mock(status_code=code));self.assertEqual(self.invoke(n).status_code,code);self.assertEqual(n.call_count,1)
if __name__=='__main__':unittest.main()
