import ast,unittest
from pathlib import Path
class Tests(unittest.TestCase):
 def test_no_astra_literals_in_executable_runtime(self):
  root=Path(__file__).resolve().parents[1];bad=[]
  for p in root.rglob('*.py'):
   rel=p.relative_to(root)
   if any(x in rel.parts for x in ('private-audit','recovery-output','recovery-vault','.git','tests'))or p.name.startswith('test_'):continue
   try:tree=ast.parse(p.read_text(encoding='utf-8-sig'))
   except (UnicodeError,SyntaxError):continue
   for n in ast.walk(tree):
    if isinstance(n,ast.Constant)and isinstance(n.value,str)and 'gpt-6-astra'in n.value:bad.append(str(rel)+':'+str(n.lineno))
  self.assertEqual([],bad)
 def test_ooo_ignores_historical_model_and_retains_caps(self):
  root=Path(__file__).resolve().parents[1]
  for name in ('ooo_cloud_pilot_20261106.py','ooo_pilot_full_worker.py'):
   tree=ast.parse((root/'scripts'/name).read_text(encoding='utf-8'))
   calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)and any(k.arg=='model'for k in n.keywords)]
   self.assertEqual(1,len(calls))
   chosen=next(k.value for k in calls[0].keywords if k.arg=='model')
   self.assertEqual(ast.dump(chosen),ast.dump(ast.Name(id='MODEL',ctx=ast.Load())))
if __name__=='__main__':unittest.main()
