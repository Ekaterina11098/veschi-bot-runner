import copy,unittest
from unittest.mock import patch
from datetime import datetime,timezone
import china_free_diagnostic_repair as r
class W:
 now=datetime(2026,11,10,tzinfo=timezone.utc)
 def __init__(self):
  self.values={};self.sent=[]
  self.original=dict(id=283,chat_id=r.CHAT,sender_id=5122667182,request_text='/codex Почему недоступна',tool_trace=[dict(name='china_saved_question',bot_id=8780468043,message_id=123,codex_bridge=True,bridge_request_text='Почему недоступна')])
 def config(self):return dict(chat_id=r.CHAT,bot_id=8780468043)
 def db(self,*a,**k):return [copy.deepcopy(self.original)]
 def get(self,k):return self.values.get(k)
 def save(self,k,v,**kw):self.values[k]=copy.deepcopy(v);return True
 def send_once(self,key,chat,text):
  self.sent.append(text);self.values['china_agent:conversion_watch_delivery:v1:'+key]=dict(status='sent',chat_id=chat,message_id=999);return 'sent'
class Repair(unittest.TestCase):
 def answer(self,w,job):
  w.save('china_agent:free_diagnostic:v1:283',dict(status='answered'));return 'Проверено'
 def test_delivered_correction_not_replayed_and_original_unchanged(self):
  w=W();original=copy.deepcopy(w.original)
  with patch.object(r,'handle',side_effect=self.answer),patch('china_table_png.delivery_parts',side_effect=lambda w,j,a,s:[a]):
   self.assertEqual(r.repair(w,283)['status'],'delivered')
   self.assertEqual(r.repair(w,283)['status'],'already_delivered')
  self.assertEqual(w.sent,['Проверено']);self.assertEqual(w.original,original)
 def test_foreign_sender_and_changed_frozen_question_rejected(self):
  w=W();w.original['sender_id']=5
  with self.assertRaises(PermissionError):r.repair(w,283)
  w=W();w.values[r.ROOT+'283']=dict(job_id=283,chat_id=r.CHAT,input_message_id=123,question_sha256='wrong',status='prepared')
  with self.assertRaises(PermissionError):r.repair(w,283)
 def test_failed_diagnostic_not_delivered(self):
  w=W()
  with patch.object(r,'handle',return_value='Не удалось'):
   with self.assertRaises(RuntimeError):r.repair(w,283)
  self.assertEqual(w.sent,[])
if __name__=='__main__':unittest.main()
