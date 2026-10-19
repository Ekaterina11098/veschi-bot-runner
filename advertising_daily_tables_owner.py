"""Daily two-table delivery: retained data only, independent of saved analysis status."""
import os,sys,json,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
import requests
from advertising_agent import agent_store as store
from advertising_budget_evidence import load_daily_table_view,render_daily_tables,deliver_daily_tables
from stock_deploy_support import seal,error
def main():
 report=dict(source_calls=0,wb_writes=0,telegram_calls=0,business_status='incomplete')
 native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
 def guard(session,method,url,*a,**kw):
  u=urlparse(url)
  if u.hostname==host and u.path.startswith('/rest/v1/'):pass
  elif u.hostname=='api.telegram.org' and method.upper()=='POST' and u.path.endswith('/sendMessage'):report['telegram_calls']+=1
  else:raise PermissionError('Daily tables cannot collect sources or change WB')
  return native(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  reg=store.registration();approval=store.cache_get('advertising:ip:daily_rollout:v1') or {}
  if not approval.get('enabled') or approval.get('chat_id')!=reg['chat_id'] or approval.get('owner_id')!=reg['registered_by_user_id']:raise PermissionError('Existing daily owner approval mismatch')
  view=load_daily_table_view(store,datetime.now(timezone.utc))
  report['view']=view
  messages=render_daily_tables(view)
  report['messages']=messages
  last=[None]
  def send(chat,text):
   if last[0] is not None:
    wait=3.2-(time.monotonic()-last[0])
    if wait>0:time.sleep(wait)
   last[0]=time.monotonic()
   response=requests.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendMessage',json={'chat_id':chat,'text':text,'parse_mode':'HTML'},timeout=(10,30))
   body=response.json();msg=body.get('result') or {}
   return dict(ok=response.status_code==200 and body.get('ok') is True,message_id=msg.get('message_id'),chat_id=(msg.get('chat') or {}).get('id'))
  from zoneinfo import ZoneInfo
  day=str(datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).date())
  report['receipts']=deliver_daily_tables(store,messages,reg['chat_id'],day,send)
  report['business_status']='complete'
  report['data_coverage']='complete' if all(x['metrics_complete'] for x in view['campaigns']) else 'partial_explicitly_labelled'
 except Exception as exc:report['error']=error(exc)
 finally:
  requests.sessions.Session.request=native
  seal('advertising-daily-tables',report)
  print(json.dumps({k:report.get(k) for k in ('business_status','data_coverage','source_calls','wb_writes','telegram_calls')}))
 return report
if __name__=='__main__':
 if main()['business_status']!='complete':raise SystemExit(1)
