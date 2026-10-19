"""One bounded retained WB cache check; no source, configuration, or delivery calls."""
import os,json,sys,requests
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from stock_deploy_support import seal,error
p=dict(complete=False,source_calls=0,telegram_calls=0,wb_writes=0,configuration_writes=0)
try:
 native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
 def guard(self,method,url,*a,**kw):
  if method!='GET' or urlparse(url).hostname!=host or not urlparse(url).path.startswith('/rest/v1/'):raise RuntimeError('Only retained GET')
  return native(self,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 from advertising_agent import agent_store as store
 from analytics.payload_storage import decode_rows
 rows=decode_rows(store.db('GET','analytics_snapshots',params={'source':'in.(advertising_all_spend_stats,advertising_active_stats)','cabinet':'eq.token_2','status':'eq.complete','select':'id,payload,collected_at,period_from,period_to','order':'id.desc','limit':1}) or [])
 p['saved_wb_cache']=rows;p['complete']=True
except Exception as exc:p['error']=error(exc)
seal('advertising-retained-inventory',p)
print(json.dumps({k:p[k] for k in ('complete','source_calls','telegram_calls','wb_writes','configuration_writes')}))
if not p['complete']:raise SystemExit(1)
