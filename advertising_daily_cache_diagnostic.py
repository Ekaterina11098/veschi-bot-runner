"""One read-only retained-data diagnostic. No source tools or business execution."""
import os,sys,json,copy,requests
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.collect import _database_transport as db
from analytics.stage_one import read
from stock_deploy_support import seal,error
r={'source_calls':0,'wb_calls':0,'telegram_calls':0,'db_writes':0,'http':[],'snapshots':[]}
def size(v):return len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())
original=requests.sessions.Session.request
def guarded(session,method,url,*a,**kw):
 from urllib.parse import urlsplit
 p=urlsplit(url);allowed=urlsplit(os.environ['SUPABASE_URL']).hostname
 if p.hostname!=allowed or method.upper()!='GET':raise PermissionError('Retained-data diagnostic GET-only')
 response=original(session,method,url,*a,**kw)
 r['http'].append(dict(table=p.path.rsplit('/',1)[-1],decoded_response_bytes=len(response.content),
  content_length=response.headers.get('Content-Length'),content_encoding=response.headers.get('Content-Encoding')))
 return response
try:
 requests.sessions.Session.request=guarded
 key='mpstats:agent_reports:token_2:v1'
 row=db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1})
 index=row[0]['payload'] if row else {}
 r['index']={'updated_at':row[0].get('updated_at') if row else None,'json_payload_bytes':size(index),
  'report_count':len(index.get('reports',{}))}
 ids=(17841,17842,17843,17844,17845,17847,17849,17851,17853)
 from analytics.mpstats_recovery import normalize
 for ident in ids:
  rows=read('analytics_snapshots',{'id':'eq.'+str(ident),'select':'id,source,period_from,period_to,payload,collected_at','limit':1})
  if len(rows)!=1:raise RuntimeError('Exact saved snapshot missing')
  row=rows[0];obs=row['payload'][0];item={k:row.get(k) for k in ('id','source','period_from','period_to','collected_at')}
  item.update(payload_bytes=size(row['payload']),tool=obs.get('tool'),observed_at=obs.get('observed_at'))
  try:
   source,n=normalize(obs,'token_2')
   item.update(normalized_source=source,normalized_bytes=size(n) if source else 0)
  except Exception as e:item['normalization_error']=type(e).__name__
  r['snapshots'].append(item)
 claim=db('GET','telegram_api_cache',params={'cache_key':'eq.advertising:ip:daily_run:v1:2026-10-17','select':'payload,updated_at','limit':1})
 r['daily_claim']=claim
 monitor=db('GET','telegram_api_cache',params={'cache_key':'eq.advertising:ip:order_outcome_monitor:v1','select':'payload','limit':1})
 m=monitor[0]['payload'] if monitor else {}
 r['monitor']={'tracked':len(m.get('orders',{})),'json_bytes':size(m),'history_not_replayed':True}
 r['decoded_response_bytes_total']=sum(x['decoded_response_bytes'] for x in r['http'])
except Exception as e:r['error']=error(e)
finally:
 requests.sessions.Session.request=original
 seal('daily-cache-diagnostic',r)
 print(json.dumps({'error_type':r.get('error',{}).get('type'),'source_calls':0,'db_writes':0,'wb_calls':0}))
