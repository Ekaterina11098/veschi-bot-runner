import ast,pathlib,types,sys,unittest
from datetime import date
from unittest.mock import patch

scope={}
tree=ast.parse(pathlib.Path(__file__).with_name('china_codex_reports.py').read_text(encoding='utf8'))
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='review_price')
exec(compile(ast.Module(body=[node],type_ignores=[]),'review_price','exec'),scope)

class FinalPriceRoute(unittest.TestCase):
 def worker(self,mode='morning'):
  return types.SimpleNamespace(mode=mode,day=date(2026,11,12),get=lambda key:{},price_control_review={'status':'complete_disclosed_forecast_model'},control_value={'model_version':'wb_profit_floor_price_hypothesis_v4','report_date':'2026-11-12'})
 def test_disabled_paid_transport_uses_complete_rules_and_current_check(self):
  calls=[]
  def blocked(*args):raise PermissionError('No request sent')
  modules={'china_no_paid':types.SimpleNamespace(require_paid_api=blocked),'china_price_current_check':types.SimpleNamespace(check=lambda w,a:calls.append(a)or a)}
  with patch.dict(sys.modules,modules):
   answer,trace=scope['review_price'](self.worker(),'ready',[{'name':'china_price_daily_report','status':'complete_orders'}])
  self.assertEqual(answer,'ready');self.assertEqual(calls,['ready']);self.assertEqual(trace[-1]['model_calls'],0)
 def test_missing_reduction_review_cannot_publish_false_empty(self):
  w=self.worker();w.price_control_review={'status':'unavailable'}
  def blocked(*args):raise PermissionError()
  with patch.dict(sys.modules,{'china_no_paid':types.SimpleNamespace(require_paid_api=blocked)}):
   with self.assertRaises(ValueError):scope['review_price'](w,'draft',[{'name':'china_price_daily_report','status':'complete_orders'}])
 def test_control_preserves_canonical_table_without_model(self):
  answer,trace=scope['review_price'](self.worker('control'),'table',[])
  self.assertEqual(answer,'table');self.assertEqual(trace[-1]['model_calls'],0)

if __name__=='__main__':unittest.main()
