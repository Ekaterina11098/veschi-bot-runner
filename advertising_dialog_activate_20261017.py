"""Owner-approved exact deletion, regression and saved answer proof."""
import os,sys,json,copy,subprocess,requests
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store,conversation as c
from stock_deploy_support import seal
proof=dict(complete=False,source_calls=0,wb_writes=0,model_calls=0,telegram_sends=0,deletions=[])
try:
 r=store.registration()
 if r['chat_id']!=-1004378639510:raise RuntimeError('Unexpected registered group')
 token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
 for jid,mid in ((30,5),(31,6)):
  job=store.db('GET','advertising_agent_jobs',params={'id':'eq.'+str(jid),'select':'*','limit':1})[0]
  d=copy.deepcopy(job['delivery'])
  if job['chat_id']!=r['chat_id'] or d.get('send_state')!='confirmed' or d.get('answer_message_id')!=mid or d.get('route')!='saved-dialog-v1':raise RuntimeError('Deletion receipt identity mismatch')
  if d.get('owner_deletion',{}).get('state')=='confirmed':
   proof['deletions'].append(dict(job_id=jid,message_id=mid,state='already_confirmed'));continue
  if d.get('owner_deletion'):raise RuntimeError('Previous deletion uncertain; no blind repeat')
  d['owner_deletion']=dict(state='uncertain',at=store.now().isoformat())
  changed=store.db('PATCH','advertising_agent_jobs',params={'id':'eq.'+str(jid),'delivery->>answer_message_id':'eq.'+str(mid),'select':'delivery'},body={'delivery':d},prefer='return=representation') or []
  if len(changed)!=1:raise RuntimeError('Deletion intent save failed')
  res=requests.post('https://api.telegram.org/bot'+token+'/deleteMessage',json={'chat_id':r['chat_id'],'message_id':mid},timeout=(5,25))
  value=res.json()
  if not(res.ok and value.get('ok') is True and value.get('result') is True):raise RuntimeError('Exact message deletion not confirmed')
  d['owner_deletion']=dict(state='confirmed',at=store.now().isoformat())
  store.db('PATCH','advertising_agent_jobs',params={'id':'eq.'+str(jid)},body={'delivery':d})
  check=store.db('GET','advertising_agent_jobs',params={'id':'eq.'+str(jid),'select':'delivery','limit':1}) or []
  if len(check)!=1 or check[0]['delivery']!=d:raise RuntimeError('Deletion receipt readback mismatch')
  proof['deletions'].append(dict(job_id=jid,message_id=mid,state='confirmed'))
 testcode="import socket,unittest,sys\ndef deny(*a,**k):raise AssertionError(\"Offline test network forbidden\")\nsocket.socket.connect=deny\nloader=unittest.TestLoader();sys.path.insert(0,\"tests\")\nimport test_advertising_conversation as old\nsuite=unittest.TestSuite([loader.discover(\"tests\",pattern=\"test_advertising_saved_dialogue.py\"),loader.loadTestsFromTestCase(old.ConversationTests)])\nresult=unittest.TextTestRunner(verbosity=2).run(suite)\nsys.exit(not result.wasSuccessful())\n"
 result=subprocess.run([sys.executable,'-c',testcode],cwd='private-source')
 proof['regression_passed']=result.returncode==0
 if result.returncode:raise RuntimeError('Free-dialogue answer regression failed')
 job=store.db('GET','advertising_agent_jobs',params={'id':'eq.31','select':'*','limit':1})[0]
 probe=copy.deepcopy(job);probe['request_text']='Почему у 57-NoelBag-burgundy высокий ДРР?'
 def no_model(_):raise RuntimeError('Exact saved arithmetic must not invoke model')
 from analytics.payload_storage import decode_rows
 legacy=decode_rows(store.db('GET','analytics_snapshots',params={'id':'eq.18029','select':'payload','limit':1}) or [])[0]['payload']
 if isinstance(legacy,list):legacy=legacy[0]
 proof['legacy_root_keys']=list(legacy)
 proof['legacy_sections']={k:(list(v)[:50] if isinstance(v,dict) else 'list:'+str(len(v)) if isinstance(v,list) else str(type(v))) for k,v in legacy.items() if k!='daily'}
 proof['legacy_campaign_context']={k:([v2 for v2 in v.get('campaigns',[]) if v2.get('wb_campaign_id')==39410834 or v2.get('campaign_id')==39410834]) for k,v in legacy.items() if isinstance(v,dict) and isinstance(v.get('campaigns'),list)}
 answer,trace=c.run_saved_dialog(probe,no_model)
 proof.update(automatic_answer=answer,trace=trace,complete=True,source_sha=os.environ['ADVERTISING_DIALOG_SOURCE_SHA'])
except Exception as exc:proof.update(error_type=type(exc).__name__,error=str(exc)[:200])
seal('advertising-dialog-activation',proof)
print(json.dumps({k:proof.get(k) for k in ('complete','regression_passed','source_calls','model_calls','telegram_sends','wb_writes','deletions','error')}))
if not proof['complete']:raise SystemExit(1)
