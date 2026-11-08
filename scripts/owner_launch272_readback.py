"""Bounded readback of the exact failed accepted launch. No WB mutation or Telegram."""
import json,os,time
from datetime import datetime,timezone
import requests
from china_codex_cloud import DB
db=DB();key='china_agent:owner_launch272_readback:2026-11-08:v1'
old=db.get(key)
if old:print(json.dumps({'status':'existing_readback'}));raise SystemExit()
token=os.environ['WB_TOKEN_3'];out={}
for name,method,path,body in [
 ('config','GET','/api/advert/v1/config',None),
 ('campaign','GET','/api/advert/v2/adverts?ids=41680341',None),
 ('limit','GET','/api/advert/v0/daily-limits?advertIds=41680341',None),
 ('budget','POST','/api/advert/v2/budget',dict(advertIds=[41680341]))]:
 try:
  response=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':token},json=body,timeout=45)
  try:payload=response.json()
  except Exception:payload={'body_excerpt':response.text[:2000]}
  out[name]=dict(http_status=response.status_code,payload=payload,read_only=True)
 except Exception:out[name]=dict(error='transport_unavailable',read_only=True)
 time.sleep(1.5)
db.once(key,dict(status='readback_complete',campaign_id=41680341,job_id=272,observed_at=datetime.now(timezone.utc).isoformat(),results=out,wb_writes=0,telegram_calls=0))
print(json.dumps({'status':'readback_complete','http_statuses':{k:v.get('http_status')for k,v in out.items()},'wb_writes':0}))
