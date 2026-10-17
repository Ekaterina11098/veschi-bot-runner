"""Verify deeper saved-data dialogue without any incoming job creation or sending."""
import os,sys,json,copy,subprocess,requests
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store,conversation as c
from stock_deploy_support import seal
proof=dict(complete=False,simulation=True,source_calls=0,model_calls=0,telegram_sends=0,wb_writes=0)
try:
 result=subprocess.run([sys.executable,'-c',"import socket,unittest,sys\ndef deny(*a,**k):raise AssertionError(\"Offline test network forbidden\")\nsocket.socket.connect=deny\nloader=unittest.TestLoader();sys.path.insert(0,\"tests\")\nimport test_advertising_conversation as old\nsuite=unittest.TestSuite([loader.discover(\"tests\",pattern=\"test_advertising_saved_dialogue.py\"),loader.loadTestsFromTestCase(old.ConversationTests)])\nresult=unittest.TextTestRunner(verbosity=2).run(suite)\nsys.exit(not result.wasSuccessful())\n"],cwd='private-source')
 proof['regression_passed']=result.returncode==0
 if result.returncode:raise RuntimeError('Free dialogue regression failed')
 native=requests.sessions.Session.request
 host=urlparse(os.environ['SUPABASE_URL']).hostname
 def guard(self,method,url,*args,**kwargs):
  if method.upper()!='GET' or urlparse(url).hostname!=host:raise RuntimeError('Only retained database GET permitted')
  return native(self,method,url,*args,**kwargs)
 requests.sessions.Session.request=guard
 parent=store.db('GET','advertising_agent_jobs',params={'id':'eq.33','select':'*','limit':1})[0]
 probe=copy.deepcopy(parent);probe['id']=34;probe['request_text']='А почему?'
 probe['delivery']=dict(route='saved-dialog-v1',incoming_message_id=0,reply_context=dict(message_id=parent['delivery']['answer_message_id'],text=parent['answer'],is_bot=True))
 def no_model(_):raise RuntimeError('No model for exact saved arithmetic')
 answer,trace=c.run_saved_dialog(probe,no_model)
 checks=dict(differs_from_initial=answer!=parent['answer'],has_deeper_reasoning='Углублю объяснение' in answer,
  exact_parent=probe['delivery'].get('context_parent_job_id')==33,
  explicit_reply_resolution=probe['delivery'].get('context_resolution')=='telegram_reply',
  no_new_cause='Называть одну из них причиной пока нельзя' in answer)
 proof.update(complete=all(checks.values()),checks=checks,automatic_followup=answer,context=probe['delivery'],trace=trace,source_sha=os.environ['ADVERTISING_DIALOG_SOURCE_SHA'])
except Exception as exc:proof.update(error_type=type(exc).__name__,error=str(exc)[:180])
seal('advertising-dialog-activation',proof)
print(json.dumps({k:proof.get(k) for k in ('complete','regression_passed','simulation','checks','source_calls','model_calls','telegram_sends','wb_writes','error')}))
if not proof['complete']:raise SystemExit(1)
