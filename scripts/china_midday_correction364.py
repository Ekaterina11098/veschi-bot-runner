"""Owner-authorized correction of message364 only; cache-only inputs, no WB transport."""
import base64,copy,hashlib,json,os,sys
from datetime import datetime,timezone
import requests
from china_advertising_state import AdvertisingIO
from china_advertising_midday import current_report_context,revise_midday_bundle,render_midday
from china_advertising_v2 import MSK
from china_daily_ad_actions import plan,BIND
from china_loss_control import PLAN,digest
DAY='2026-10-27';MID=364;CHAT=-1004342917488;BOT=8780468043
ROOT='china_agent:midday_correction:2026-10-27:364:v2'
ART='china_agent:advertising_midday_artifacts:'+DAY+':v1'
DEL='china_agent:advertising_midday_delivery:'+DAY+':v1'
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
 if delivery.get('status')!='delivered' or len(delivery['parts'])!=1 or len(artifact['files'])!=1:raise ValueError('Original report scope')
 receipt=delivery['parts'][0];original=artifact['files'][0]
 if receipt['message_id']!=MID or receipt['receipt']['chat']['id']!=CHAT or receipt['receipt']['from']['id']!=BOT:raise ValueError('Original Telegram identity')
 if hashlib.sha256(base64.b64decode(original['b64'],validate=True)).hexdigest()!=receipt['sha256']:raise ValueError('Original artifact hash')
 old=io.get(PLAN+binding['plan_id'])
 if old['plan_sha256']!='35ffa906b4bb539696cfa20319fc89e60a0be520787ed0ca0a9c5e16c07a3b87' or digest(old['items'])!=binding['plan_sha256']:raise ValueError('Original plan changed')
 source=io.get(SOURCE)
 if source.get('status')!='complete':raise ValueError('Frozen source incomplete')
 records,context=current_report_context(io,source,DAY)
 corrected=revise_midday_bundle(artifact['bundle'],source,records)
 removed=corrected['correction']['removed_actions']
 if {a['nm_id'] for a in removed}!={1473243905,1473244000,1473243915,1473245499}:raise ValueError('Unexpected correction delta')
 actions=[a['action'] for c in corrected['campaigns'] for a in c['attention']]
 if len(actions)!=1 or actions[0]['nm_id']!=1473243917 or actions[0].get('target_minor')!=30:raise ValueError('Unexpected remaining action')
 # Funding and reported figures remain the original15:02 snapshot.
 corrected['review_context']=dict(corrected.get('review_context',{}),correction_registry=context['verified_registry'])
 files=render_midday(corrected)
 if len(files)!=1:raise ValueError('Correction must edit exactly one image')
 f=files[0];new=plan(io,DAY,f,0,slot='midday-owner-correction-v2')
 for key,value in [('artifacts',artifact),('delivery',delivery),('binding',binding),('plan',old)]:archive(io,ROOT+':before_'+key,value)
 # Revoke before making the replacement visible. Historical receipts stay intact.
 old.update(invalidated_at=stamp(),invalidation_reason='Premature exclusions before a complete post-change day; owner requested correction',replacement_plan_id=new['plan_id'])
 io.put(PLAN+old['plan_id'],old)
 record=dict(status='prepared',created_at=stamp(),day=DAY,message_id=MID,chat_id=CHAT,bot_id=BOT,authorization='owner_explicit_codex_request27Oct_fix_and_edit_midday',wb_writes=0,telegram_sends=0,bundle=corrected,file=dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],b64=base64.b64encode(f['bytes']).decode(),sha256=hashlib.sha256(f['bytes']).hexdigest(),plan_id=new['plan_id'],plan_sha256=new['plan_sha256'],action_count=len(actions)))
 if not io.create(ROOT,record):raise ValueError('Correction journal race')
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
  caption='Китай · промежуточный отчёт · '+DAY+' · исправлено. Четыре преждевременных исключения сняты: ждём полный день после запуска/изменения. Осталось 1 новое действие; ответьте «Сделай всё» только на обновлённый PNG. Срез данных15:02МСК.'
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
 artifact.update(bundle=e['bundle'],files=[{k:f[k] for k in ['kind','family','page','total','b64','plan_id','plan_sha256','action_count']}],owner_revision=ROOT,original_archive=ROOT+':before_artifacts')
 io.put(ART,artifact)
 delivery=io.get(ROOT+':before_delivery')
 delivery['parts'][0].update(receipt=receipt,sha256=f['sha256'],edited_at=e['edited_at'],owner_revision=ROOT)
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
