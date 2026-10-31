"""Owner-authorized31Oct display-only revision. Edits545 only; archives old image and binding; no WB reads/writes."""
import base64,copy,hashlib,json,os,sys
from datetime import datetime,timezone
import requests
from china_advertising_state import AdvertisingIO
from china_advertising_v2 import MSK
from china_advertising_v2_png import render
from china_daily_ad_actions import plan,BIND
from china_loss_control import PLAN,digest
DAY='2026-10-31'
INPUT='china_agent:morning_correction:'+DAY+':compact545_input:v1'
ROOT='china_agent:morning_correction:'+DAY+':compact545:v1'
ART='china_agent:advertising_artifacts:'+DAY+':v2'
DEL='china_agent:advertising_delivery:'+DAY+':v1'
LOSS='china_agent:loss_report:'+DAY+':v2'
CHAT=-1004342917488;BOT=8780468043;OWNER=5122667182

def stamp():return datetime.now(timezone.utc).isoformat()
def validate_input(p):
 if not p or p.get('day')!=DAY or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT or p.get('owner_id')!=OWNER or p.get('wb_writes')!=0:raise ValueError('Correction identity mismatch')
 if p.get('edit_message_ids')!=[545] or p.get('delete_message_ids')!=[] or p.get('authorization')!='owner_explicit_request_in_codex_2026-10-31':raise ValueError('Correction scope mismatch')
 if p.get('bundle',{}).get('day')!=DAY:raise ValueError('Report day mismatch')

def archive(io,key,value):
 old=io.get(key)
 if old is not None:
  if old!=value:raise ValueError('Correction archive changed')
 elif not io.create(key,value):
  if io.get(key)!=value:raise ValueError('Correction archive race')

def prepare(io):
 p=io.get(INPUT);validate_input(p)
 prior=io.get(ROOT)
 if prior:return prior
 delivery=io.get(DEL);artifact=io.get(ART)
 if delivery.get('status')!='delivered' or delivery['parts'][0]['message_id']!=545:raise ValueError('Original advertising receipt missing')
 if len(artifact['files'])!=2:raise ValueError('Unexpected original image count')
 for f,r in zip(artifact['files'],delivery['parts']):
  raw=base64.b64decode(f['b64'],validate=True)
  if f['kind']!=r['kind'] or hashlib.sha256(raw).hexdigest()!=r['sha256'] or r['receipt']['from']['id']!=BOT or r['receipt']['chat']['id']!=CHAT:raise ValueError('Original PNG receipt mismatch')
 archive(io,ROOT+':before_artifacts',artifact);archive(io,ROOT+':before_delivery',delivery)
 files=[]
 for i,f in enumerate(f for f in render(p['bundle']) if f['family']=='drr'):
  if f['kind']!='drr:001':raise ValueError('Correction must remain two PNGs')
  newplan=plan(io,DAY,f,i,slot='owner-compact31-v1')
  original=io.get(BIND+str(545+i))
  if not original:raise ValueError('Original reply binding missing')
  files.append(dict(kind=f['kind'],family=f['family'],page=f['page'],total=f['total'],b64=base64.b64encode(f['bytes']).decode(),sha256=hashlib.sha256(f['bytes']).hexdigest(),plan_id=newplan['plan_id'],plan_sha256=newplan['plan_sha256'],action_count=len(newplan['items']),message_id=545+i,status='prepared',old_binding=original))
 if [f['kind'] for f in files]!=['drr:001']:raise ValueError('Ordered PNG pair required')
 record=dict(status='prepared',day=DAY,chat_id=CHAT,bot_id=BOT,owner_id=OWNER,created_at=stamp(),files=files,wb_writes=0,telegram_sends=0,bundle=p['bundle'],authorization=p['authorization'])
 if not io.create(ROOT,record):raise ValueError('Concurrent correction')
 return record

def apply(io):
 p=io.get(INPUT);validate_input(p)
 if p.get('status')!='approved_after_visual_check':raise ValueError('Reviewed correction input required')
 e=io.get(ROOT)
 if not e:raise ValueError('Prepare correction first')
 if e['status']=='completed':return e
 if e.get('day')!=DAY or e.get('chat_id')!=CHAT:raise ValueError('Correction journal scope')
 me=io.tg('getMe',{})
 if me.get('id')!=BOT:raise ValueError('China bot identity')
 for uid in [OWNER,BOT]:
  member=io.tg('getChatMember',dict(chat_id=CHAT,user_id=uid))
  if member.get('status') in ['left','kicked'] or member.get('user',{}).get('id')!=uid:raise ValueError('Group membership changed')
 def save():io.put(ROOT,e)
 def publish_binding(f):
  result=f['receipt'];new=io.get(PLAN+f['plan_id'])
  if new['plan_sha256']!=f['plan_sha256'] or digest(new['items'])!=f['plan_sha256']:raise ValueError('New plan hash mismatch')
  new['report_message_ids']=[f['message_id']]
  new['visible_from']=datetime.fromtimestamp(result.get('edit_date',int(datetime.now(timezone.utc).timestamp())),timezone.utc).isoformat()
  new['owner_revision']=ROOT;io.put(PLAN+new['plan_id'],new)
  binding=dict(plan_id=new['plan_id'],plan_sha256=new['plan_sha256'],chat_id=CHAT,family=f['family'],owner_revision=ROOT)
  previous=io.get(BIND+str(f['message_id']))
  if previous not in [f['old_binding'],binding]:raise ValueError('Reply binding changed during correction')
  io.put(BIND+str(f['message_id']),binding);f['status']='bound';save()
 for f in e['files']:
  if f['message_id'] not in [545]:raise ValueError('Unexpected edit target')
  if f['status']=='bound':continue
  if f['status']=='edited':
   publish_binding(f);continue
  if f['status']!='prepared':raise ValueError('Telegram edit uncertain; no blind retry')
  data=base64.b64decode(f['b64'],validate=True)
  if hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('Frozen replacement PNG changed')
  caption='Китай · '+('реклама' if f['family']=='drr' else 'бюджеты')+' · '+DAY+' · исправлено по проверке владельца. ДРР день: 30.10; 3 дня: 28–30.10. '
  caption+=('Новых действий: '+str(f['action_count'])+'. Ответьте «Сделай всё» только на обновлённый PNG.' if f['action_count'] else 'Новых действий для исполнения нет.')
  oldplan=io.get(PLAN+f['old_binding']['plan_id'])
  if not oldplan:raise ValueError('Previous plan missing')
  archive(io,ROOT+':before_plan:'+oldplan['plan_id'],oldplan)
  oldplan.update(invalidated_at=stamp(),invalidation_reason='Owner requested compact recommendations: new action or Не требуется; no execution authorized')
  io.put(PLAN+oldplan['plan_id'],oldplan)
  f.update(status='submitting',caption=caption,submitted_at=stamp());e['status']='editing';save()
  media=dict(type='photo',media='attach://photo',caption=caption)
  try:
   response=requests.post('https://api.telegram.org/bot'+io.bot+'/editMessageMedia',data=dict(chat_id=str(CHAT),message_id=str(f['message_id']),media=json.dumps(media,ensure_ascii=False)),files={'photo':('corrected.png',data,'image/png')},timeout=60).json()
  except Exception:raise RuntimeError('Telegram edit uncertain; no automatic repeat') from None
  if not response.get('ok'):
   f.update(status='rejected',error_code=response.get('error_code'));save();raise RuntimeError('Telegram rejected correction')
  result=response['result']
  if result.get('message_id')!=f['message_id'] or result.get('chat',{}).get('id')!=CHAT or result.get('from',{}).get('id')!=BOT:raise RuntimeError('Telegram edit receipt mismatch')
  f.update(status='edited',receipt=result,edited_at=stamp());save();publish_binding(f)
 # Preserve the original frozen artifacts/receipts in immutable private archives.
 original=io.get(ROOT+':before_artifacts');old_delivery=io.get(ROOT+':before_delivery')
 newfiles=[{k:f[k] for k in ['kind','family','page','total','plan_id','plan_sha256','action_count','b64']} for f in e['files']]+original['files'][1:]
 updated=dict(original,bundle=e['bundle'],files=newfiles,owner_revision=ROOT,original_archive=ROOT+':before_artifacts')
 io.put(ART,updated)
 updated_delivery=copy.deepcopy(old_delivery)
 for part,f in zip(updated_delivery['parts'],e['files']):
  if part['message_id']!=f['message_id']:raise ValueError('Delivery identity changed')
  part.update(sha256=f['sha256'],receipt=f['receipt'],edited_at=f['edited_at'],owner_revision=ROOT)
 updated_delivery['owner_revision']=ROOT;updated_delivery['original_archive']=ROOT+':before_delivery'
 io.put(DEL,updated_delivery)
 e.update(status='completed',completed_at=stamp());save();return e

def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or str(datetime.now(MSK).date())!=DAY:raise ValueError('Dated public main only')
 io=AdvertisingIO()
 mode=sys.argv[1:] 
 if mode==['--prepare']:
  p=io.get(INPUT)
  if not p or p.get('status')!='owner_authorized_prepare':raise ValueError('Owner preparation authorization missing')
  validate_input(dict(p,bundle=dict(day=DAY)))
  p['bundle']=io.get(ART)['bundle'];p['status']='pending_visual_review';io.put(INPUT,p)
  e=prepare(io)
 elif mode==['--apply']:e=apply(io)
 else:raise ValueError('Expected explicit preparation or application')
 print(json.dumps(dict(status=e['status'],wb_writes=0,telegram_sends=0,edited=sum(f['status']=='bound' for f in e['files']) ,deleted=0)))
if __name__=='__main__':run()


