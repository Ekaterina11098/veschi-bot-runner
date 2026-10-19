"""Final retained-only projection: no collectors or configuration writes."""
import os,sys,json,requests
from urllib.parse import urlparse
sys.path.insert(0,'private-source')
from stock_deploy_support import seal
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(self,method,url,*a,**kw):
 if method!='GET' or urlparse(url).hostname!=host or not urlparse(url).path.startswith('/rest/v1/'):raise PermissionError('Only retained GET')
 return native(self,method,url,*a,**kw)
requests.sessions.Session.request=guard
from advertising_agent import agent_store as store
from analytics.payload_storage import decode_rows
rows=decode_rows(store.db('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_from':'eq.2026-10-18','period_to':'eq.2026-10-18','run_id':'eq.39231827505','select':'id,payload,collected_at','order':'id.asc','limit':20}) or [])
proof=dict(reports=rows,report_count=len(rows),daily_rollout=store.cache_get('advertising:ip:daily_rollout:v1'),day_claim=store.cache_get('advertising:ip:daily_run:v1:2026-10-19'),source_calls=0,telegram_calls=0,wb_writes=0,configuration_writes=0)
seal('ip-targeted18',proof)
print(json.dumps(dict(report_count=len(rows),source_calls=0,telegram_calls=0,wb_writes=0)))
