"""One owner-approved corrected DRR image from saved snapshots. No collection."""
import sys,os,json,hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
from advertising_daily_png import render_daily_png
from advertising_budget_evidence import load_daily_table_view,deliver_daily_tables
from stock_deploy_support import seal,error
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
proof=dict(complete=False,source_calls=0,wb_changes=0,telegram_calls=0)
def guard(session,method,url,*a,**kw):
 u=urlparse(url);method=method.upper()
 if u.hostname==host and u.path.startswith('/rest/v1/'):
  if method!='GET' and u.path!='/rest/v1/telegram_api_cache':raise PermissionError('Only existing delivery receipt writes')
 elif u.hostname=='api.telegram.org' and method=='POST' and u.path.endswith('/sendPhoto'):
  proof['telegram_calls']+=1
  if proof['telegram_calls']>1:raise PermissionError('One DRR image maximum')
 else:raise PermissionError('No collection, other Telegram calls or WB')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
try:
 now=datetime.now(ZoneInfo('Europe/Moscow'))
 assert str(now.date())=='2026-10-21','Approval date expired'
 reg=s.registration();assert reg['chat_id']==-1004378639510
 v=load_daily_table_view(s,now)
 assert v['period']=='2026-10-20' and len(v['campaigns'])==11
 expected={35654841:(18734,17,273),36514081:(18736,3,42),37155100:(18738,1,421),37363108:(18740,10,334),37757330:(18742,0,0),39410834:(18744,25,48),39483230:(18746,0,0),39634287:(18748,10,900),40192945:(18750,2,169),40428505:(18752,0,0),40428689:(18754,3,298)}
 for c in v['campaigns']:
  assert (c['source_snapshot_id'],c['no_order_count'],c['no_order_spend'])==expected[c['campaign_id']],'Approved data changed'
 assert sum(c['spend'] for c in v['campaigns'])==3461
 images=render_daily_png(v,Path(os.environ['RUNNER_TEMP'])/'approved-noorders-png')
 path=Path(next(x['path'] for x in images if x['kind']=='drr'))
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 text=json.dumps(dict(path=str(path),sha256=digest),sort_keys=True)
 def send(chat,text):
  with path.open('rb') as f:
   response=requests.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendPhoto',data={'chat_id':chat,'caption':'ДРР за 20 октября · обновлённый формат: количество товаров и расход без прямых заказов. Сохранённые данные, без нового сбора.'},files={'photo':(path.name,f,'image/png')},timeout=(10,60))
  b=response.json();m=b.get('result') or {};photos=m.get('photo') or []
  if response.status_code!=200 or b.get('ok') is not True or (m.get('chat') or {}).get('id')!=chat or type(m.get('message_id')) is not int or not photos:raise RuntimeError('Unknown delivery outcome; no retry')
  return dict(ok=True,chat_id=chat,message_id=m['message_id'],media_sha256=digest,photo_file_unique_id=photos[-1].get('file_unique_id'))
 proof['receipts']=deliver_daily_tables(s,[dict(kind='drr',text=text)],reg['chat_id'],'2026-10-21:owner-approved-noorders-v1',send)
 proof.update(complete=True,receipt_readback=True,view=v)
except Exception as e:proof['error']=error(e)
finally:
 seal('approved-noorders-png',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','telegram_calls','source_calls','wb_changes','receipt_readback')}))
if not proof['complete']:raise SystemExit(1)
