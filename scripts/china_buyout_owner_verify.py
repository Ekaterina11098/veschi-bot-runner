"""Verify real saved question60 with production routing, without Telegram or WB."""
import os,sys,json
from datetime import datetime,timezone
sys.path[:0]=['scripts','source']
import requests
from urllib.parse import urlparse
from conversion_watches import Worker
base=os.environ['SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SECRET_KEY']
headers={'apikey':key}
if not key.startswith('sb_secret_'):headers['Authorization']='Bearer '+key
def db(method,table,params=None,**kw):
 if method!='GET' or table not in ('telegram_api_cache','analytics_snapshots','analytics_costs','business_agent_jobs','business_agent_config'):raise RuntimeError('Preview read scope')
 r=requests.get(base+'/rest/v1/'+table,headers=headers,params=params,timeout=45)
 if not r.ok:raise RuntimeError('State HTTP '+str(r.status_code))
 return r.json()
def forbidden(*a,**kw):raise RuntimeError('Telegram forbidden in owner-only preview')
w=Worker(db,forbidden)
jobs=db('GET','business_agent_jobs',params={'id':'eq.60','agent_id':'eq.china','select':'*'})
if len(jobs)!=1:raise RuntimeError('Original119questionmissing')
answer,trace=w.saved_question(jobs[0],[])
result=next(x for x in trace if x.get('name')=='china_break_even')
if result.get('buyout',{}).get('sample_size')!=3 or abs(result['buyout']['percent']-100/3)>.001:raise RuntimeError('Actual119buyoutnotused')
if len(result['scenarios'])!=2 or any(s['status']!='calculated' for s in result['scenarios']):raise RuntimeError('Bothscenariosrequired')
payload=dict(status='verified',answer=answer,trace=trace,source_job_id=60,source_job_mutated=False,telegram_calls=0,wb_writes=0,observed_at=datetime.now(timezone.utc).isoformat())
h={**headers,'Prefer':'resolution=ignore-duplicates,return=representation','Content-Type':'application/json'}
r=requests.post(base+'/rest/v1/telegram_api_cache',params={'on_conflict':'cache_key'},headers=h,json=dict(cache_key='china_agent:break_even_preview:'+w.now.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()+':'+os.environ['GITHUB_RUN_ID'],payload=payload,expires_at='2036-10-20T00:00:00Z'),timeout=45)
if not r.ok:raise RuntimeError('Preview audit not saved')
print(json.dumps(payload,ensure_ascii=False))
