"""Edit only two owner-specified final PNG messages; no WB credentials or calls."""
import base64,copy,hashlib,json,os,types
from datetime import datetime,timezone
import requests
from china_codex_cloud import DB
from china_new_ad_reports import render
from china_loss_control import PLAN,CHAT,BOT
from china_new_ads import BIND

db=DB();pid='new-ad-test-270-final-v3';p=db.get(PLAN+pid)
if not p or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT or p.get('report_message_ids')!=[787,788]:raise ValueError('Exact current plan/message scope changed')
rows={int(k):v for k,v in p['candidate_evidence'].items()}
new='Расчёт по фактическому собственному выкупу, не плановым 40%. Прибыль предварительная; ДРР 5% — сценарий, неизвестные расходы не ноль.'
old='Экономика предварительная: сценарий ДРР 5%, не доказанная прибыль. Неизвестные расходы не ноль; выборка выкупа указана.'
def previous(code):
 return code.replace(co_consts=tuple(previous(c)if isinstance(c,types.CodeType)else old if c==new else c for c in code.co_consts))
old_render=types.FunctionType(previous(render.__code__),render.__globals__)
args=(p,rows,'2026-10-09 — 2026-11-07',p['source_observed_at'])
images=render(*args);originals=old_render(*args)
if len(images)!=2 or len(originals)!=2:raise ValueError('Unexpected image count')
caption='Новых РК: 2 · товаров: 6 · 200 ¥ всего. Пока не запущены. Ответьте на этот PNG «делай» для запуска только указанного плана.'
token=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
def tg(method,data,files=None):
 try:
  r=requests.post('https://api.telegram.org/bot'+token+'/'+method,data=data,files=files,timeout=45)
  if not r.ok:raise RuntimeError('Telegram HTTP '+str(r.status_code))
  value=r.json()
  if not value.get('ok'):raise RuntimeError('Telegram rejected edit')
  return value['result']
 except Exception:raise RuntimeError('Telegram transport failed; inspect journal, no automatic retry')from None
if tg('getMe',{}).get('id')!=BOT or tg('getChat',dict(chat_id=CHAT)).get('id')!=CHAT:raise ValueError('Telegram identity mismatch')
for index,mid in enumerate([787,788]):
 part=pid if index==0 else pid+'-page-1';dk='china_agent:new_ad_delivery:v1:'+part
 delivery=db.get(dk);binding=db.get(BIND+str(mid));partplan=db.get(PLAN+part)
 if not delivery or delivery.get('status')!='sent' or delivery.get('message_id')!=mid or not binding or binding.get('plan_id')!=pid or binding.get('plan_sha256')!=p['plan_sha256']:raise ValueError('Exact visible delivery binding mismatch')
 key='china_agent:owner_png_label_edit:2026-11-08:v1:'+str(mid)
 existing=db.get(key)
 if existing:
  if existing.get('status')=='edited_verified':continue
  raise RuntimeError('Previous edit outcome uncertain; no retry')
 before=hashlib.sha256(originals[index]).hexdigest();after=hashlib.sha256(images[index]).hexdigest()
 if before!=delivery['png_sha256']:raise ValueError('Reconstructed original differs; no edit or overwrite')
 archive=dict(status='archived_before_edit',chat_id=CHAT,bot_id=BOT,message_id=mid,plan=partplan,parent_plan=p,delivery=delivery,binding=binding,original_png=base64.b64encode(originals[index]).decode(),png_sha256=before)
 db.once(key+':archive',archive)
 state=dict(status='editing_uncertain',chat_id=CHAT,bot_id=BOT,message_id=mid,old_png_sha256=before,new_png_sha256=after,plan_sha256=p['plan_sha256'],owner_source='Owner Codex8Nov: поменяй в ТГ',started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 db.once(key,state)
 result=tg('editMessageMedia',dict(chat_id=CHAT,message_id=mid,media=json.dumps(dict(type='photo',media='attach://photo',caption=caption),ensure_ascii=False)),files={'photo':('china-final-buyout-label.png',images[index],'image/png')})
 if result.get('message_id')!=mid or result.get('chat',{}).get('id')!=CHAT or result.get('from',{}).get('id')!=BOT or not result.get('photo') or result.get('caption')!=caption:raise RuntimeError('Edited message scope/readback mismatch')
 # Keep action hash, exact message IDs, expiry and selection unchanged.
 state.update(status='edited_verified',edited_at=datetime.now(timezone.utc).isoformat(),receipt={k:result.get(k)for k in ('message_id','chat','from','date','edit_date','caption')},photo_sha256=after)
 db.update(key,state)
 db.update(dk,dict(delivery,png_sha256=after,label_edit_receipt_key=key,last_edit_at=state['edited_at']))
 db.update(BIND+str(mid),dict(binding,png_sha256=after))
 db.update(PLAN+part,dict(partplan,png_sha256=after,label_edit_receipt_key=key))
print(json.dumps({'status':'edited_verified','message_ids':[787,788],'wb_writes':0,'new_messages':0}))
