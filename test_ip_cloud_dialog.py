import copy,json,unittest,sys,types
from unittest.mock import patch
try:import requests
except ImportError:sys.modules['requests']=types.SimpleNamespace(post=lambda *a,**kw:None)
from ip_cloud_dialog import Budget,Halt,ROOT,MODEL,RESERVE,select_scope,names_from_own,Worker,digest

class FakeState:
 def __init__(self):self.data={ROOT+'policy':{'enabled':True,'model':MODEL,'wb_permission':False}};self.conflict=False
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def row(self,k):return {'payload':self.get(k),'updated_at':'v1'}if k in self.data else None
 def cas(self,k,p,old):
  if self.conflict:return False
  self.data[k]=copy.deepcopy(p);return True

class Tests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict('os.environ',{'OPENAI_API_KEY':'offline-test-placeholder'});self.env.start();self.addCleanup(self.env.stop)
 def test_atomic_conflict_never_authorizes_call(self):
  s=FakeState();s.conflict=True
  with self.assertRaises(Halt):Budget(s).reserve(1)
 def test_uncertain_reservation_blocks_same_question(self):
  s=FakeState();b=Budget(s);b.reserve(1)
  with self.assertRaises(Halt):b.reserve(1)
  self.assertEqual(s.get(ROOT+'ledger')['transfer'],0)
 def test_settlement_includes_reasoning_not_added_twice(self):
  s=FakeState();b=Budget(s);b.reserve(1,True)
  value=b.settle(1,dict(input_tokens=1000,output_tokens=500,output_tokens_details={'reasoning_tokens':400}))
  self.assertEqual(value,7000);self.assertEqual(s.get(ROOT+'ledger')['transfer'],7000)
 def test_monthly_cap_includes_reserved(self):
  s=FakeState();b=Budget(s);b.reserve(1);v=s.data[ROOT+'ledger'];month=next(iter(v['months']));v['months'][month]=10000000-RESERVE+1
  with self.assertRaises(Halt):b.reserve(2)
 def test_daily_cap(self):
  s=FakeState();b=Budget(s)
  for j in range(13):b.reserve(j)
  with self.assertRaises(Halt):b.reserve(99)
 def test_turn_limit_even_cheap_calls(self):
  s=FakeState();b=Budget(s)
  for j in range(20):b.reserve(j);b.settle(j,dict(input_tokens=100,output_tokens=10))
  with self.assertRaises(Halt):b.reserve(21)
 def test_unverifiable_usage_keeps_full_reserve(self):
  s=FakeState();b=Budget(s);b.reserve(1)
  with self.assertRaises(Halt):b.settle(1,dict(input_tokens=8001,output_tokens=3))
  self.assertEqual(s.get(ROOT+'ledger')['jobs']['1']['charged'],RESERVE)
 def test_kill_switch(self):
  s=FakeState();s.data[ROOT+'policy']['enabled']=False
  with self.assertRaises(Halt):Budget(s).reserve(1)
 def test_ambiguous_short_article_not_guessed(self):
  s=select_scope('почему 57?',{'1':'57-NoelBag-burgundy','2':'57-Other'},[])
  self.assertEqual(s['nms'],[1,2])
 def test_full_article_exact(self):
  s=select_scope('57-NoelBag-burgundy в 39410834',{'1':'57-NoelBag-burgundy','2':'57-Other'},[{'campaign_id':39410834}])
  self.assertEqual(s,{'nms':[1],'campaigns':[39410834]})
 def test_own_names_not_profit(self):
  names=names_from_own([{'data':{'data':{'data':[{'nm_id':5,'sa_name':'SKU5','profit':100000}]}}}])
  self.assertEqual(names,{'5':'SKU5'})
 def test_no_blind_telegram_resend(self):
  w=Worker(None)
  with self.assertRaises(Halt):w.deliver({'delivery':{'send_state':'uncertain'}})
 def test_input_preflight_failure_never_calls_paid_model(self):
  w=Worker(None);w.s=FakeState()
  with patch('ip_cloud_dialog.requests.post')as post:
   post.return_value.status_code=503
   with self.assertRaises(Halt):w.generate({'id':1,'request_text':'почему?'},{},False)
   self.assertEqual(post.call_count,1);self.assertEqual(w.model_calls,0)
 def test_model_request_budget_and_output_cap(self):
  w=Worker(None);w.s=FakeState();w.s.put=lambda k,p:None
  class R:
   status_code=200
   def __init__(self,d):self.d=d
   def json(self):return self.d
  results=[R({'input_tokens':300}),R({'status':'completed','model':MODEL,'usage':{'input_tokens':300,'output_tokens':100},'output':[{'type':'message','content':[{'type':'output_text','text':'Проверенный ответ.'}]}]})]
  with patch('ip_cloud_dialog.requests.post',side_effect=results)as post:
   self.assertEqual(w.generate({'id':1,'request_text':'почему?'},{},True),'Проверенный ответ.')
   body=post.call_args_list[1].kwargs['json'];self.assertEqual(body['max_output_tokens'],2000);self.assertFalse(body['store']);self.assertEqual(body['tools'],[])
 def test_incomplete_paid_result_is_not_retried(self):
  w=Worker(None);w.s=FakeState();w.s.put=lambda k,p:None
  class R:
   status_code=200
   def __init__(self,d):self.d=d
   def json(self):return self.d
  with patch('ip_cloud_dialog.requests.post',side_effect=[R({'input_tokens':100}),R({'status':'incomplete','usage':{'input_tokens':100,'output_tokens':2000}})])as post:
   with self.assertRaises(Halt):w.generate({'id':1,'request_text':'почему?'},{},True)
   self.assertEqual(post.call_count,2)

if __name__=='__main__':unittest.main()

