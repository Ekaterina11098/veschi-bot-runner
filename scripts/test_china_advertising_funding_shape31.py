import ast,unittest
from pathlib import Path
class FundingShapeRegression(unittest.TestCase):
 def test_mixed_step_metadata_preserves_verified_deposit(self):
  tree=ast.parse(Path(__file__).with_name('china_advertising_v2.py').read_text(encoding='utf-8-sig'))
  fn=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='funding_steps')
  env={'funds':[],'c':{'id':40933588},'payload':{},'verified_ui_funding':lambda z,cid:None}
  exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'funding_steps','exec'),env)
  env['funding_steps']({'steps':{'stage':'done','count':2,'missing':None,'array':[], 'deposit':{'status':'verified','path':'/adv/v1/budget/deposit?id=40933588','body':{'sum':100},'submitted_at':'2026-10-30T05:00:00Z'},'pending':{'status':'pending','body':{'sum':999}}}})
  self.assertEqual(env['funds'],[('2026-10-30T05:00:00Z',100)])
if __name__=='__main__':unittest.main()

