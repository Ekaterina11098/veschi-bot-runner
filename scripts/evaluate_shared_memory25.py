"""Replay private real questions through the production model; no Telegram/WB network."""
import os,json,copy,re,hashlib,time
from datetime import datetime,timezone
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
import requests
from china_price_apply import IO
from conversion_watches import runtime,question_request
from china_analytic_dialog import answer
ROOT='china_agent:memory_eval:2026-10-25:'
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
 io=IO();suite=io.get(ROOT+'cases:v1');assert suite['no_telegram'] and suite['no_wb']
 phase=os.environ.get('EVAL_PHASE','before');key=ROOT+'results:'+phase
 results=io.get(key) or dict(status='running',phase=phase,model='gpt-6.1-sol',cases=[],telegram_sends=0,wb_requests=0)
 for case in suite['cases']:
  for pattern in case.get('required',[])+case.get('forbidden',[]):re.compile(pattern)
 frozen=datetime.fromisoformat(os.environ.get('EVAL_NOW',suite['fixed_now']))
 class FrozenDateTime(datetime):
  @classmethod
  def now(cls,tz=None):return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)
 original=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
 blocked=[]
 def guard(session,method,url,*args,**kwargs):
  u=urlparse(url)
  if u.hostname==host and method.upper()=='GET':return original(session,method,url,*args,**kwargs)
  if u.hostname==host and u.path=='/rest/v1/telegram_api_cache':
   body=kwargs.get('json') or {};filters=parse_qs(u.query)
   if (method.upper()=='POST' and str(body.get('cache_key','')).startswith(ROOT)) or (method.upper()=='PATCH' and filters.get('cache_key',[''])[0].startswith('eq.'+ROOT)):return original(session,method,url,*args,**kwargs)
  if u.hostname=='api.openai.com' and u.path=='/v1/responses' and method.upper()=='POST':return original(session,method,url,*args,**kwargs)
  blocked.append(dict(host=u.hostname,method=method.upper()));raise PermissionError('Evaluation blocked external transport')
 def persist():
  value=json.loads(json.dumps(results,default=str))
  if io.get(key):io.put(key,value)
  else:assert io.create(key,value)
 persist()
 memory={};read_cache={}
 selected=set(filter(None,os.environ.get('EVAL_CASE_IDS','').split(',')))
 for index,case in enumerate(suite['cases']):
  if selected and case['id'] not in selected:continue
  if any(r['id']==case['id'] for r in results['cases']):continue
  results['active_case']=case['id'];results['active_stage']='initializing';persist()
  w=runtime();w.now=frozen;original_get=w.get;original_db=w.db
  def db_read(method,table,params=None,**kwargs):
   if method.upper()!='GET':raise PermissionError('Evaluation forbids production writes')
   signature=json.dumps([table,params],sort_keys=True)
   if signature not in read_cache:read_cache[signature]=original_db(method,table,params=params,**kwargs)
   return copy.deepcopy(read_cache[signature])
  w.db=db_read
  w.get=lambda k:copy.deepcopy(memory[k]) if k in memory else original_get(k)
  def save(k,v,insert=False):
   if insert and k in memory:return False
   memory[k]=copy.deepcopy(v);return True
  w.save=save;w.transport=lambda *a,**kw:(_ for _ in ()).throw(PermissionError('Evaluation forbids Telegram'))
  w.collect=None
  def model_request(body):
   results['active_stage']='model';results['active_input_chars']=len(json.dumps(body['input'],ensure_ascii=False));results['model_calls']=results.get('model_calls',0)+1;persist()
   started=time.monotonic()
   value=question_request(body)
   results['last_model_seconds']=round(time.monotonic()-started,2);results['active_stage']='tools';persist()
   return value
  w.model_request=model_request
  job=dict(id=-int(os.environ.get('GITHUB_RUN_ID','1'))*100-index,agent_id='china',chat_id=-1004342917488,sender_id=5122667182,request_text=case['question'],tool_trace=[])
  before=len(blocked)
  try:
   with patch('requests.sessions.Session.request',guard),patch('china_advertising_intraday.datetime',FrozenDateTime):
    value=answer(w,job,case.get('history',[]))
   text,trace=value;status='answered'
  except Exception as exc:text='';trace=[];status='error:'+type(exc).__name__
  results.setdefault('raw_answers',[]).append(dict(id=case['id'],answer=text,status=status));persist()
  failures=[]
  for pattern in case.get('required',[]):
   if not re.search(pattern,text,re.I|re.S):failures.append('missing:'+pattern)
  for pattern in case.get('forbidden',[]):
   if re.search(pattern,text,re.I|re.S):failures.append('forbidden:'+pattern)
  reports=[]
  for t in trace:
   if t.get('name')=='make_report':
    reports.append(dict(arguments=t.get('arguments'),result=t.get('result')))
  if case.get('require_report') and not any((r.get('result') or {}).get('status')=='ready' for r in reports):failures.append('no_ready_current_report')
  if len(blocked)>before:failures.append('attempted_unneeded_external_read')
  if status!='answered':failures.append(status)
  results['cases'].append(dict(id=case['id'],question=case['question'],history=case.get('history',[]),answer=text,status=status,failures=failures,tools=[dict(name=t.get('name'),arguments=t.get('arguments'),error=t.get('result',{}).get('error') if isinstance(t.get('result'),dict) else None,note=t.get('result',{}).get('note') if isinstance(t.get('result'),dict) else None) for t in trace],reports=reports,blocked=blocked[before:],tool_trace=trace))
  persist()
  print(json.dumps(dict(case_index=index,status=status,failures=len(failures),telegram_sends=0,wb_requests=0)))
 results.update(status='completed',passed=sum(not r['failures'] for r in results['cases']),total=len(results['cases']),blocked_attempts=blocked,completed_at=datetime.now(timezone.utc).isoformat());persist()
 print(json.dumps(dict(status='completed',passed=results['passed'],total=results['total'],telegram_sends=0,wb_requests=0)))
if __name__=='__main__':main()
