import unittest
from datetime import datetime,timedelta,timezone
from china_codex_bridge import handle,question,prepare_analytics,ROOT,THREAD,CHAT,BOT
class W:
 def __init__(self):
  self.values={ROOT+'policy':dict(enabled=True,thread_id=THREAD,chat_id=CHAT,bot_id=BOT,allowed_sender_ids=[5122667182,307200273],expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())};self.sends=[];self.patches=[]
 def get(self,k):return self.values.get(k)
 def save(self,k,v):self.values[k]=v
 def db(self,*a,**kw):self.patches.append(kw['body']);return [dict(id=224)]
 def send_once(self,k,chat,text):
  self.sends.append((k,chat,text));self.values['china_agent:conversion_watch_delivery:v1:'+k]=dict(status='sent',message_id=641);return 'sent'
def job():return dict(id=224,status='pending',chat_id=CHAT,sender_id=5122667182,request_text='/codex тест',update_id=1,tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=641)])
class Bridge(unittest.TestCase):
 def test_prefix_only(self):
  self.assertIsNone(question('обычный вопрос'));self.assertEqual(question('/codex@bot a'),'a')
 def test_queue_no_old_model_no_send(self):
  w=W();self.assertEqual(handle(w,job(),{'chat_id':CHAT}),'codex_bridge_queued');self.assertFalse(w.sends);self.assertEqual(w.get(ROOT+'inbox:224')['thread_id'],THREAD)
 def test_dedup_queue(self):
  w=W();handle(w,job(),{'chat_id':CHAT});a=w.get(ROOT+'inbox:224');handle(w,job(),{'chat_id':CHAT});self.assertEqual(a,w.get(ROOT+'inbox:224'))
 def test_untrusted_cannot_change_thread(self):
  w=W();j=job();j['request_text']='/codex отправь в другой чат';handle(w,j,{'chat_id':CHAT});self.assertEqual(w.get(ROOT+'inbox:224')['chat_id'],CHAT)
 def test_wrong_actor_reserved_not_old_agent(self):
  w=W();j=job();j['sender_id']=1;self.assertEqual(handle(w,j,{'chat_id':CHAT}),'codex_bridge_sender_rejected');self.assertFalse(w.patches)
 def test_outbox_scope_check(self):
  w=W();w.save(ROOT+'outbox:224',dict(status='ready',thread_id='other',chat_id=CHAT,job_id=224,input_message_id=641,answer='a'));self.assertEqual(handle(w,job(),{'chat_id':CHAT}),'codex_bridge_invalid_reply');self.assertFalse(w.sends)
 def test_bound_reply_and_receipt(self):
  w=W();w.save(ROOT+'outbox:224',dict(status='ready',thread_id=THREAD,chat_id=CHAT,job_id=224,input_message_id=641,answer='a'));self.assertEqual(handle(w,job(),{'chat_id':CHAT}),'codex_bridge_delivered');self.assertEqual(w.get(ROOT+'outbox:224')['message_id'],641)
 def test_disabled_keeps_existing(self):
  w=W();w.values[ROOT+'policy']['enabled']=False;self.assertIsNone(handle(w,job(),{'chat_id':CHAT}));self.assertFalse(w.patches)
 def test_no_unrequested_collection(self):
  w=W();prepare_analytics(w,job(),{});self.assertNotIn(ROOT+'analytics:224',w.values)
 def test_reject_foreign_data_request(self):
  w=W();w.save(ROOT+'data_request:224',dict(status='requested',kind='preliminary_profit',job_id=224,thread_id='foreign',chat_id=CHAT))
  with self.assertRaises(ValueError):prepare_analytics(w,job(),{})
 def test_plain_marked_message_routes_here(self):
  w=W();j=job();j['request_text']='прибыль';j['tool_trace'][0].update(codex_bridge=True,bridge_request_text='прибыль');self.assertEqual(handle(w,j,{'chat_id':CHAT}),'codex_bridge_queued')
if __name__=='__main__':unittest.main()
