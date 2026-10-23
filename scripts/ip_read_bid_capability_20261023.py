"""Two exclusive WB READ calls for exact recommendation parameters. Never writes WB."""
import os,sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from advertising_agent import collect_ip as c,agent_store as s
from stock_deploy_support import seal,error
CID=39410834;NMS=[255477781,506186804,1007948812]
proof=dict(complete=False,wb_writes=0,telegram_calls=0,reads=[],observed_at=datetime.now(timezone.utc).isoformat())
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*args,**kw):
 u=urlparse(url);method=method.upper()
 if u.hostname==host and u.path.startswith('/rest/v1/'):pass
 elif u.hostname=='advert-api.wildberries.ru':
  if method=='GET' and u.path=='/api/advert/v2/adverts' and kw.get('params')=={'ids':str(CID)}:pass
  elif method=='POST' and u.path=='/api/advert/v1/bids/min' and kw.get('json')==dict(advert_id=CID,nm_ids=NMS,payment_type='cpm',placement_types=['recommendation']):pass
  else:raise PermissionError('Only exact configuration and minimum READ allowed')
  proof['reads'].append(dict(method=method,path=u.path))
  if len(proof['reads'])>2:raise PermissionError('Two exclusive reads only')
 else:raise PermissionError('No other sources or Telegram')
 return native(session,method,url,*args,**kw)
requests.sessions.Session.request=guard
try:
 token=os.environ['WB_TOKEN_2']
 proof['configuration']=c.wb('GET','https://advert-api.wildberries.ru/api/advert/v2/adverts',token,'active_configuration',params={'ids':str(CID)})
 adverts=proof['configuration'].get('adverts') or []
 if len(adverts)!=1 or adverts[0]['id']!=CID or adverts[0].get('currency')!='RUB' or adverts[0].get('settings',{}).get('payment_type')!='cpm':raise ValueError('IP campaign identity/payment changed')
 if not set(NMS)<=set(x['nm_id'] for x in adverts[0].get('nm_settings',[])):raise ValueError('Selected membership changed; do not infer old plan')
 proof['minimum']=c.wb('POST','https://advert-api.wildberries.ru/api/advert/v1/bids/min',token,'recommendation_minimum',body=dict(advert_id=CID,nm_ids=NMS,payment_type='cpm',placement_types=['recommendation']))
 body=dict(source='advertising_recommendation_capability',cabinet='token_2',run_id=os.environ['GITHUB_RUN_ID'],period_from='2026-10-23',period_to='2026-10-23',status='complete',payload=dict(configuration=proof['configuration'],minimum=proof['minimum'],observed_at=proof['observed_at']),detail='Owner authorized missing recommendation inputs, read-only; no execution')
 saved=s.db('POST','analytics_snapshots',body=body,prefer='return=representation') or []
 if len(saved)!=1:raise RuntimeError('Read proof persistence failed')
 got=s.db('GET','analytics_snapshots',params={'id':'eq.'+str(saved[0]['id']),'select':'payload','limit':1}) or []
 if not got or got[0]['payload']!=body['payload']:raise RuntimeError('Read proof readback mismatch')
 proof.update(complete=True,snapshot_id=saved[0]['id'],full_readback=True)
except Exception as exc:proof['error']=error(exc)
finally:
 seal('ip-recommendation-capability',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','snapshot_id','full_readback','wb_writes','telegram_calls')}))
if not proof['complete']:raise SystemExit(1)
