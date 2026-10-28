"""Owner-authorized correction of message364 only; cache-only inputs, no WB transport."""
import base64,copy,hashlib,json,os,sys
from datetime import datetime,timezone
import requests
from china_advertising_state import AdvertisingIO
from china_advertising_v2_png import render
from china_advertising_v2 import MSK
from china_daily_ad_actions import plan,BIND
from china_loss_control import PLAN,digest
DAY='2026-10-28';MID=376;CHAT=-1004342917488;BOT=8780468043
ROOT='china_agent:morning_correction:2026-10-28:376:v1'
ART='china_agent:advertising_artifacts:'+DAY+':v2'
DEL='china_agent:advertising_delivery:'+DAY+':v1'
SOURCE='china_agent:advertising_midday_source:'+DAY+':v2'
def stamp():return datetime.now(timezone.utc).isoformat()
def archive(io,key,value):
 old=io.get(key)
 if old is None:
  if not io.create(key,value):raise ValueError('Archive race')
 elif old!=value:raise ValueError('Archive changed')
def prepare(io):
 prior=io.get(ROOT)
 if prior:return prior
 artifact=io.get(ART);delivery=io.get(DEL);binding=io.get(BIND+str(MID))
 if delivery.get('status')!='delivered':raise ValueError('Daily not delivered')
 receipt=next(p for p in delivery['parts'] if p['message_id']==MID)
 original=next(f for f in artifact['files'] if f['family']=='drr')
 if receipt['receipt']['chat']['id']!=CHAT or receipt['receipt']['from']['id']!=BOT:raise ValueError('Telegram identity')
 if hashlib.sha256(base64.b64decode(original['b64'],validate=True)).hexdigest()!=receipt['sha256']:raise ValueError('Artifact hash')
 old=io.get(PLAN+binding['plan_id'])
 if old['plan_sha256']!='7ff31a5d42c3215ca3286aa90a737407815c3e75264ccee94568455708c9fa4f':raise ValueError('Unexpected original plan')
 corrected=copy.deepcopy(artifact['bundle'])
 keep={1473242754,1473246051};hold={1560345287,1473245000,1473244988,1473244000,1473244355}
 reasons={1560345287:'Малый расход и выборка; собственная экономика предварительно положительная.',1473245000:'Малая выкупная выборка; есть заказ на товар из другой РК. Остаток требует свежей проверки.',1473244988:'Малый трафик и небольшой запас маржи; оценить полный день 28.10.',1473244000:'17 корзин за 27.10; есть заказы из других РК. Их нельзя приписать собственным кликам.',1473244355:'5 корзин за 27.10; есть заказ из другой РК. Сначала итог полного дня 28.10.'}
 for c in corrected['campaigns']:
  for r in c['focus']:
   if r['nm'] in hold and (r.get('action') or {}).get('kind')=='ad_exclude_sku':
    r['action']=None;r['decision']='Продолжить тест без повышения; оценка 29.10.';r['reason']=reasons[r['nm']];r['owner_review']=ROOT
  c['attention']=[r for r in c['focus'] if r.get('action')]
  notes=[r['article']+': '+r['decision']+' '+r['reason'] for r in c['focus'] if r.get('owner_review')==ROOT]
  c['notes']+=notes
 corrected['owner_revision']=ROOT
 files=[f for f in render(corrected) if f['family']=='drr']
 if len(files)!=1:raise ValueError('Exactly one daily page required')
 f=files[0];actions=f['actions']
 if len(actions)!=4 or {a['nm_id'] for a in actions if a['kind']=='ad_exclude_sku'}!=keep:raise ValueError('Correction scope')
 new=plan(io,DAY,f,0,slot='owner-review376-v1')
 for key,value in [('artifacts',artifact),('delivery',delivery),('binding',binding),('plan',old)]:archive(io,ROOT+':before_'+key,value)
 old.update(invalidated_at=stamp(),invalidation_reason='Owner requested economics and postclick review; five exclusions withdrawn',replacement_plan_id=new['plan_id'])
 io.put(PLAN+old['plan_id'],old)
 record=dict(status='prepared',created_at=stamp(),day=DAY,message_id=MID,chat_id=CHAT,bot_id=BOT,authorization='owner_explicit_codex28Oct_replace_png_update_algorithm_only',wb_writes=0,telegram_sends=0,bundle=corrected,file=dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],b64=base64.b64encode(f['bytes']).decode(),sha256=hashlib.sha256(f['bytes']).hexdigest(),plan_id=new['plan_id'],plan_sha256=new['plan_sha256'],action_count=len(actions)))
 if not io.create(ROOT,record):raise ValueError('Correction race')
 return record

def apply(io):
 e=io.get(ROOT)
 if not e or e.get('visual_review')!='approved':raise ValueError('Prepared reviewed image required')
 if e['status']=='completed':return e
 if e['status'] not in ['prepared','edited']:raise ValueError('Uncertain edit; no blind retry')
 f=e['file'];oldbinding=io.get(ROOT+':before_binding');old=io.get(PLAN+oldbinding['plan_id'])
 if not old.get('invalidated_at'):raise ValueError('Old plan must be revoked')
 if io.tg('getMe',{}).get('id')!=BOT:raise ValueError('Bot identity')
 if e['status']=='prepared':
  if io.get(BIND+str(MID))!=oldbinding:raise ValueError('Original reply binding changed')
  raw=base64.b64decode(f['b64'],validate=True)
  if hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('Replacement bytes changed')
  e.update(status='submitting',submitted_at=stamp());io.put(ROOT,e)
  caption='Китай · реклама · '+DAY+' · исправлено после проверки экономики и заказов других товаров. Новых предложений: 4 (2 снижения ставок, исключения 98 и 650). Пять исключений сняты. Ответьте «Сделай всё» только на обновлённый PNG. Вчерашние тесты не повторяются.'
  media=dict(type='photo',media='attach://photo',caption=caption)
  try:
   response=requests.post('https://api.telegram.org/bot'+io.bot+'/editMessageMedia',data=dict(chat_id=str(CHAT),message_id=str(MID),media=json.dumps(media,ensure_ascii=False)),files={'photo':('midday-corrected.png',raw,'image/png')},timeout=60).json()
  except Exception:raise RuntimeError('Telegram edit uncertain; do not repeat') from None
  if not response.get('ok'):
   e.update(status='rejected',error_code=response.get('error_code'));io.put(ROOT,e);raise ValueError('Telegram edit rejected')
  receipt=response['result']
  if receipt.get('message_id')!=MID or receipt.get('chat',{}).get('id')!=CHAT or receipt.get('from',{}).get('id')!=BOT or not receipt.get('edit_date'):raise ValueError('Edit receipt identity')
  e.update(status='edited',receipt=receipt,edited_at=stamp());io.put(ROOT,e)
 receipt=e['receipt'];new=io.get(PLAN+f['plan_id'])
 if digest(new['items'])!=f['plan_sha256']:raise ValueError('Replacement plan digest')
 new.update(report_message_ids=[MID],visible_from=datetime.fromtimestamp(receipt['edit_date'],timezone.utc).isoformat(),owner_revision=ROOT)
 io.put(PLAN+new['plan_id'],new)
 binding=dict(plan_id=new['plan_id'],plan_sha256=new['plan_sha256'],chat_id=CHAT,family=f['family'],owner_revision=ROOT)
 if io.get(BIND+str(MID)) not in [oldbinding,binding]:raise ValueError('Binding race')
 io.put(BIND+str(MID),binding)
 artifact=io.get(ROOT+':before_artifacts')
 artifact.update(bundle=e['bundle'],files=[({k:f[k] for k in ['kind','family','page','total','b64','plan_id','plan_sha256','action_count']} if x['family']=='drr' else x) for x in artifact['files']],owner_revision=ROOT,original_archive=ROOT+':before_artifacts')
 io.put(ART,artifact)
 delivery=io.get(ROOT+':before_delivery')
 next(p for p in delivery['parts'] if p['message_id']==MID).update(receipt=receipt,sha256=f['sha256'],edited_at=e['edited_at'],owner_revision=ROOT)
 delivery.update(owner_revision=ROOT,original_archive=ROOT+':before_delivery')
 io.put(DEL,delivery)
 e.update(status='completed',completed_at=stamp());io.put(ROOT,e)
 return e
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or str(datetime.now(MSK).date())!=DAY:raise ValueError('Dated public main only')
 io=AdvertisingIO()
 if sys.argv[1:]==['--prepare']:e=prepare(io)
 elif sys.argv[1:]==['--apply']:e=apply(io)
 else:raise ValueError('Explicit mode required')
 print(json.dumps(dict(status=e['status'],message_id=MID,actions=e['file']['action_count'],wb_writes=0,telegram_sends=0)))
if __name__=='__main__':run()

