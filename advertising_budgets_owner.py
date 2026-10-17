"""One bounded budget-read recovery job; no schedule, Telegram or mutation."""
import os,sys,time,json,io,contextlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
def cached_read_request(native,session,method,url,dbhost,*args,**kwargs):
 """Retry transient Supabase GET only; never replay WB or database writes."""
 import requests
 from urllib.parse import urlsplit
 eligible=method.upper()=='GET' and urlsplit(url).hostname==dbhost
 delays=(5,15,30)
 for attempt in range(4):
  try:
   response=native(session,method,url,*args,**kwargs)
  except (requests.exceptions.ReadTimeout,requests.exceptions.ConnectTimeout,requests.exceptions.ConnectionError):
   if not eligible or attempt==3:raise
  else:
   if not eligible or response.status_code not in (502,503,504) or attempt==3:return response
   response.close()
  time.sleep(delays[attempt])

from advertising_daily_runtime_guard import budget_pending
report={'iterations':[],'wb_writes':0,'telegram_calls':0}
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  from advertising_agent import collect_ip as c
  import requests
  from urllib.parse import urlsplit
  native=requests.sessions.Session.request;dbhost=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*args,**kwargs):
   u=urlsplit(url)
   if u.hostname!=dbhost and not (u.hostname=='advert-api.wildberries.ru' and method.upper()=='GET' and u.path=='/adv/v1/budget'):raise RuntimeError('Budget-only request allowlist')
   return cached_read_request(native,session,method,url,dbhost,*args,**kwargs)
  requests.sessions.Session.request=guarded
  config=c.latest('advertising_active_configuration',status=None)
  if not config or (datetime.now(timezone.utc)-datetime.fromisoformat(config['collected_at'])).total_seconds()>21600:raise RuntimeError('Current membership expired; no blind budget scope')
  active=config['payload']['campaign_ids'];report['membership_observed_at']=config['collected_at'];report['active_campaign_ids']=active
  single_step=os.environ.get('ADVERTISING_BUDGET_STEP_ONLY')=='true'
  # Time and request caps are independent: a429 does not consume successful progress.
  deadline=time.monotonic()+(120 if single_step else 13700)
  max_requests=1 if single_step else min(40,max(6,len(active)*3))
  def checkpoint(payload):
   queue=budget_pending(payload,active,c.NOW)
   queue.update(day=str(c.TODAY),membership_observed_at=config['collected_at'],origin_day_run=os.environ.get('GITHUB_RUN_ID'))
   c.save('advertising_budget_pending',queue,status='complete' if queue['complete'] else 'partial')
   got=c.latest('advertising_budget_pending',status=None)
   if not got or got.get('payload')!=queue:raise RuntimeError('Budget pending queue full readback missing')
   report['pending_queue']=queue
  for iteration in range(max_requests):
   c.NOW=datetime.now(timezone.utc);c.TODAY=c.NOW.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date()
   old=c.latest('advertising_campaign_budgets',status=None) or {};payload=old.get('payload') or {}
   fresh={x['campaign_id'] for x in payload.get('items',[]) if x.get('available') and x.get('observed_at') and 0<=(c.NOW-datetime.fromisoformat(x['observed_at'])).total_seconds()<21600}
   if set(active)<=fresh:report['complete']=True;report['budgets']=payload;checkpoint(payload);break
   report['budgets']=payload;checkpoint(payload)
   due=payload.get('next_retry_at')
   wait=max(0,(datetime.fromisoformat(due)-c.NOW).total_seconds()) if due else 0
   if wait>1800 or wait+60>deadline-time.monotonic() or (single_step and wait>0):report['pending_until']=due;report['budgets']=payload;break
   if wait:time.sleep(wait+2)
   c.NOW=datetime.now(timezone.utc);c.TODAY=c.NOW.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date()
   if time.monotonic()>=deadline:report['reason']='bounded_budget_deadline';break
   # Existing collector owns the WB cooldown and reuses fresh values; scope remains exact current active IDs.
   c.collect_campaign_budgets(os.environ['WB_TOKEN_2'],active)
   got=c.latest('advertising_campaign_budgets',status=None)
   if not got:raise RuntimeError('Budget save/readback missing')
   report['complete']=bool(got['payload'].get('complete'))
   report['budgets']=got['payload'];report['iterations'].append({'at':c.NOW.isoformat(),'available':sum(bool(x.get('available')) for x in got['payload']['items']),'missing':got['payload'].get('missing_campaign_ids'),'next_retry_at':got['payload'].get('next_retry_at')})
   checkpoint(got['payload'])
   seal('advertising-budgets',report)
   if report['complete']:break
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-budgets',report)
 queue=report.get('pending_queue') or {}
 print(json.dumps({'pending_campaign_ids':queue.get('pending_campaign_ids'),'next_allowed_at':queue.get('next_allowed_at'),'pending_queue_verified':bool(queue),'complete':report.get('complete',False),'iterations':len(report['iterations']),'wb_writes':0,'telegram_calls':0,'error_type':report.get('error',{}).get('type')}))
