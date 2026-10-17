import copy,unittest
from conversion_watches import Worker,question_allowed,question_marker,RECEIPTS
from china_chat_migration import accepted_chat,previous_chats
from test_conversion_watches import Memory,job,CREATE,CFG

LINE={'verified':True,'agent_id':'china','from_chat_id':-99,'to_chat_id':-123,'previous_chat_ids':[-99],'bot_id':9,'owner_user_id':5}

class Migration(unittest.TestCase):
 def db(self,*a,**kw):return [{'payload':LINE}]
 def test_only_verified_scope(self):
  self.assertTrue(accepted_chat(self.db,-99,-123,9,5))
  for old,new,bot,owner in [(-98,-123,9,5),(-99,-123,8,5),(-99,-123,9,6)]:self.assertFalse(accepted_chat(self.db,old,new,bot,owner))
 def test_lineage(self):self.assertEqual(previous_chats(self.db,CFG),[-99])
 def test_old_key_reused(self):
  w=Memory();w.command(job(CREATE));key,watch=w.watches()[0]
  w.mem['china_agent:conversion_watch:v1:-99:5:987']=w.mem.pop(key)
  w.command(job(CREATE,2));self.assertEqual(len(w.watches()),1)
  self.assertEqual(w.watches()[0][1]['id'],watch['id'])
 def test_member_questions_but_owner_commands(self):
  w=Memory();j=job('Почему?',sender=1) if False else job('Почему?')
  j.update(sender_id=6,tool_trace=[{'name':'china_saved_question','message_id':7}])
  self.assertTrue(question_allowed(j,CFG))
  j['chat_id']=-99;self.assertFalse(question_allowed(j,CFG))
  j['chat_id']=-123;j['request_text']=CREATE
  with self.assertRaises(PermissionError):w.command(j)
 def test_watches_use_alias_keep_time(self):
  w=Memory();w.command(job(CREATE));key,watch=w.watches()[0];before=copy.deepcopy(watch)
  def db(method,table,params=None,**kw):
   if params.get('cache_key')=='eq.china_agent:chat_migration:v1:-123':return [{'payload':LINE}]
   if '-99:' in params.get('cache_key',''):return [{'cache_key':'legacy-key','payload':watch}]
   return []
  w.db=db;rows=Worker.watches(w)
  self.assertEqual(rows,[('legacy-key',before)]);self.assertEqual(rows[0][1]['next_at'],before['next_at'])
 def test_question_never_calls_reports_or_collector(self):
  j=job('Покажи данные');j.update(status='pending',tool_trace=[{'name':'china_saved_question','message_id':7}],answer='Сохранённые данные',attempts=0)
  w=Memory();w.reports=lambda:(_ for _ in ()).throw(AssertionError('reports'))
  w.collect=lambda *a:(_ for _ in ()).throw(AssertionError('collect'))
  patches=[]
  def db(method,table,params=None,body=None,**kw):
   if method=='PATCH':patches.append(body);return [j]
   if table=='business_agent_jobs' and params.get('id')=='eq.1':return [j]
   return []
  w.db=db
  self.assertEqual(w.question(1),'sent');self.assertEqual(len(w.sent),1)
  self.assertEqual(w.question(1),'sent');self.assertEqual(len(w.sent),1)
 def test_uncertain_not_resent(self):
  w=Memory();w.transport=lambda *a:(_ for _ in ()).throw(TimeoutError())
  self.assertEqual(w.send_once('question:1:0',-123,'answer'),'uncertain')
  w.transport=w.send;self.assertEqual(w.send_once('question:1:0',-123,'answer'),'uncertain');self.assertEqual(w.sent,[])
 def test_saved_model_only_uses_allowed_read_tools(self):
  w=Memory();j=job('Какие данные доступны?');j['tool_trace']=[{'name':'china_saved_question','message_id':7}]
  calls=[]
  def model(body):
   calls.append(body)
   self.assertNotIn('recover_missing_data',{t['name'] for t in body['tools']})
   self.assertNotIn('forecast_price',{t['name'] for t in body['tools']})
   if len(calls)==1:return {'output':[{'type':'function_call','name':'get_status','arguments':'{}','call_id':'status'}]}
   return {'output':[{'type':'message','content':[{'type':'output_text','text':'Срез недоступен; неизвестное не равно нулю.'}]}]}
  w.model_request=model
  answer,trace=w.saved_question(j,[])
  self.assertEqual(len(calls),2);self.assertEqual(trace[0]['name'],'get_status');self.assertIn('не равно нулю',answer)

if __name__=='__main__':unittest.main()
