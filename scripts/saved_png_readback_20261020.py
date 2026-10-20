"""Owner requested saved daily PNG report readback; GET-only, no sources or delivery."""
import os,sys,json
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
sys.path.insert(0,'private-source')
from stock_deploy_support import seal,error
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
calls=0
def guard(session,method,url,*a,**kw):
 global calls
 u=urlparse(url)
 if u.hostname!=host or not u.path.startswith('/rest/v1/') or method.upper()!='GET':raise PermissionError('Read-only saved Supabase data only')
 calls+=1
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
proof=dict(source_calls=0,telegram_calls=0,wb_changes=0,state_changes=0,complete=False)
try:
 from advertising_agent import agent_store as s
 from advertising_budget_evidence import load_daily_table_view
 now=datetime.now(timezone.utc)
 proof['view']=load_daily_table_view(s,now)
 proof['configuration']=s.db('GET','analytics_snapshots',params={'source':'eq.advertising_active_configuration','cabinet':'eq.token_2','select':'id,payload,collected_at','order':'id.desc','limit':1})
 proof['daily_claim']=s.cache_get('advertising:ip:daily_run:v1:2026-10-20')
 proof['budget_pending']=s.db('GET','analytics_snapshots',params={'source':'eq.advertising_budget_pending','cabinet':'eq.token_2','select':'id,payload,collected_at','order':'id.desc','limit':1})
 proof['complete']=True
except Exception as e:proof['error']=error(e)
finally:
 proof['saved_read_calls']=calls
 seal('saved-png-readback',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','saved_read_calls','source_calls','telegram_calls','state_changes')}))
if not proof['complete']:raise SystemExit(1)
