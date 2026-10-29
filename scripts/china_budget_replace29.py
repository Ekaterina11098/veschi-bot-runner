"""Owner29Oct: replace budgets485 only. Private archives, exact bindings, no WB."""
import os,sys,json,copy,base64,hashlib
from datetime import datetime,timezone
import requests
from china_advertising_state import AdvertisingIO
from china_advertising_v2_png import render
from china_budget_reserve import apply as reserve
from china_advertising_delivery import deliver,telegram_sender,CHAT,BOT
from china_daily_ad_actions import plan,bind,BIND
from china_loss_control import PLAN,digest
DAY='2026-10-29'
ROOT='china_agent:budget_format_revision:'+DAY+':v1'
INPUT=ROOT+':input'
ART='china_agent:advertising_artifacts:'+DAY+':v2'
DEL='china_agent:advertising_delivery:'+DAY+':v1'
OLD=485
class NoMarketIO(AdvertisingIO):
 def wb(self,*args,**kwargs):raise ValueError('Report replacement has no WB capability')
def stamp():return datetime.now(timezone.utc).isoformat()
def validate(p):
 if not p or p.get('day')!=DAY or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT or p.get('owner_id')!=5122667182 or p.get('old_message_id')!=OLD or p.get('wb_writes')!=0 or p.get('status')!='owner_approved' or p.get('authorization')!='owner_codex_replace_budget29':raise ValueError('Explicit report replacement authorization missing')
def archive(io,key,value):
 old=io.get(key)
 if old is None:
  if not io.create(key,value):raise ValueError('Concurrent report archive')
 elif old!=value:raise ValueError('Immutable report archive changed')
def prepare(io):
 authorization=io.get(INPUT);validate(authorization)
 e=io.get(ROOT)
 if e:return e
 art=io.get(ART);delivery=io.get(DEL)
 if not art or art.get('status')!='frozen' or not delivery or delivery.get('status')!='delivered':raise ValueError('Original delivered report unavailable')
 parts=[r for r in delivery['parts'] if r['kind'].split(':')[0]=='budgets']
 oldfiles=[f for f in art['files'] if f['family']=='budgets']
 if len(parts)!=1 or len(oldfiles)!=1 or parts[0]['message_id']!=OLD:raise ValueError('Old budget message identity changed')
 part=parts[0];original=oldfiles[0]
 if part['receipt']['chat']['id']!=CHAT or part['receipt']['from']['id']!=BOT or hashlib.sha256(base64.b64decode(original['b64'],validate=True)).hexdigest()!=part['sha256']:raise ValueError('Original budget photo receipt mismatch')
 archive(io,ROOT+':before_artifacts',art);archive(io,ROOT+':before_delivery',delivery)
 oldbinding=io.get(BIND+str(OLD))
 if not oldbinding:raise ValueError('Original budget binding missing')
 oldplan=io.get(PLAN+oldbinding['plan_id'])
 archive(io,ROOT+':before_binding',oldbinding);archive(io,ROOT+':before_plan',oldplan)
 bundle=copy.deepcopy(art['bundle'])
 cached=io.get(authorization['balances_key']);current=io.get(authorization['campaigns_key'])
 if not cached or not current:raise ValueError('Dated approved balance/composition snapshot missing')
 balances={r['advertId']:r for r in cached['data']['adverts']};campaigns={r['id']:r for r in current['rows']}
 for c in bundle['campaigns']:
  if c['id'] not in balances:continue
  b=balances[c['id']];config=campaigns.get(c['id'])
  if b.get('currency')!='CNY' or not config or config.get('currency')!='CNY':raise ValueError('CNY identity mismatch')
  c['balance']=b['total'];c['status']=config['status']
  c['current_articles']=[dict(nm=n['nm_id']) for n in config['nm_settings']]
 source=io.get('china_agent:advertising_source:'+DAY+':v2') or {}
 minimum=(source.get('config') or {}).get('minTopUp',10000)/100
 bundle=reserve(bundle,minimum)
 at=datetime.fromisoformat(cached['observed_at'].replace('Z','+00:00')).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow'))
 bundle['budget_balance_observed_at']=at.strftime('%d.%m %H:%M МСК')
 files=[]
 for i,f in enumerate(render(bundle)):
  if f['family']!='budgets':continue
  p=plan(io,DAY,f,i,slot='budget-format-v1')
  files.append(dict(kind=f['kind'],family='budgets',page=f['page'],total=f['total'],b64=base64.b64encode(f['bytes']).decode(),sha256=hashlib.sha256(f['bytes']).hexdigest(),plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],action_count=len(p['items'])))
 if not files:raise ValueError('Budget replacement missing')
 e=dict(status='prepared',day=DAY,created_at=stamp(),files=files,bundle=bundle,delete=dict(message_id=OLD,status='ready'),wb_writes=0)
 if not io.create(ROOT,e):raise ValueError('Concurrent replacement')
 return e
def apply(io):
 validate(io.get(INPUT));e=io.get(ROOT)
 if not e:raise ValueError('Prepare and review before applying')
 if e['status']=='completed':return e
 files=[]
 for f in e['files']:
  raw=base64.b64decode(f['b64'],validate=True)
  if hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('Frozen updated photo changed')
  files.append(dict(f,bytes=raw,caption='Китай · бюджеты · '+DAY+' · обновлено по просьбе владельца. Новых действий: '+str(f['action_count'])+'. '+('Ответьте «делай» на этот PNG для подтверждения указанных сумм.' if f['action_count'] else 'Пополнения к исполнению не предложены.')))
 result=deliver(io,DAY,files,telegram_sender(io),delivery_key=ROOT+':delivery',expected_families={'budgets'})
 for f,part in zip(e['files'],result['parts']):
  receipt=part['receipt']
  if receipt.get('from',{}).get('id')!=BOT or receipt.get('chat',{}).get('id')!=CHAT or part['sha256']!=f['sha256']:raise ValueError('New budget receipt mismatch')
  bind(io,f,receipt)
  p=io.get(PLAN+f['plan_id']);p['visible_from']=datetime.fromtimestamp(receipt['date'],timezone.utc).isoformat();p['owner_revision']=ROOT;io.put(PLAN+p['plan_id'],p)
 previous=io.get(ROOT+':before_plan')
 if previous:
  previous.update(invalidated_at=e['created_at'],invalidation_reason='Budget PNG replaced by explicit owner request29Oct',replacement_revision=ROOT);io.put(PLAN+previous['plan_id'],previous)
 e['status']='sent_bound';io.put(ROOT,e)
 deletion=e['delete']
 if deletion['status']=='ready':
  deletion.update(status='submitting',submitted_at=stamp());io.put(ROOT,e)
  try:
   answer=requests.post('https://api.telegram.org/bot'+io.bot+'/deleteMessage',json=dict(chat_id=CHAT,message_id=OLD),timeout=40).json()
  except Exception:
   deletion['status']='uncertain';io.put(ROOT,e);raise RuntimeError('Deletion uncertain; no blind retry') from None
  absent=answer.get('error_code')==400 and 'message to delete not found' in str(answer.get('description','')).lower()
  if not(answer.get('ok') and answer.get('result') is True or absent):
   deletion.update(status='rejected',error_code=answer.get('error_code'));io.put(ROOT,e);raise RuntimeError('Old budget deletion rejected')
  deletion.update(status='deleted',receipt=answer,deleted_at=stamp());io.put(ROOT,e)
 elif deletion['status']!='deleted':raise ValueError('Deletion uncertain; no automatic repeat')
 oldart=io.get(ROOT+':before_artifacts');olddel=io.get(ROOT+':before_delivery')
 newart=copy.deepcopy(oldart);newart['files']=[f for f in oldart['files'] if f['family']!='budgets']+[{k:v for k,v in f.items() if k!='sha256'} for f in e['files']]
 newart.update(bundle=e['bundle'],owner_revision=ROOT,original_archive=ROOT+':before_artifacts')
 newdel=copy.deepcopy(olddel);newdel['parts']=[p for p in olddel['parts'] if p['kind'].split(':')[0]!='budgets']+copy.deepcopy(result['parts'])
 newdel.update(owner_revision=ROOT,original_archive=ROOT+':before_delivery')
 for key,value,original in [(ART,newart,oldart),(DEL,newdel,olddel)]:
  current=io.get(key)
  if current!=original and current.get('owner_revision')!=ROOT:raise ValueError('Concurrent canonical report change')
  io.put(key,value)
 e.update(status='completed',completed_at=stamp(),new_message_ids=[p['message_id'] for p in result['parts']]);io.put(ROOT,e)
 return e
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or str(datetime.now(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date())!=DAY:raise ValueError('Dated public main only')
 io=NoMarketIO();mode=sys.argv[1:]
 e=prepare(io) if mode==['--prepare'] else apply(io) if mode==['--apply'] else None
 if not e:raise ValueError('Choose prepare or apply')
 print(json.dumps(dict(status=e['status'],wb_writes=0,message_ids=e.get('new_message_ids',[]))))
if __name__=='__main__':run()
