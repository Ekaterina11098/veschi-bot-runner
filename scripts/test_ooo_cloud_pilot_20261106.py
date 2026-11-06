import unittest,sys,types,json
from decimal import Decimal
stub=types.ModuleType('china_codex_cloud');stub.DB=object;sys.modules['china_codex_cloud']=stub
import ooo_cloud_pilot_20261106 as p
class Memory:
 def __init__(self):self.rows={}
 def get(self,k):return self.rows.get(k)
 def once(self,k,v):
  if k in self.rows:raise RuntimeError('Duplicate')
  self.rows[k]=v
 def update(self,k,v):self.rows[k]=v
class Tests(unittest.TestCase):
 def setUp(self):self.policy={'allowed_senders':[7],'expected_username':'ExampleBot','command_not_before_unix':100}
 def update(self,chat=-1,sender=7,text='/pilot@ExampleBot'):
  return {'update_id':1,'message':{'message_id':4,'date':101,'text':text,'from':{'id':sender},'chat':{'id':chat,'type':'supergroup','title':'private'}}}
 def test_exact_group(self):self.assertEqual(p.select_trigger([self.update()],self.policy)['chat_id'],-1)
 def test_ambiguous_group_stops(self):
  with self.assertRaises(ValueError):p.select_trigger([self.update(-1),self.update(-2)],self.policy)
 def test_wrong_sender_stops(self):
  with self.assertRaises(ValueError):p.select_trigger([self.update(sender=8)],self.policy)
 def test_wrong_command_stops(self):
  with self.assertRaises(ValueError):p.select_trigger([self.update(text='/start')],self.policy)
 def test_cost(self):self.assertEqual(p.cost({'input_tokens':10000,'output_tokens':2000},{'input':10,'output':50,'cached_input':1}),Decimal('.2'))
 def test_invalid_usage(self):
  with self.assertRaises(ValueError):p.cost({'input_tokens':1,'output_tokens':0,'input_tokens_details':{'cached_tokens':2}},{'input':10,'output':50,'cached_input':1})
 def test_no_duplicate_delivery(self):
  c=Memory();calls=[]
  def send(*a):calls.append(1);return {'message_id':25,'chat':{'id':-1}}
  for _ in range(2):p.send_once(c,'receipt','sendMessage',send,-1,{})
  self.assertEqual(len(calls),1)
 def test_uncertain_never_resends(self):
  c=Memory();calls=[]
  def send(*a):calls.append(1);raise TimeoutError()
  for _ in range(2):
   with self.assertRaises(RuntimeError):p.send_once(c,'receipt','sendMessage',send,-1,{})
  self.assertEqual(len(calls),1);self.assertEqual(c.get('receipt')['status'],'uncertain')
 def test_scope(self):
  with self.assertRaises(PermissionError):p.Cache().check('china_agent:outside')
 def test_prompt_bound(self):
  policy={'snapshot':{'day':'2026-11-05','three_days':['2026-11-03','2026-11-05'],'advertising_at':'dated','totals':{'junk':'x'*7000}}}
  with self.assertRaises(ValueError):p.model_message(policy)
 def test_resume_only_pre_model_failure(self):
  s={'status':'attention','last_stage':'starting','model_calls':0,'safe_error':'Expected one authorized pilot group command'}
  self.assertTrue(p.binding_resume_allowed(s,[None,None]))
  self.assertFalse(p.binding_resume_allowed(s,[{'status':'reserved'}]))
  self.assertFalse(p.binding_resume_allowed(s|{'model_calls':1},[]))
  self.assertFalse(p.binding_resume_allowed(s|{'last_stage':'model_submitting'},[]))
if __name__=='__main__':unittest.main()

