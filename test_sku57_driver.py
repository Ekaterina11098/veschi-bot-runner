import importlib.util,unittest,os
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
s=importlib.util.spec_from_file_location('driver',Path(__file__).with_name('advertising_sku57_recovery_owner.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Closed:
 def __getattr__(self,key):raise AssertionError('No side effects when disabled')
class Driver(unittest.TestCase):
 def test_off_no_reads_writes(self):self.assertEqual(m.resume_existing(Closed(),Closed(),datetime.now(timezone.utc))['wb_calls'],0)
 def test_global_disabled(self):
  with patch.dict(os.environ,{'ADVERTISING_EXECUTION_ENABLED':'false'}):
   with self.assertRaises(PermissionError):m.resume_existing(Closed(),Closed(),datetime.now(timezone.utc),enabled=True)
 def test_no_new_rows_or_generic_claim(self):
  source=Path(__file__).with_name('advertising_sku57_recovery_owner.py').read_text()
  self.assertNotIn("store.db('POST'",source);self.assertNotIn('claim_advertising_agent_job',source)
 def test_no_expiry_filter(self):
  source=Path(__file__).with_name('advertising_sku57_recovery_owner.py').read_text();self.assertNotIn("'expires_at'",source)
 def port(self,storage_fails=False):
  import copy
  class Port:
   state={'revision':1,'phase':'conflict','incident':'employee changed target'}
   def load(self,aid):return copy.deepcopy(self.state)
   def cas(self,aid,revision,value):
    if storage_fails:raise RuntimeError('storage unavailable')
    if revision!=self.state['revision']:return False
    self.state=copy.deepcopy(value);return True
   def fenced(self,aid):return True
  return Port()
 def test_notice_confirmed_once(self):
  p=self.port();calls=[];action=dict(id='a',chat_id=7)
  send=lambda chat,text:(calls.append(chat) or 123)
  self.assertEqual(m.notify_recovery_incident(p,action,send,datetime.now(timezone.utc))['status'],'confirmed')
  m.notify_recovery_incident(p,action,send,datetime.now(timezone.utc));self.assertEqual(calls,[7])
 def test_notice_unknown_not_repeated(self):
  p=self.port();calls=[]
  def send(chat,text):calls.append(chat);raise TimeoutError('lost response')
  m.notify_recovery_incident(p,dict(id='a',chat_id=7),send,datetime.now(timezone.utc))
  self.assertEqual(p.state['incident_notice']['status'],'uncertain')
  m.notify_recovery_incident(p,dict(id='a',chat_id=7),send,datetime.now(timezone.utc));self.assertEqual(len(calls),1)
 def test_notice_no_storage_no_send(self):
  calls=[]
  with self.assertRaises(RuntimeError):m.notify_recovery_incident(self.port(True),dict(id='a',chat_id=7),lambda *a:calls.append(a),datetime.now(timezone.utc))
  self.assertEqual(calls,[])
if __name__=='__main__':unittest.main()
