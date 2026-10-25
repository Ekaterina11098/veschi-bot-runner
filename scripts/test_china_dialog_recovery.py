import ast,json,unittest
from datetime import datetime,timezone
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path
class Recovery(unittest.TestCase):
 def test_replaced_dispatches_are_drained_in_order(self):
  module=ast.parse(Path('scripts/conversion_watches.py').read_text())
  fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='drain_saved_questions')
  ns=dict(DEPLOYED_AFTER='2026-10-01',saved_network_guard=nullcontext,question_marker=lambda r:bool(r.get('tool_trace')))
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'queue','exec'),ns)
  called=[]
  w=SimpleNamespace(now=datetime.now(timezone.utc),db=lambda *a,**kw:[dict(id=98,tool_trace=[1]),dict(id=99,tool_trace=[1]),dict(id=100,tool_trace=[])],question=lambda i:called.append(i) or 'sent')
  result=ns['drain_saved_questions'](w,101)
  self.assertEqual(called,[98,99,101]);self.assertEqual(len(result),3)
 def test_requested_pending_not_duplicated(self):
  module=ast.parse(Path('scripts/conversion_watches.py').read_text());fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='drain_saved_questions')
  ns=dict(DEPLOYED_AFTER='2026-10-01',saved_network_guard=nullcontext,question_marker=lambda r:True)
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'queue','exec'),ns)
  calls=[];w=SimpleNamespace(now=datetime.now(timezone.utc),db=lambda *a,**kw:[dict(id=101)],question=lambda i:calls.append(i) or 'sent')
  ns['drain_saved_questions'](w,101);self.assertEqual(calls,[101])
 def test_source_wire_shape_is_normalized_before_readback(self):
  module=ast.parse(Path('scripts/china_new_ad_reports.py').read_text())
  source=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='source')
  node=next(n for n in source.body if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and ast.unparse(n.value).startswith('json.loads(json.dumps(result'))
  ns=dict(json=json,result=dict(campaigns={41298169:dict(id=41298169)},amount=12.34))
  exec(compile(ast.Module(body=[node],type_ignores=[]),'normalize','exec'),ns)
  self.assertEqual(ns['result'],json.loads(json.dumps(ns['result'])))
  self.assertIn('41298169',ns['result']['campaigns'])
if __name__=='__main__':unittest.main()
