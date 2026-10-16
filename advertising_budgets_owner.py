"""One bounded budget-read recovery job; no schedule, Telegram or mutation."""
import os,sys,time,json,io,contextlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
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
   return native(session,method,url,*args,**kwargs)
  requests.sessions.Session.request=guarded
  config=c.latest('advertising_active_configuration',status=None)
  if not config or (datetime.now(timezone.utc)-datetime.fromisoformat(config['collected_at'])).total_seconds()>21600:raise RuntimeError('Current membership expired; no blind budget scope')
  active=config['payload']['campaign_ids'];report['membership_observed_at']=config['collected_at'];report['active_campaign_ids']=active
  single_step=os.environ.get('ADVERTISING_BUDGET_STEP_ONLY')=='true'
  for iteration in range(1 if single_step else len(active)+2):
   c.NOW=datetime.now(timezone.utc);c.TODAY=c.NOW.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date()
   old=c.latest('advertising_campaign_budgets',status=None) or {};payload=old.get('payload') or {}
   fresh={x['campaign_id'] for x in payload.get('items',[]) if x.get('available') and x.get('observed_at') and 0<=(c.NOW-datetime.fromisoformat(x['observed_at'])).total_seconds()<21600}
   if set(active)<=fresh:report['complete']=True;report['budgets']=payload;break
   due=payload.get('next_retry_at')
   wait=max(0,(datetime.fromisoformat(due)-c.NOW).total_seconds()) if due else 0
   if wait>1800 or (single_step and wait>0):report['pending_until']=due;report['budgets']=payload;break
   if wait:time.sleep(wait+2)
   c.NOW=datetime.now(timezone.utc);c.TODAY=c.NOW.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date()
   c.collect_campaign_budgets(os.environ['WB_TOKEN_2'],active)
   got=c.latest('advertising_campaign_budgets',status=None)
   if not got:raise RuntimeError('Budget save/readback missing')
   report['complete']=bool(got['payload'].get('complete'))
   report['budgets']=got['payload'];report['iterations'].append({'at':c.NOW.isoformat(),'available':sum(bool(x.get('available')) for x in got['payload']['items']),'missing':got['payload'].get('missing_campaign_ids'),'next_retry_at':got['payload'].get('next_retry_at')})
   seal('advertising-budgets',report)
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-budgets',report)
 print(json.dumps({'complete':report.get('complete',False),'iterations':len(report['iterations']),'wb_writes':0,'telegram_calls':0,'error_type':report.get('error',{}).get('type')}))
