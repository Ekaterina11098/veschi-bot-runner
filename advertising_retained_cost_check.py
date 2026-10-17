"""Exactly two saved cost GETs; no source collection or business database writes."""
import os,requests,hashlib,json
from stock_deploy_support import seal,error
r=dict(source_calls=0,wb_calls=0,telegram_calls=0,db_writes=0)
try:
 url=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/analytics_costs'
 kw=dict(headers={'apikey':os.environ['SUPABASE_SECRET_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_SECRET_KEY']},params={'article':'ilike.5belts-chocolate','select':'article,cost,observed_at,source','limit':10},timeout=30)
 a=requests.get(url,**kw);a.raise_for_status();b=requests.get(url,**kw);b.raise_for_status()
 if a.json()!=b.json():raise RuntimeError('Retained cost readback changed')
 r['rows']=a.json();r['complete']=True;r['decoded_bytes']=len(a.content)+len(b.content)
except Exception as exc:r['error']=error(exc)
finally:seal('retained-cost',r);print(json.dumps({'complete':r.get('complete',False),'source_calls':0,'db_writes':0}))
