import os,sys,json
from pathlib import Path
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from stock_deploy_support import seal,error
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*a,**kw):
 u=urlparse(url)
 if method.upper()!='GET' or u.hostname!=host or not u.path.startswith('/rest/v1/'):raise PermissionError('Saved raw GET only')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
from advertising_agent import agent_store as s
proof=dict(source_calls=0,wb_changes=0,telegram_calls=0)
rows=s.db('GET','analytics_snapshots',params={'id':'eq.18542','select':'id,source,cabinet,period_from,period_to,payload,collected_at','limit':1})
proof['raw']=rows
from analytics.mpstats_recovery import normalize
try:proof['normalized']=normalize(rows[0]['payload'][0],'token_2')
except Exception as e:proof['normalization_error']=error(e)
seal('saved-401-raw',proof)
print(json.dumps({'saved_raw_count':len(rows),'source_calls':0,'telegram_calls':0,'normalized':bool(proof.get('normalized'))}))
