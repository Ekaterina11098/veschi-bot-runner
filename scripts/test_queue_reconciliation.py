import unittest
from unittest.mock import patch
import china_codex_cloud as c
class DB:
 def __init__(self,rows):self.rows=rows
 def get(self,k):return self.rows.get(k)
 def api(self,*a,**kw):return [dict(id=236)]
 def update(self,k,v,expected=None):
  if expected and self.rows[k]['status']!=expected:return False
  self.rows[k]=v;return True
class Tests(unittest.TestCase):
 def worker(self,extra):
  inbox=dict(job_id=236,status='queued',input_message_id=672)
  key=c.ROOT+'inbox:236';w=c.Worker.__new__(c.Worker);w.db=DB({key:inbox,**extra})
  w.generate=lambda *a:self.fail('Must not call model');return w,key,inbox
 def test_owner_resolved_retires_head_without_resubmission(self):
  w,k,i=self.worker({'china_agent:owner_dialog_resolution:v1:job:236':dict(status='answered_by_owner',chat_id=c.CHAT,message_id=670,receipt_key='receipt'),'receipt':{'status':'edited_verified','message_id':670,'chat_id':c.CHAT}})
  with patch.object(c,'validate',return_value=True):self.assertEqual(w.process(k,i),'owner_resolved')
  self.assertEqual(w.db.get(k)['status'],'owner_resolved')
 def test_missing_receipt_keeps_head_for_review(self):
  w,k,i=self.worker({'china_agent:owner_dialog_resolution:v1:job:236':dict(status='answered_by_owner',chat_id=c.CHAT,message_id=670,receipt_key='missing')})
  with patch.object(c,'validate',return_value=True),self.assertRaises(RuntimeError):w.process(k,i)
  self.assertEqual(w.db.get(k)['status'],'queued')
 def test_ready_outbox_retires_head_but_does_not_send(self):
  w,k,i=self.worker({c.ROOT+'outbox:236':dict(status='ready',job_id=236,chat_id=c.CHAT,thread_id=c.THREAD,input_message_id=672)})
  with patch.object(c,'validate',return_value=True):self.assertEqual(w.process(k,i),'existing_outbox')
  self.assertEqual(w.db.get(k)['status'],'answered')
 def test_wrong_outbox_scope_not_hidden(self):
  w,k,i=self.worker({c.ROOT+'outbox:236':dict(status='delivered',job_id=236,chat_id=1,thread_id=c.THREAD,input_message_id=672)})
  with patch.object(c,'validate',return_value=True),self.assertRaises(RuntimeError):w.process(k,i)
  self.assertEqual(w.db.get(k)['status'],'queued')
if __name__=='__main__':unittest.main()

