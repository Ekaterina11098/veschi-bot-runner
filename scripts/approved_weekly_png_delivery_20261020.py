"""Owner approved two saved PNGs. No collection or WB changes."""
import os,sys,json,hashlib,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
from approved_weekly_png_renderer import render_daily_png
from stock_deploy_support import seal,error
native=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
proof=dict(complete=False,source_calls=0,wb_changes=0,telegram_calls=0,receipts=[])
def guard(session,method,url,*a,**kw):
 u=urlparse(url)
 if u.hostname==host and u.path.startswith('/rest/v1/'):pass
 elif u.hostname=='api.telegram.org' and method.upper()=='POST' and u.path.endswith('/sendPhoto'):
  proof['telegram_calls']+=1
  if proof['telegram_calls']>2:raise RuntimeError('Two PNGs maximum')
 else:raise PermissionError('No sources or WB')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
try:
 reg=s.registration();assert reg['chat_id']==-1004378639510
 if str(datetime.now(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date())!='2026-10-20':raise PermissionError('Approval date expired')
 v=json.loads(Path('scripts/approved_weekly_view_20261020.json').read_text(encoding='utf-8'))
 images=render_daily_png(v,Path(os.environ['RUNNER_TEMP'])/'approved-weekly-png')
 assert len(images)==2 and [x['kind'] for x in images]==['drr','budgets']
 for i,image in enumerate(images,1):
  key='advertising:ip:approved-weekly-overview:20261020:'+str(i)
  dailykey='advertising:ip:daily-tables:v1:2026-10-20:'+str(i)
  prior=s.cache_get(key)
  if prior:
   if prior.get('status')!='confirmed':raise RuntimeError('Prior uncertain photo outcome; no blind retry')
   proof['receipts'].append(prior);continue
  daily=s.cache_get(dailykey)
  if not daily or daily.get('status')!='owner_held':raise RuntimeError('Expected owner-held current delivery slot; inspect before sending')
  path=Path(image['path']);sha=hashlib.sha256(path.read_bytes()).hexdigest()
  claim=dict(status='uncertain',kind=image['kind'],part=i,chat_id=reg['chat_id'],media_sha256=sha,at=datetime.now(timezone.utc).isoformat())
  s.cache_set(key,claim,ttl_days=365);assert s.cache_get(key)==claim
  caption='ДРР за 19 октября · расход за день и 13–19 октября. Все 11 РК.' if i==1 else 'Бюджеты · фактические даты наблюдения указаны на картинке. Оценка по расходу 19 октября, не гарантия срока.'
  if i>1:time.sleep(3.2)
  with path.open('rb') as f:
   response=requests.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendPhoto',data={'chat_id':reg['chat_id'],'caption':caption},files={'photo':(path.name,f,'image/png')},timeout=(10,60))
  b=response.json();m=b.get('result') or {};photos=m.get('photo') or []
  if response.status_code!=200 or b.get('ok') is not True or (m.get('chat') or {}).get('id')!=reg['chat_id'] or type(m.get('message_id')) is not int or not photos:raise RuntimeError('Photo delivery unconfirmed; do not retry')
  receipt=dict(claim,status='confirmed',message_id=m['message_id'],photo_file_unique_id=photos[-1].get('file_unique_id'),confirmed_at=datetime.now(timezone.utc).isoformat())
  s.cache_set(key,receipt,ttl_days=365);assert s.cache_get(key)==receipt
  s.cache_set(dailykey,dict(receipt,approved_manual_delivery=True,prevents_daily_duplicate=True),ttl_days=365)
  assert (s.cache_get(dailykey) or {}).get('message_id')==receipt['message_id']
  proof['receipts'].append(receipt)
  print(json.dumps(dict(part=i,message_id=receipt['message_id'],status='confirmed',receipt_readback=True)))
 scope=dict(cabinet='token_2',chat_id=reg['chat_id'],owner_id=reg['registered_by_user_id'],campaign_ids=sorted(c['campaign_id'] for c in v['campaigns']),basis='Owner approved established overview including paused campaigns',at=datetime.now(timezone.utc).isoformat())
 s.cache_set('advertising:ip:daily-overview-scope:v1',scope,ttl_days=365)
 assert s.cache_get('advertising:ip:daily-overview-scope:v1')==scope
 hold=s.cache_get('advertising:ip:notification_hold:v1') or {}
 if hold.get('chat_id')==reg['chat_id']:
  hold.update(paused=False,resumed_at=datetime.now(timezone.utc).isoformat(),reason='Owner approved both current PNG delivery and daily format on 2026-10-20')
  s.cache_set('advertising:ip:notification_hold:v1',hold,ttl_days=365)
  assert (s.cache_get('advertising:ip:notification_hold:v1') or {}).get('paused') is False
 proof.update(complete=True,daily_slots_readback=True,overview_scope_readback=True,notification_hold_released=True)
except Exception as e:proof['error']=error(e)
finally:
 seal('approved-weekly-png-delivery',proof)
 print(json.dumps({k:proof.get(k) for k in ('complete','telegram_calls','source_calls','wb_changes','daily_slots_readback','notification_hold_released')}))
if not proof['complete']:raise SystemExit(1)
