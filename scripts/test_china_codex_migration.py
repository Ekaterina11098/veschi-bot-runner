import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
from china_codex_analysis import Core,POLICY,active
from china_codex_reports import ad_validate,review_advertising,review_price,price_parts
from china_codex_read_broker import validate_read
from datetime import date
class DB:
 def __init__(self):
  self.d={POLICY:dict(enabled=True,status='shadow',cabinet='token_3',chat_id=-1004342917488,wb_action_permission=False),'china_agent:shared_memory:policy:v1':dict(enabled=True)}
 def get(self,k):return copy.deepcopy(self.d.get(k))
 def once(self,k,v):
  if k in self.d:raise RuntimeError('Conflict')
  self.d[k]=copy.deepcopy(v)
 def update(self,k,v,*a):self.d[k]=copy.deepcopy(v);return True
 def api(self,*a,**kw):return []
class Events:
 def with_result_collection(self):return self
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def __iter__(self):return iter([])
 def get_final_result(self):return SimpleNamespace(session_id='synthetic')
class Worker:
 def __init__(self,answer='{"kind":"answer","answer":"Верно"}'):self.calls=0;self.boots=0;self.answer=answer;self.settings=None;self.fail=False
 def sdk(self):return SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(create=self.create))))
 def create(self,**kw):self.boots+=1;self.settings=kw;return Events()
 def generate(self,*a):
  self.calls+=1
  if self.fail:raise TimeoutError()
  return self.answer
 def recover(self,state):return None
def answer(v):
 if v.get('kind')!='answer':raise ValueError('kind')
 return v
class CoreTests(unittest.TestCase):
 def test_active_policy_is_not_shadow(self):
  db=DB();self.assertFalse(active(db));db.d[POLICY]['status']='active';self.assertTrue(active(db))
 def test_completed_turn_reused_without_model_or_bootstrap(self):
  db=DB();w=Worker();c=Core(db,w)
  first,_=c.ask('id','analysis',{'facts':3},{'kind':'answer'},answer,True)
  second,_=c.ask('id','analysis',{'facts':3},{'kind':'answer'},answer,True)
  self.assertEqual(first,second);self.assertEqual(1,w.calls);self.assertEqual(1,w.boots)
  self.assertEqual({'type':'none'},w.settings['environment']);self.assertNotIn('tools',w.settings['agent'])
 def test_uncertain_turn_is_get_recovered_without_resubmission(self):
  db=DB();w=Worker();w.fail=True;c=Core(db,w)
  for _ in range(2):
   with self.assertRaises(RuntimeError):c.ask('id','analysis',{}, {},answer,True)
  self.assertEqual(1,w.calls);self.assertEqual(1,w.boots)
 def test_shadow_cannot_publish_as_active_without_force(self):
  with self.assertRaises(RuntimeError):Core(DB(),Worker()).ask('x','x',{}, {},answer)
 def test_cross_cabinet_policy_rejected(self):
  db=DB();db.d[POLICY]['cabinet']='other'
  with self.assertRaises(ValueError):Core(db,Worker()).ask('x','x',{}, {},answer,True)
 def test_malformed_output_never_calls_old_model(self):
  db=DB();w=Worker('not json')
  with self.assertRaises(ValueError):Core(db,w).ask('x','x',{}, {},answer,True)
  self.assertTrue(any(v.get('status')=='invalid_output'for v in db.d.values()if isinstance(v,dict)))
class ContractTests(unittest.TestCase):
 def fixture(self):
  action=dict(id='1:2',kind='ad_set_bid',campaign_id=1,nm_id=2,old_minor=31,target_minor=28,placement='search')
  cov={k:dict(status='checked',note='Проверено')for k in ('raise','add','reduce','exclude')}
  return action,dict(kind='advertising_review',decisions=[dict(id='1:2',note='Снизить')],directions=cov,research=[])
 def test_action_parameters_cannot_be_changed_by_model(self):
  a,v=self.fixture();v['decisions'][0]['target_minor']=99
  with self.assertRaises(ValueError):ad_validate(v,{'1:2':a},{1},{2:'bag'})
 def test_all_directions_required_even_when_no_growth_ready(self):
  a,v=self.fixture();del v['directions']['add']
  with self.assertRaises(ValueError):ad_validate(v,{'1:2':a},{1},{2:'bag'})
 def test_unknown_or_duplicate_selection_rejected(self):
  for rows in ([dict(id='missing',note='x')],[dict(id='1:2',note='x')]*2):
   a,v=self.fixture();v['decisions']=rows
   with self.assertRaises(ValueError):ad_validate(v,{'1:2':a},{1},{2:'bag'})
 def test_unknown_research_subject_rejected(self):
  a,v=self.fixture();v['research']=[dict(nm_id=999,campaign_id=1,direction='raise',note='x')]
  with self.assertRaises(ValueError):ad_validate(v,{'1:2':a},{1},{2:'bag'})
 def test_price_evidence_rows_are_identified_without_changing_numbers(self):
  text='Артикул | Цена\n--- | ---\n1-Bag-black | 100 → 105\n2-Bag-white | 200 → 210'
  rows,tables,plain=price_parts(text)
  self.assertEqual(2,len(rows));self.assertEqual(1,len(tables));self.assertFalse(plain)
 def test_read_only_scope_and_date_window(self):
  good=dict(kind='read',topic='stock',nm_ids=[1535337770],date_from='2026-11-03',date_to='2026-11-03')
  self.assertEqual(good,validate_read(good,date(2026,11,3)))
  for change in (dict(topic='set_price'),dict(nm_ids=[True]),dict(date_to='2026-11-04'),dict(date_from='2026-09-01')):
   with self.assertRaises(ValueError):validate_read(good|change,date(2026,11,3))
if __name__=='__main__':unittest.main()
