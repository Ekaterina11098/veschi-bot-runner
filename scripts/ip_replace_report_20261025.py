"""Replace only confirmed bad IP PNG messages44/45, after complete frozen preview validation."""
import os,sys,json,hashlib,base64
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,'private-source')
import requests
from advertising_agent import agent_store as s
from stock_deploy_support import seal
CHAT=-1004378639510;BOT=8987327588;KEY='advertising:ip:daily-report-replace:20261025:v1'
proof=dict(complete=False,source_calls=0,wb_writes=0,receipts=[])
def tg(method,body=None,files=None):
 url='https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/'+method
 r=requests.post(url,data=body,files=files,timeout=(10,60));j=r.json()
 if not r.ok or not j.get('ok'):raise RuntimeError('Telegram replacement not confirmed HTTP '+str(r.status_code))
 return j['result']
try:
 reg=s.registration()
 if reg['chat_id']!=CHAT or tg('getMe')['id']!=BOT:raise ValueError('Bot or registered chat mismatch')
 frozen=s.cache_get(KEY+':input')
 if not frozen or frozen.get('complete') is not True:raise ValueError('Verified frozen preview missing')
 view=frozen['view']
 if view['period']!='2026-10-24' or len(view['campaigns'])!=11 or not all(x.get('metrics_complete') and x.get('weekly_spend') is not None for x in view['campaigns']):raise ValueError('Incomplete coverage; no Telegram edits')
 for index,item in enumerate(frozen['images'],1):
  expected=[('drr',44),('budgets',45)][index-1]
  if item['kind']!=expected[0]:raise ValueError('Wrong report kind')
  old=s.cache_get('advertising:ip:daily-tables:v1:2026-10-25:'+str(index))
  if not old or old.get('status')!='confirmed' or old.get('message_id')!=expected[1] or old.get('chat_id')!=CHAT or old.get('kind')!=item['kind']:raise ValueError('Original receipt mismatch')
  b=base64.b64decode(item['data'],validate=True)
  if hashlib.sha256(b).hexdigest()!=item['sha256']:raise ValueError('Frozen media SHA mismatch')
  key=KEY+':'+item['kind'];prior=s.cache_get(key)
  if prior:
   if prior.get('status')=='confirmed':proof['receipts'].append(prior);continue
   raise ValueError('Prior replacement outcome unknown; no blind repetition')
  claim=dict(status='uncertain',chat_id=CHAT,message_id=expected[1],media_sha256=item['sha256'],at=datetime.now(timezone.utc).isoformat())
  rows=s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body=dict(cache_key=key,payload=claim,expires_at=(datetime.now(timezone.utc)+timedelta(days=365)).isoformat()),prefer='resolution=ignore-duplicates,return=representation') or []
  if len(rows)!=1 or s.cache_get(key)!=claim:raise ValueError('Replacement claim conflict')
  caption='ДРР за24.10.2026 · расход за день и18–24 октября. Исправленный полный отчёт.' if item['kind']=='drr' else 'Бюджеты ·25.10.2026, время МСК. Срок условный, по расходу24.10; даты балансов указаны отдельно.'
  result=tg('editMessageMedia',dict(chat_id=CHAT,message_id=expected[1],media=json.dumps(dict(type='photo',media='attach://photo',caption=caption),ensure_ascii=False)),files={'photo':('IP-'+item['kind']+'.png',b,'image/png')})
  if result.get('chat',{}).get('id')!=CHAT or result.get('message_id')!=expected[1] or not result.get('photo'):raise ValueError('Edited receipt mismatch')
  value=dict(claim,status='confirmed',confirmed_at=datetime.now(timezone.utc).isoformat(),photo_file_unique_id=result['photo'][-1]['file_unique_id'])
  s.cache_set(key,value,ttl_days=365)
  if s.cache_get(key)!=value:raise ValueError('Replacement receipt persistence mismatch')
  proof['receipts'].append(value)
 proof['complete']=len(proof['receipts'])==2
except Exception as ex:proof['error']=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__
finally:
 seal('ip-report-replaced-20261025',proof)
 print(json.dumps({k:proof.get(k) for k in ['complete','error','wb_writes','source_calls']}))
if not proof['complete']:raise SystemExit(1)
