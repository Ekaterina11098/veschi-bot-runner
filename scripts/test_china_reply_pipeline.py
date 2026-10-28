"""Real question() pipeline replay with fake persistence and transport; no credentials or network."""
import copy,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
from conversion_watches import Worker
from test_china_reply_evidence import fixture,job,NOW
class PipelineTests(unittest.TestCase):
 def run_question(self,prepared):
  saved=job();saved.update(agent_id='china',chat_id=-1001,sender_id=7,status='pending',attempts=0,answer='Нет инструмента. Не выполнено.' if prepared else None)
  history=dict(id=3,request_text='Не повторяй прежнее повышение',answer='Ожидается исполнение',tool_trace=[])
  mem=fixture();out=[];recorded=[]
  def db(method,table,params=None,body=None,prefer=None):
   if table=='business_agent_config':return [dict(chat_id=-1001,bot_id=9,owner_user_id=7)]
   if table=='business_agent_jobs':
    if method=='PATCH':saved.update(copy.deepcopy(body));return [copy.deepcopy(saved)]
    return [copy.deepcopy(saved if params.get('select')=='*' else history)]
   if table=='telegram_api_cache' and method=='GET':
    p=mem.get(params['cache_key'][3:]);return [dict(payload=copy.deepcopy(p))] if p else []
   raise AssertionError('Unexpected persistence '+method+' '+table)
  def forbidden(*a,**k):raise AssertionError('External transport is forbidden')
  w=Worker(db,forbidden,now=NOW);w.saved_question=lambda *a:('Нет инструмента. Не выполнено.',[])
  def send(key,chat,text):
   self.assertEqual(saved['answer'],text);out.append(text);return 'sent'
  w.send_once=send
  modules={
   'china_chat_migration':SimpleNamespace(previous_chats=lambda *a:[]),
   'china_shared_memory':SimpleNamespace(record_turn=lambda w,j,a,t:recorded.append(a)),
   'china_table_png':SimpleNamespace(delivery_parts=lambda w,j,a,split:[a]),
   'china_model_transport':SimpleNamespace(ModelResponseError=type('FakeModelResponseError',(Exception,),{}))}
  with patch.dict(sys.modules,modules):result=w.question(4)
  self.assertEqual(result,'sent');self.assertEqual(saved['status'],'done')
  self.assertIn('WB подтвердил 2 из 3',out[0]);self.assertEqual(recorded,out)
  self.assertEqual(mem,fixture())
 def test_existing_prepared_answer_is_rechecked(self):self.run_question(True)
 def test_newly_generated_answer_is_rechecked(self):self.run_question(False)
if __name__=='__main__':unittest.main()
