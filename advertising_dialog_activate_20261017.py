"""Read-only evidence for exact two human dialogue questions. No replay or sending."""
import os,sys,json,re,requests
from decimal import Decimal,ROUND_HALF_UP
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as store
from stock_deploy_support import seal
native=requests.sessions.Session.request
host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(self,method,url,*args,**kwargs):
 if method.upper()!='GET' or urlparse(url).hostname!=host or not urlparse(url).path.startswith('/rest/v1/'):raise RuntimeError('Only retained database GET allowed')
 return native(self,method,url,*args,**kwargs)
requests.sessions.Session.request=guard
proof=dict(complete=False,source_calls=0,model_calls=0,telegram_sends=0,wb_writes=0)
try:
 registration=store.registration()
 jobs=store.db('GET','advertising_agent_jobs',params={'id':'in.(32,33)','select':'id,chat_id,sender_id,update_id,request_text,answer,status,created_at,tool_trace,delivery','order':'id.asc','limit':2}) or []
 if len(jobs)!=2:raise RuntimeError('Exact questions absent')
 first,follow=jobs;d1=first['delivery'];d2=follow['delivery']
 def correct_math(answer):
  match=re.search(r'100%:\s*([\d ,]+) ₽ / ([\d ,]+) ₽ = ([\d,]+)%',answer)
  if not match:return False
  values=[Decimal(v.replace(' ','').replace(',','.')) for v in match.groups()]
  return values[1]>0 and (values[0]/values[1]*100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)==values[2]
 checks=dict(
  two_distinct_updates=first['update_id']!=follow['update_id'],
  both_done=all(j['status']=='done' for j in jobs),
  both_confirmed=all(j['delivery'].get('send_state')=='confirmed' and isinstance(j['delivery'].get('answer_message_id'),int) for j in jobs),
  registered_chat_only=all(j['chat_id']==registration['chat_id'] for j in jobs),
  same_participant=first['sender_id']==follow['sender_id'],
  followup_is_why=bool(re.fullmatch(r'\s*а\s+почему[?!.\s]*',follow['request_text'],re.I)),
  exact_reply_link=(d2.get('reply_context') or {}).get('message_id')==d1.get('answer_message_id'),
  same_thread=d1.get('thread_root')==d2.get('thread_root'),
  same_scope=d1.get('scope')==d2.get('scope'),
  both_math_correct=all(correct_math(j['answer']) for j in jobs),
  no_old_positive_cause=all(not any(p in j['answer'].lower() for p in ('высокий дрр свидетельствует о том, что','значительного интереса','конверсионные способности, что повышает')) for j in jobs),
  both_explain_direction=all('рост конверсии или чека снижает ДРР' in j['answer'] and 'рост стоимости перехода увеличивает' in j['answer'] for j in jobs),
  both_separate_unknown_cause=all('Первопричину по ним одним определить нельзя' in j['answer'] for j in jobs),
  both_saved_proposal_not_execution=all('Статус: проект; запуск не согласован' in j['answer'] for j in jobs),
  no_source_calls=all(all(t.get('source_calls',0)==0 and t.get('wb_writes',0)==0 for t in j.get('tool_trace') or []) for j in jobs))
 proof.update(complete=all(checks.values()),checks=checks,jobs=jobs,registration=registration)
except Exception as exc:proof.update(error_type=type(exc).__name__,error=str(exc)[:160])
seal('advertising-dialog-activation',proof)
print(json.dumps({k:proof.get(k) for k in ('complete','checks','source_calls','model_calls','telegram_sends','wb_writes','error')}))
if not proof['complete']:raise SystemExit(1)
