import unittest,json,types,sys,hashlib,base64,datetime
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).parent
ASSET=HERE/('audit_ooo_report_templates.json'if(HERE/'audit_ooo_report_templates.json').exists()else'ooo_report_templates.json')
WORKER=HERE/('audit_ooo_daily_reports.py'if(HERE/'audit_ooo_daily_reports.py').exists()else'ooo_daily_reports.py')
ASSETS=json.loads(ASSET.read_text(encoding='utf-8'))
class Recovery(unittest.TestCase):
 def setup_sender(self,existing=None,fail_me=False):
  root='ooo_agent:morning:2026-11-11:telegram';raw=b'\x89PNG\r\n\x1a\nfixture';h=hashlib.sha256(raw).hexdigest();self.photos=[];self.fail_me=fail_me
  self.data={root+':input':{'owner_approved':True,'chat_id':-1003987998401,'kinds':['advertising','budgets'],'images':[{'kind':k,'chunk_keys':['chunk'],'bytes':len(raw),'sha256':h}for k in ['advertising','budgets']]},'chunk':{'data':base64.b64encode(raw).decode()},'ooo_agent:morning:2026-11-11:report':{'status':'ready'},'ooo_agent:telegram_group:v1':{'status':'verified','chat_id':-1003987998401}}
  if existing:
   self.data[root+':execution']={'status':'attention','receipts':[]}
   self.data[root+':delivery:advertising']={'status':existing,'message_id':41,'chat_id':-1003987998401,'sha256':h}
  data=self.data
  class DB:
   def get(s,k):return data.get(k)
   def once(s,k,v):
    if k in data:raise RuntimeError('duplicate key')
    data[k]=v
   def update(s,k,v):data[k]=v
  def post(url,**kw):
   if url.endswith('/getMe'):
    if self.fail_me:self.fail_me=False;raise TimeoutError()
    v={'result':{'id':9167526388,'username':'VESCHI_OOO_bot'}}
   else:self.photos.append(kw['files']['photo'][0]);v={'result':{'message_id':50+len(self.photos),'chat':{'id':-1003987998401}}}
   return types.SimpleNamespace(status_code=200,json=lambda:v)
  mods={'china_codex_cloud':types.SimpleNamespace(DB=DB,stamp=lambda:'now'),'requests':types.SimpleNamespace(post=post),'ooo_report_command':types.SimpleNamespace(bind_delivery=lambda*a:None)}
  ns={'__name__':'sender_test'}
  with patch.dict(sys.modules,mods),patch.dict('os.environ',{'GITHUB_RUN_ID':'test','OOO_TELEGRAM_BOT_TOKEN':'fixture'}):
   exec(ASSETS['sender'],ns)
   self.run_sender=lambda:None
   def run():
    with patch.dict(sys.modules,mods),patch.dict('os.environ',{'GITHUB_RUN_ID':'test','OOO_TELEGRAM_BOT_TOKEN':'fixture'}):ns['run']()
   return run
 def test_preflight_timeout_recovers_without_lost_delivery(self):
  run=self.setup_sender(fail_me=True);run();self.assertEqual(self.photos,[]);run();self.assertEqual(len(self.photos),2)
 def test_partial_pair_resumes_only_missing_png(self):
  run=self.setup_sender('sent');run();self.assertEqual(self.photos,['budgets.png'])
 def test_unknown_outcome_is_never_replayed(self):
  run=self.setup_sender('uncertain');run();self.assertEqual(self.photos,[])
 def test_submitting_outcome_is_never_replayed(self):
  run=self.setup_sender('submitting');run();self.assertEqual(self.photos,[])
 def test_verified_pair_is_not_sent_twice(self):
  run=self.setup_sender();run();run();self.assertEqual(len(self.photos),2)
 def test_midday_runs_when_morning_fails(self):
  mods={'china_codex_cloud':types.SimpleNamespace(DB=lambda:types.SimpleNamespace(get=lambda k:{'status':'sent'},update=lambda *a:None),stamp=lambda:'now'),'ooo_daily_review':types.SimpleNamespace(review=lambda*a:None)}
  ns={'__name__':'worker_test','__file__':str(WORKER)}
  with patch.dict(sys.modules,mods):exec(WORKER.read_text(encoding='utf-8'),ns)
  calls=[]
  def worker(slot,**kw):
   calls.append(slot)
   if slot=='morning':raise TimeoutError()
   return {'status':'verified'}
  ns['worker']=worker
  class Clock(datetime.datetime):
   @classmethod
   def now(cls,tz=None):return cls(2026,11,15,15,1,tzinfo=tz)
  with patch.object(ns['datetime'],'datetime',Clock),patch.dict('os.environ',{},clear=True):
   with self.assertRaises(RuntimeError):ns['run']()
  self.assertEqual(calls,['morning','midday'])
 def test_prepared_artifact_is_not_sent_before_target_time(self):
  def get(k):
   if k.endswith(':policy'):return {'enabled':True}
   if k.endswith(':report'):return {'status':'ready'}
   return None
  mods={'china_codex_cloud':types.SimpleNamespace(DB=lambda:types.SimpleNamespace(get=get),stamp=lambda:'now'),'ooo_daily_review':types.SimpleNamespace(review=lambda*a:None)}
  ns={'__name__':'worker_test','__file__':str(WORKER)}
  with patch.dict(sys.modules,mods):exec(WORKER.read_text(encoding='utf-8'),ns)
  ns['execute']=lambda*a:(_ for _ in()).throw(AssertionError('Send attempted before target'))
  self.assertEqual(ns['worker']('morning',day='2026-11-14',prepare_only=True)['status'],'already_prepared')
if __name__=='__main__':unittest.main()