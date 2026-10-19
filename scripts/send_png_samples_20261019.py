"""Two owner-approved PNG samples. No sources, WB writes, daily-format changes."""
import os,sys,json,hashlib,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
from render_png_samples_20261019 import render
native=requests.sessions.Session.request
host=urlparse(os.environ['SUPABASE_URL']).hostname
calls=0
def guard(session,method,url,*a,**kw):
 global calls
 u=urlparse(url)
 if u.hostname==host and u.path.startswith('/rest/v1/'):pass
 elif u.hostname=='api.telegram.org' and method.upper()=='POST' and u.path.endswith('/sendPhoto'):
  calls+=1
  if calls>2:raise RuntimeError('Two samples maximum')
 else:raise PermissionError('No collection or WB calls allowed')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
reg=s.registration()
assert int(reg['chat_id'])==-1004378639510
if datetime.now(timezone.utc).date().isoformat()!='2026-10-19':raise RuntimeError('Sample authorization date expired')
data=json.loads(Path('scripts/png_samples_retained_20261019.json').read_text(encoding='utf-8'))
assert len(data['campaigns'])==11
out=Path(os.environ['RUNNER_TEMP'])/'png-report-samples'
files=render(data,out)
captions=['Образец PNG · ДРР за 18 октября. Итоги РК с подтверждённым посткликом; по товарам — прямой ДРР. Ежедневный формат пока не изменён.',
'Образец PNG · Бюджеты: наблюдения 19 октября, время МСК. Оценка по расходу 18 октября, не текущий остаток и не гарантия срока. Ежедневный формат пока не изменён.']
for i,(path,caption) in enumerate(zip(files,captions),1):
 key='advertising:ip:png-samples:20261019:'+str(i)
 previous=s.cache_get(key)
 if previous:
  if previous.get('status')!='confirmed':raise RuntimeError('Prior outcome uncertain; no blind retry')
  print(json.dumps(previous));continue
 payload=Path(path).read_bytes()
 assert payload[:8]==b'\x89PNG\r\n\x1a\n'
 claim=dict(status='uncertain',part=i,chat_id=reg['chat_id'],sha256=hashlib.sha256(payload).hexdigest(),at=datetime.now(timezone.utc).isoformat())
 # Claim persisted and read back before a single Telegram request per sample.
 s.cache_set(key,claim,ttl_days=365)
 assert s.cache_get(key)==claim
 if i>1:time.sleep(3.2)
 with open(path,'rb') as fh:
  r=requests.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendPhoto',data={'chat_id':reg['chat_id'],'caption':caption},files={'photo':(Path(path).name,fh,'image/png')},timeout=(10,60))
 b=r.json();m=b.get('result') or {}
 if r.status_code!=200 or b.get('ok') is not True or (m.get('chat') or {}).get('id')!=reg['chat_id'] or not isinstance(m.get('message_id'),int) or not m.get('photo'):raise RuntimeError('Photo outcome unconfirmed; no automatic retry')
 receipt=dict(claim,status='confirmed',message_id=m['message_id'],photo_file_unique_id=m['photo'][-1]['file_unique_id'],confirmed_at=datetime.now(timezone.utc).isoformat())
 s.cache_set(key,receipt,ttl_days=365)
 assert s.cache_get(key)==receipt
 print(json.dumps(dict(receipt,receipt_readback=True)))
print(json.dumps({'complete':True,'telegram_sendPhoto_calls':calls,'source_calls':0,'wb_writes':0,'daily_format_changed':False}))
