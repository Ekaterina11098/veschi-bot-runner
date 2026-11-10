import ast,copy,unittest
from pathlib import Path

def guard(value):
 source=Path(__file__).with_name('china_midday_completed_review.py').read_text(encoding='utf-8')
 fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='validate_recommendation_readiness')
 scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'readiness','exec'),scope)
 return scope['validate_recommendation_readiness'](copy.deepcopy(value))

class PartialReadiness(unittest.TestCase):
 def sample(self):
  return dict(economic_review_complete=False,economic_review_blockers=[dict(campaign_id=1,article='A')],campaigns=[dict(id=1,focus=[dict(article='A',action=None)],attention=[])],recommendation_directions={k:dict(status='checked')for k in ('raise','add','reduce','exclude')})
 def test_missing_evidence_is_visible_and_not_complete(self):
  result=guard(self.sample())
  self.assertFalse(result['economic_review_complete'])
  self.assertIn('не завершена',result['campaigns'][0]['recommendation_review_note'])
  self.assertTrue(all(x['status']=='unavailable'for x in result['recommendation_directions'].values()))
 def test_unsafe_action_still_blocks_delivery(self):
  p=self.sample();p['campaigns'][0]['focus'][0]['action']={'kind':'ad_exclude_sku'}
  with self.assertRaises(ValueError):guard(p)
 def test_unexplained_incomplete_review_still_blocks(self):
  p=self.sample();p['economic_review_blockers']=[]
  with self.assertRaises(ValueError):guard(p)
 def test_complete_review_unchanged(self):
  p=self.sample();p['economic_review_complete']=True
  self.assertEqual(p,guard(p))

if __name__=='__main__':unittest.main()