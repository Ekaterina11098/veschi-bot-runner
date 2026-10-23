import unittest,types,sys,copy
from unittest.mock import patch,Mock
from datetime import datetime,timezone
from test_china_analytic_dialog import W,Rules
from china_model_transport import ModelResponseError
import china_analytic_dialog as a
from conversion_watches import Worker

class CheckpointTests(unittest.TestCase):
 def test_product_projection_reuses_one_full_source_collection(self):
  w=W();w.catalog=lambda:[('100','one-bag'),('200','two-bag')];an=a.Analyst(w,{},[])
  with patch.object(an,'collect',return_value=dict(source='MPStats',rows=[dict(nm_id=100),dict(nm_id=200)])) as collect:
   first=an.live('products',[100],None,None);second=an.live('products',[200],None,None)
  self.assertEqual(first['rows'],[dict(nm_id=100)]);self.assertEqual(second['rows'],[dict(nm_id=200)]);self.assertEqual(collect.call_count,1)
 def test_resume_keeps_completed_tool_call_without_repeating(self):
  w=W();count=[]
  def model(body):
   count.append(1)
   if len(count)==1:return dict(output=[dict(type='function_call',name='calculate',arguments='{"expression":"2+2"}',call_id='calc')])
   raise ModelResponseError(429,dict(code='rate_limit_exceeded'))
  w.model_request=model;job=dict(id=1,chat_id=-1,request_text='Посчитай 2+2',tool_trace=[])
  with patch.dict(sys.modules,Rules().modules()):
   with self.assertRaises(ModelResponseError):a.answer(w,job,[])
   w.model_request=lambda body:dict(output=[dict(type='message',content=[dict(type='output_text',text='4')])])
   answer,trace=a.answer(w,job,[])
  self.assertEqual(answer,'4');self.assertEqual(sum(t['name']=='calculate' for t in trace),1)
 def test_transient_failure_returns_same_job_to_pending_without_delivery(self):
  job=dict(id=1,agent_id='china',chat_id=-1,sender_id=2,status='pending',attempts=0,request_text='Разбери падение заказов',tool_trace=[dict(name='china_saved_question')]);state={};sent=[]
  def db(method,table,params=None,body=None,**kw):
   if table!='business_agent_jobs':return []
   if method=='PATCH':job.update(body);return [copy.deepcopy(job)]
   return [copy.deepcopy(job)] if (params or {}).get('id')=='eq.1' else []
  w=Worker(db,lambda *args:sent.append(args),now=datetime.now(timezone.utc));w.config=lambda:dict(chat_id=-1);w.get=lambda key:state.get(key);w.save=lambda k,v:state.update({k:v})
  w.saved_question=Mock(side_effect=ModelResponseError(429,dict(code='rate_limit_exceeded'),300))
  module=types.ModuleType('china_chat_migration');module.previous_chats=lambda *args:[]
  with patch.dict(sys.modules,{'china_chat_migration':module}):self.assertEqual(w.question(1),'model_deferred')
  self.assertEqual(job['status'],'pending');self.assertFalse(sent);self.assertIsNone(job.get('answer'))

if __name__=='__main__':unittest.main()
