"""Scheduled intraday must reach the same complete deterministic gate as morning."""
import ast,types,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from test_china_price_schedule_identity import function
from test_china_price_delivery import Delivery

def prepare_method():
 tree=ast.parse(Path(__file__).with_name('china_coverage_worker.py').read_text(encoding='utf8'))
 cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='CoverageWorker')
 node=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='prepare')
 ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'prepare','exec'),ns)
 return ns['prepare']

class ScheduledIntraday(unittest.TestCase):
 def test_intraday_uses_complete_selector_and_zero_model_gate(self):
  calls=[]
  def choose(w,preview):
   calls.append(preview)
   w.price_control_review={'status':'complete_disclosed_forecast_model'}
   return 'Повышение: нет\n\nСнижение: нет',[{'name':'china_price_daily_report','status':'complete_orders'}]
  w=types.SimpleNamespace(mode='intraday',day=date(2026,11,13))
  with patch.dict('sys.modules',{'china_price_selection':types.SimpleNamespace(choose=choose)}):
   answer,trace=prepare_method()(w,True)
  review=function('china_codex_reports.py','review_price',dict(Core=lambda:(_ for _ in()).throw(AssertionError('paid model forbidden'))))
  with patch.dict('sys.modules',{'china_price_current_check':types.SimpleNamespace(check=lambda worker,text:text)}):
   answer,trace=review(w,answer,trace)
  self.assertEqual(calls,[True]);self.assertEqual(trace[-1]['model_calls'],0)
  self.assertEqual(w.mode,'intraday')
 def test_incomplete_reduction_cannot_pass_as_final(self):
  review=function('china_codex_reports.py','review_price',{})
  w=types.SimpleNamespace(mode='intraday',day=date(2026,11,13),price_control_review={'status':'unavailable'})
  with self.assertRaisesRegex(ValueError,'reduction review incomplete'):
   review(w,'draft',[{'name':'china_price_daily_report','status':'complete_orders'}])
 def test_intraday_delivery_retains_separate_identity_and_no_replay(self):
  helper=Delivery();w=helper.worker(6);w.mode='intraday'
  db,calls=helper.run_delivery(w)
  self.assertIn('china_agent:price_delivery:v2:2026-11-09:intraday',db)
  self.assertNotIn('china_agent:price_delivery:v2:2026-11-09:morning',db)
  _,calls=helper.run_delivery(w,db)
  self.assertEqual(calls,['getMe'])
if __name__=='__main__':unittest.main()
