"""Existing retained-data diagnostic adapted to three exact advertising snapshots. GET-only."""
import os,sys,json,hashlib,requests
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.collect import _database_transport as db
from analytics.mpstats_recovery import normalize
from stock_deploy_support import seal,error
result={'source_calls':0,'wb_calls':0,'telegram_calls':0,'db_writes':0,'http':[],'reports':[]}
original=requests.sessions.Session.request
def guarded(session,method,url,*a,**kw):
 from urllib.parse import urlsplit
 if urlsplit(url).hostname!=urlsplit(os.environ['SUPABASE_URL']).hostname or method.upper()!='GET':raise PermissionError('Retained GET-only')
 response=original(session,method,url,*a,**kw)
 result['http'].append({'decoded_bytes':len(response.content)})
 if sum(v['decoded_bytes'] for v in result['http'])>100000000:raise RuntimeError('100MB retained read limit')
 return response
try:
 requests.sessions.Session.request=guarded
 cached=db('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:agent_reports:token_2:v1','select':'payload,updated_at','limit':1})
 index=cached[0]['payload'] if cached else {}
 for ident,cid in ((17977,12190110),(17993,12221548),(17997,12221549)):
  rows=db('GET','analytics_snapshots',params={'id':'eq.'+str(ident),'select':'id,source,payload,collected_at','limit':1})
  if len(rows)!=1:raise RuntimeError('Exact retained snapshot missing')
  obs=rows[0]['payload'][0];args=obs['arguments']
  if args!={'campaign_id':cid,'d1':'2026-10-10','d2':'2026-10-16','report':'products'}:raise RuntimeError('Exact retained scope mismatch')
  source,n=normalize(obs,'token_2')
  entries=[v for v in index.get('reports',{}).values() if (v.get('report') or {}).get('source_request_key')==obs.get('request_key')]
  result['reports'].append({'id':ident,'source':source,'observation':obs,'renormalized':n,'matching_cache_entries':entries,'raw_sha256':hashlib.sha256(json.dumps(obs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
 result['complete']=True
except Exception as exc:result['error']=error(exc);result['complete']=False
finally:
 requests.sessions.Session.request=original
 seal('pair-retained-audit',result)
 print(json.dumps({'complete':result.get('complete'),'exact_retained_reports':len(result['reports']),'source_calls':0,'db_writes':0,'error_type':(result.get('error') or {}).get('type')}))
 if not result.get('complete'):sys.exit(1)
