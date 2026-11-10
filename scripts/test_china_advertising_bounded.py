import ast,copy,json,os,unittest
from pathlib import Path
def compact(value):
 source=Path(__file__).with_name('china_advertising_bounded_review.py').read_text(encoding='utf-8')
 fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='compact')
 scope={'copy':copy};exec(compile(ast.Module(body=[fn],type_ignores=[]),'compact','exec'),scope)
 return scope['compact'](value)
class BoundedMidday(unittest.TestCase):
 def sample(self):
  return dict(data=dict(allowed_actions={'one':dict(nm_id=1,campaign_id=2,target_minor=28)},candidate_evidence={'one':dict(metrics=None)},completed_source=dict(products={'2:1':dict(nm_id=1,daily={'closed':None}),'2:3':dict(nm_id=3)},economics=dict(rows={'1':dict(stock_free=0),'3':{}}),catalogue=dict(rows=[dict(nmID=1)]),current_campaigns=[dict(id=2,nm_settings=[dict(nm_id=1)])]),intraday_observation=dict(day='2026-11-10',campaigns=['duplicate'])),work_notes=[])
 def test_exact_actions_and_evidence(self):
  p=self.sample();v=compact(p);self.assertEqual(p['data']['allowed_actions'],v['data']['allowed_actions']);self.assertEqual(p['data']['candidate_evidence'],v['data']['candidate_evidence'])
 def test_unknown_not_zero(self):
  self.assertIsNone(compact(self.sample())['data']['completed_source']['products']['2:1']['daily']['closed'])
 def test_original_catalogue_unchanged(self):
  p=self.sample();compact(p);self.assertEqual(2,len(p['data']['completed_source']['products']))
 def test_scope_disclosed(self):
  self.assertIn('No new research actions',compact(self.sample())['context_scope'])
 def test_large_candidate_set_is_partitioned_without_loss(self):
  source=Path(__file__).with_name('china_advertising_bounded_review.py').read_text(encoding='utf-8')
  nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name in ('compact','ask','replace_times')]
  calls=[]
  def one(core,identity,p,validate,rules,*args):
   calls.append(p)
   self.assertLess(len(json.dumps(p)),29000)
   return validate(dict(kind='advertising_review',decisions=[dict(id=k,note='Keep')for k in p['data']['allowed_actions']],directions={d:dict(status='checked',note='Group only')for d in ('raise','add','reduce','exclude')},research=[])),{}
  scope=dict(copy=copy,os=os,ask_one=one)
  exec(compile(ast.Module(body=nodes,type_ignores=[]),'bounded','exec'),scope)
  p=self.sample();p['data']['allowed_actions']={str(i):dict(nm_id=i+1,campaign_id=2,evidence='x'*2000)for i in range(35)}
  result,_=scope['ask'](None,'test',p,lambda v:v,'rules','root',lambda v:'hash',None,None,json.dumps,'test')
  self.assertGreater(len(calls),1)
  self.assertEqual(set(p['data']['allowed_actions']),{r['id']for r in result['decisions']})
 def test_full_catalogue_reviewed_even_without_candidates(self):
  source=Path(__file__).with_name('china_advertising_bounded_review.py').read_text(encoding='utf-8')
  nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name in ('compact','ask','replace_times')]
  seen=set()
  def one(core,identity,p,validate,rules,*args):
   seen.update(str(x['nm_id'])for x in p['data']['completed_source']['products'].values())
   return dict(kind='advertising_review',decisions=[],directions={d:dict(status='checked',note='Checked')for d in ('raise','add','reduce','exclude')},research=[]),{}
  scope=dict(copy=copy,os=os,ask_one=one);exec(compile(ast.Module(body=nodes,type_ignores=[]),'bounded','exec'),scope)
  p=self.sample();p['data']['allowed_actions']={}
  _,receipt=scope['ask'](None,'test',p,lambda v:v,'rules','root',lambda v:'hash',None,None,json.dumps,'test')
  self.assertEqual({'1','3'},seen)
  self.assertEqual({'1','3'},set(receipt['reviewed_nm_ids']))
if __name__=='__main__':unittest.main()