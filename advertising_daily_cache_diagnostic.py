"""GET one remaining suspected retained cache; no other data reads or writes."""
import sys,os,json,requests
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.collect import _database_transport as db
from stock_deploy_support import seal,error
r={'source_calls':0,'wb_calls':0,'telegram_calls':0,'db_writes':0}
original=requests.sessions.Session.request
def guarded(session,method,url,*a,**kw):
 from urllib.parse import urlsplit
 if urlsplit(url).hostname!=urlsplit(os.environ['SUPABASE_URL']).hostname or method!='GET':
  raise PermissionError('Exact retained cache GET only')
 response=original(session,method,url,*a,**kw)
 r['decoded_response_bytes']=len(response.content);r['content_encoding']=response.headers.get('Content-Encoding')
 return response
try:
 requests.sessions.Session.request=guarded
 rows=db('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:funnel_periods:token_2:v1','select':'payload,updated_at','limit':1}) or []
 if len(rows)!=1:raise RuntimeError('Retained funnel cache absent')
 p=rows[0]['payload'];periods=p.get('periods',{})
 r['funnel']={'updated_at':rows[0].get('updated_at'),'payload_json_bytes':len(json.dumps(p,ensure_ascii=False,separators=(',',':')).encode()),
  'skus':len(periods),'period_entries':sum(len(v) for v in periods.values())}
except Exception as e:r['error']=error(e)
finally:
 requests.sessions.Session.request=original;seal('daily-funnel-diagnostic',r)
 print(json.dumps({'source_calls':0,'db_writes':0,'error_type':r.get('error',{}).get('type')}))
