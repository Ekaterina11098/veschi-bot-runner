"""Owner asked to send nothing: hold today's pending table delivery only."""
import os,sys,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
def guard(session,method,url,*a,**kw):
 u=urlparse(url)
 if u.hostname!=host or not u.path.startswith('/rest/v1/') or method.upper() not in ('GET','POST'):raise PermissionError('No Telegram or sources; only hold state')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
reg=s.registration();assert reg['chat_id']==-1004378639510
hold=dict(owner_instruction='Send nothing until further owner instruction',paused=True,chat_id=reg['chat_id'],at=datetime.now(timezone.utc).isoformat(),scope='daily overview PNG and current addressed result',analysis_unchanged=True,schedule_unchanged=True)
s.cache_set('advertising:ip:notification_hold:v1',hold,ttl_days=365)
assert s.cache_get('advertising:ip:notification_hold:v1')==hold
for i in (1,2):
 key='advertising:ip:daily-tables:v1:2026-10-20:'+str(i)
 row=s.cache_get(key)
 if row:print(json.dumps({'part':i,'existing_status':row.get('status'),'existing_message_id':row.get('message_id'),'not_overwritten':True}));continue
 body=dict(cache_key=key,payload=dict(status='owner_held',chat_id=reg['chat_id'],part=i,reason='Explicit owner no-send instruction; not delivered',at=hold['at']),updated_at=hold['at'],expires_at=(datetime.now(timezone.utc)+timedelta(days=365)).isoformat())
 s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body=body,prefer='resolution=ignore-duplicates')
 saved=s.cache_get(key)
 assert saved and saved.get('status')=='owner_held'
 print(json.dumps({'part':i,'status':'owner_held','readback':True}))
print(json.dumps({'hold_readback':True,'telegram_calls':0,'source_calls':0,'schedule_changed':False}))
