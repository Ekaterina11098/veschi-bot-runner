import os,json,sys,requests
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from stock_deploy_support import seal
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(self,method,url,*a,**kw):
 if method!='GET' or urlparse(url).hostname!=host or not urlparse(url).path.startswith('/rest/v1/'):raise RuntimeError('Only retained GET')
 return native(self,method,url,*a,**kw)
requests.sessions.Session.request=guard
from advertising_agent import agent_store as store
r=store.db('GET','analytics_snapshots',params={'source':'in.(advertising_all_spend_stats,advertising_active_stats)','cabinet':'eq.token_2','status':'eq.complete','select':'id,collected_at,period_from,period_to,last_day:payload->0->days->-1->>date,first_day:payload->0->days->0->>date','order':'id.desc','limit':1}) or []
seal('advertising-retained-inventory',dict(complete=True,saved_wb_metadata=r,source_calls=0,telegram_calls=0,wb_writes=0,configuration_writes=0))
print(json.dumps(dict(complete=True,source_calls=0,telegram_calls=0,wb_writes=0)))
