import unittest,json
from unittest.mock import patch
import china_model_usage as m
class MeterTests(unittest.TestCase):
 def body(self):return dict(model='example',input=[dict(role='user',content='SECRET CHAT'),dict(type='function_call_output',call_id='c1',output='PRIVATE RESULT')],tools=[])
 def response(self):return dict(id='resp_fixture',model='example',status='completed',usage=dict(input_tokens=100,input_tokens_details=dict(cached_tokens=60,cache_write_tokens=20),output_tokens=10,output_tokens_details=dict(reasoning_tokens=4),total_tokens=110))
 def test_counts_and_privacy(self):
  v=m.record(self.body(),self.response(),dict(job_id=1,turn=2),.5)
  self.assertEqual((v['input_tokens'],v['cached_input_tokens'],v['cache_write_input_tokens'],v['reasoning_tokens']),(100,60,20,4))
  self.assertNotIn('SECRET',json.dumps(v));self.assertNotIn('PRIVATE',json.dumps(v));self.assertIsNone(v['cost_usd'])
 def test_missing_not_zero(self):
  v=m.record(self.body(),{}, {},0)
  self.assertIsNone(v['input_tokens']);self.assertIsNone(v['cached_input_tokens']);self.assertEqual(v['usage_status'],'missing_not_zero')
 def test_reported_zero_preserved(self):
  v=m.record({},dict(usage=dict(input_tokens=0,output_tokens=0)),{},0)
  self.assertEqual(v['input_tokens'],0);self.assertEqual(v['usage_status'],'reported')
 def test_logger_failure_never_repeats_or_changes_response(self):
  calls=[];response=self.response()
  def req(body):calls.append(body);return response
  with patch.object(m,'persist',side_effect=RuntimeError('db down')):
   self.assertIs(m.metered_request(req,self.body(),job_id=7),response)
  self.assertEqual(len(calls),1)
 def test_model_failure_not_retried(self):
  calls=[]
  def req(body):calls.append(1);raise TimeoutError()
  with patch.object(m,'persist',return_value=True):
   with self.assertRaises(TimeoutError):m.metered_request(req,self.body())
  self.assertEqual(len(calls),1)
 def test_success_context(self):
  values=[]
  with patch.object(m,'persist',side_effect=lambda v:values.append(v) or True):
   m.metered_request(lambda b:self.response(),self.body(),job_id=7,task_type='bid_plan',turn=3)
  self.assertEqual(values[0]['job_id'],7);self.assertEqual(values[0]['turn'],3)
 def test_idempotent_db_no_credentials_or_content(self):
  import os,sys,types
  requests=types.ModuleType('requests');requests.post=lambda *a,**kw:None
  class R:ok=True
  v=m.record(self.body(),self.response(),{},0)
  with patch.dict(sys.modules,requests=requests),patch.dict(os.environ,SUPABASE_URL='https://example.supabase.co',SUPABASE_SECRET_KEY='sb_secret_fixture'),patch.object(requests,'post',return_value=R()) as post:
   self.assertTrue(m.persist(v))
   args=post.call_args
   self.assertEqual(args.kwargs['json']['cache_key'],m.PREFIX+'resp_fixture')
   self.assertEqual(args.kwargs['params'],dict(on_conflict='cache_key'))
   self.assertNotIn('SECRET CHAT',json.dumps(args.kwargs['json']))
 def test_task_type(self):self.assertEqual(m.task_type('Дай товары которые не имеют заказов 14 дней'),'zero_orders')
if __name__=='__main__':unittest.main()
