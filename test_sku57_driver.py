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
  p=self.port();calls=[];action=dict(id='a',chat_id=7,specification=dict(cabinet='token_2',campaign_id=39410834,nm_id=1007948808))
  send=lambda chat,text:(calls.append(chat) or 123)
  self.assertEqual(m.notify_recovery_incident(p,action,send,datetime.now(timezone.utc))['status'],'confirmed')
  m.notify_recovery_incident(p,action,send,datetime.now(timezone.utc));self.assertEqual(calls,[7])
 def test_notice_unknown_not_repeated(self):
  p=self.port();calls=[]
  def send(chat,text):calls.append(chat);raise TimeoutError('lost response')
  m.notify_recovery_incident(p,dict(id='a',chat_id=7,specification=dict(cabinet='token_2',campaign_id=39410834,nm_id=1007948808)),send,datetime.now(timezone.utc))
  self.assertEqual(p.state['incident_notice']['status'],'uncertain')
  m.notify_recovery_incident(p,dict(id='a',chat_id=7,specification=dict(cabinet='token_2',campaign_id=39410834,nm_id=1007948808)),send,datetime.now(timezone.utc));self.assertEqual(len(calls),1)
 def test_notice_no_storage_no_send(self):
  calls=[]
  with self.assertRaises(RuntimeError):m.notify_recovery_incident(self.port(True),dict(id='a',chat_id=7,specification=dict(cabinet='token_2',campaign_id=39410834,nm_id=1007948808)),lambda *a:calls.append(a),datetime.now(timezone.utc))
  self.assertEqual(calls,[])
 def fixture(self,status='done',lease_due=None):
  import copy
  now=datetime(2026,10,16,13,tzinfo=timezone.utc)
  watch=dict(id='w',status='active',campaign_id=39410834,nm_id=1007948808,chat_id=7,sender_id=8,policy=dict(mode='sku_membership_recovery',action_id='a',executor_job_id=9,approved_digest='d',backup_operator_id=8))
  action=dict(id='a',job_id=9,chat_id=7,sender_id=8,approved_by=8,digest='d',specification=dict(cabinet='token_2',campaign_id=39410834,nm_id=1007948808,execution_authorized=True,restore_authorized=True))
  job=dict(id=9,status=status,lease_token='old',lease_until=lease_due,request_text='/_sku57_reserved_recovery a')
  class Store:
   calls=[]
   def registration(self):return dict(chat_id=7,registered_by_user_id=8)
   def db(self,method,table,**kw):
    self.calls.append((method,table,kw))
    if method=='GET':return copy.deepcopy({'advertising_agent_watches':[watch],'advertising_agent_actions':[action],'advertising_agent_jobs':[job]}[table])
    if method=='PATCH':job.update(kw['body']);return [copy.deepcopy(job)]
    raise AssertionError('INSERT forbidden')
  class Actions:
   stepped=0
   def fingerprint(self,spec):return 'd'
   def due_sku_membership_recoveries(self,rows,now):return [w for w in rows if w['status']=='active']
   def sku_membership_watch_step(self,action,watch,port,now,**kw):
    self.stepped+=1;return dict(watch,state=dict(notification_pending=False))
  return now,watch,action,job,Store(),Actions()
 def invoke(self,f):
  now,w,a,j,s,ac=f
  with patch.dict(os.environ,{'ADVERTISING_EXECUTION_ENABLED':'true'}):
   return m.resume_existing(s,ac,now,enabled=True,port_factory=lambda *a,**kw:object())
 def test_reserved_idle_job_is_reused(self):
  f=self.fixture();self.invoke(f);self.assertEqual(f[-1].stepped,1);self.assertEqual(f[3]['status'],'done')
 def test_unexpired_lease_not_stolen(self):
  f=self.fixture('running','2026-10-16T14:00:00+00:00');self.invoke(f);self.assertEqual(f[-1].stepped,0)
 def test_expired_lease_resumed(self):
  f=self.fixture('running','2026-10-16T12:00:00+00:00');self.invoke(f);self.assertEqual(f[-1].stepped,1);self.assertNotEqual(f[3]['lease_token'],'old')
 def test_digest_mismatch_no_claim(self):
  f=self.fixture();f[1]['policy']['approved_digest']='other'
  with self.assertRaises(PermissionError):self.invoke(f)
  self.assertFalse(any(m=='PATCH' for m,t,k in f[-2].calls))
 def test_backup_not_owner_no_claim(self):
  f=self.fixture();f[1]['policy']['backup_operator_id']=99
  with self.assertRaises(PermissionError):self.invoke(f)
 def test_pending_generic_job_not_repurposed(self):
  f=self.fixture('pending')
  with self.assertRaises(PermissionError):self.invoke(f)
 def test_existing_authority_required(self):
  f=self.fixture();f[2]['specification']['restore_authorized']=False
  with self.assertRaises(PermissionError):self.invoke(f)


class ScopeDriver(Driver):
 def test_valid_other_watch_cannot_drive_action(self):
  f=self.fixture();f[1]['nm_id']=7
  with self.assertRaises(PermissionError):self.invoke(f)
  self.assertFalse(any(method=='PATCH' for method,table,kw in f[-2].calls))
 def test_campaign_conflict_no_mutation(self):
  f=self.fixture();original=f[-2].db
  def db(method,table,**kw):
   if method=='GET' and table=='advertising_agent_watches' and kw.get('params',{}).get('select')=='id':
    return [{'id':'w'},{'id':'employee-or-second-test'}]
   return original(method,table,**kw)
  f[-2].db=db
  with self.assertRaises(PermissionError):self.invoke(f)
  self.assertEqual(f[-1].stepped,0)
  self.assertFalse(any(method=='PATCH' for method,table,kw in f[-2].calls))
