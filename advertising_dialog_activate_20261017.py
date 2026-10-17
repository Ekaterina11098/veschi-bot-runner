"""Read exact live Reply outcome; never process, regenerate or send."""
import os,sys,json,re,requests
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from stock_deploy_support import seal
proof=dict(complete=False,source_calls=0,model_calls=0,telegram_sends=0,wb_writes=0)
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(self,method,url,*args,**kwargs):
 if method.upper()!='GET' or urlparse(url).hostname!=host:raise RuntimeError('Retained DB reads only')
 return native(self,method,url,*args,**kwargs)
requests.sessions.Session.request=guard
try:
 r=store.registration()
 rows=store.db('GET','advertising_agent_jobs',params={'id':'gt.33','chat_id':'eq.'+str(r['chat_id']),'sender_id':'eq.'+str(r['registered_by_user_id']),'status':'eq.done','delivery->>route':'eq.saved-dialog-v1','select':'id,chat_id,sender_id,update_id,request_text,answer,status,delivery,tool_trace','order':'id.desc','limit':1}) or []
 if len(rows)!=1:raise RuntimeError('Completed live owner follow-up absent')
 job=rows[0];d=job['delivery'];pid=d.get('context_parent_job_id')
 parents=store.db('GET','advertising_agent_jobs',params={'id':'eq.'+str(pid),'chat_id':'eq.'+str(job['chat_id']),'sender_id':'eq.'+str(job['sender_id']),'select':'id,chat_id,sender_id,request_text,answer,status,delivery','limit':1}) or []
 if len(parents)!=1:raise RuntimeError('Exact scoped parent absent')
 parent=parents[0];pd=parent['delivery'];reply=d.get('reply_context') or {}
 config=store.cache_get('advertising:agent_webhook') or {}
 checks=dict(
  short_why=bool(re.fullmatch(r'\s*(?:а\s+)?почему[?! .]*',job['request_text'],re.I)),
  exact_reply=reply.get('message_id')==pd.get('answer_message_id'),
  reply_is_this_bot=reply.get('is_bot') is True and reply.get('sender_id')==config.get('bot_id'),
  recorded_resolution=d.get('context_resolution')=='telegram_reply',
  same_participant=job['sender_id']==parent['sender_id'],
  same_scope=d.get('scope')==pd.get('scope'),
  same_thread=d.get('thread_root')==pd.get('thread_root'),
  deeper_not_repeat=job['answer']!=parent['answer'] and 'Углублю объяснение' in job['answer'],
  funnel_limitation_preserved='не путь одних и тех же покупателей' in job['answer'],
  no_invented_cause='Называть одну из них причиной пока нельзя' in job['answer'],
  confirmed_delivery=d.get('send_state')=='confirmed' and isinstance(d.get('answer_message_id'),int),
  no_new_sources=all(t.get('source_calls',0)==0 and t.get('wb_writes',0)==0 for t in job.get('tool_trace') or []))
 proof.update(complete=all(checks.values()),checks=checks,job=job,parent=parent)
except Exception as exc:proof.update(error_type=type(exc).__name__,error=str(exc)[:160])
seal('advertising-dialog-activation',proof)
print(json.dumps({k:proof.get(k) for k in ('complete','checks','source_calls','model_calls','telegram_sends','wb_writes','error')}))
if not proof['complete']:raise SystemExit(1)
