"""Update exact existing Telegram messages after verified accepted launch, no WB calls."""
import base64,hashlib,importlib.util,json,os
from datetime import datetime,timezone
import requests
from china_codex_cloud import DB
from china_loss_control import PLAN,CHAT,BOT
from china_new_ads import BIND,EXEC
from china_new_ad_reports import render
db=DB();pid='new-ad-test-270-final-v3';p=db.get(PLAN+pid);e=db.get(EXEC+pid)or{}
if e.get('status')!='done' or len(e.get('campaigns',[]))!=2 or any(s.get('status')!='launched'or(s.get('verified_after')or{}).get('status')!=9 for s in e['campaigns']):raise RuntimeError('Actual verified launch incomplete; do not claim success')
rows={int(k):v for k,v in p['candidate_evidence'].items()}
spec=importlib.util.spec_from_file_location('previous_proposal_renderer','previous-render/scripts/china_new_ad_reports.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
args=(p,rows,'2026-10-09 — 2026-11-07',p['source_observed_at']);before=old.render(*args);after=render(*args)
token=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
def tg(method,data,files=None):
 try:
  result=requests.post('https://api.telegram.org/bot'+token+'/'+method,data=data,files=files,timeout=45).json()
  if not result.get('ok'):raise RuntimeError('Telegram rejected')
  return result['result']
 except Exception:raise RuntimeError('Telegram outcome requires receipt review; no retry')from None
def verify(r,mid):
 if r.get('message_id')!=mid or r.get('chat',{}).get('id')!=CHAT or r.get('from',{}).get('id')!=BOT:raise ValueError('Edited message identity mismatch')
 return {k:r.get(k)for k in('message_id','chat','from','edit_date','caption','text')}
if tg('getMe',{}).get('id')!=BOT:raise ValueError('Wrong bot')
caption='План уже подтверждён и выполнен: 2 РК, 6 товаров, CPC 0,28 CNY. Внесено по 100 CNY на РК. Повторять «делай» не нужно.'
for i,mid in enumerate([787,788]):
 key='china_agent:owner_no_limits_tg_edit:2026-11-08:v1:'+str(mid);prior=db.get(key)
 if prior:
  if prior.get('status')=='edited_verified':continue
  raise RuntimeError('Uncertain prior edit; no repeat')
 part=pid if i==0 else pid+'-page-1';dk='china_agent:new_ad_delivery:v1:'+part
 receipt=db.get(dk);binding=db.get(BIND+str(mid));partplan=db.get(PLAN+part)
 if receipt.get('message_id')!=mid or binding.get('plan_id')!=pid:raise ValueError('Exact original binding mismatch')
 oldsha=hashlib.sha256(before[i]).hexdigest();newsha=hashlib.sha256(after[i]).hexdigest()
 if oldsha!=receipt['png_sha256']:raise ValueError('Original reconstruction mismatch; no media edit')
 db.once(key+':archive',dict(plan=partplan,delivery=receipt,binding=binding,original_png=base64.b64encode(before[i]).decode(),original_png_sha256=oldsha))
 db.once(key,dict(status='editing_uncertain',chat_id=CHAT,message_id=mid,old_png_sha256=oldsha,new_png_sha256=newsha))
 result=tg('editMessageMedia',dict(chat_id=CHAT,message_id=mid,media=json.dumps(dict(type='photo',media='attach://photo',caption=caption),ensure_ascii=False)),{'photo':('china-final-no-daily-limits.png',after[i],'image/png')})
 check=verify(result,mid)
 db.update(key,dict(status='edited_verified',chat_id=CHAT,message_id=mid,receipt=check,png_sha256=newsha,edited_at=datetime.now(timezone.utc).isoformat()))
 db.update(dk,dict(receipt,png_sha256=newsha,no_limits_edit_receipt_key=key))
 db.update(BIND+str(mid),dict(binding,png_sha256=newsha))
 db.update(PLAN+part,dict(partplan,png_sha256=newsha,no_limits_edit_receipt_key=key))
result_text='Запущено и проверено в WB:\nРК 41680341 — 144, 575, 578, 55.\nРК 41680449 — 455, 84.\nРекомендации, CPC 0,28 CNY; внесено по 100 CNY, всего 200 CNY. Дневные лимиты не устанавливались при восстановлении. Повторное подтверждение не нужно.'
for mid,receiptkey,text in [
 (795,'china_agent:new_ad_result:v1:'+pid,result_text),
 (794,'china_agent:conversion_watch_delivery:v1:question:273:0','Актуальный план уже был подтверждён первым ответом «Делай» и теперь выполнен. Второй ответ пришёл на прежний PNG. Повторять подтверждение не нужно; новые РК повторно не создаются.')]:
 key='china_agent:owner_no_limits_tg_edit:2026-11-08:v1:'+str(mid);prior=db.get(key)
 if prior:
  if prior.get('status')=='edited_verified':continue
  raise RuntimeError('Previous text edit uncertain')
 receipt=db.get(receiptkey)
 if not receipt or receipt.get('status')!='sent' or receipt.get('message_id')!=mid:raise ValueError('Text delivery identity missing')
 db.once(key+':archive',receipt);db.once(key,dict(status='editing_uncertain',chat_id=CHAT,message_id=mid))
 result=tg('editMessageText',dict(chat_id=CHAT,message_id=mid,text=text));check=verify(result,mid)
 db.update(key,dict(status='edited_verified',chat_id=CHAT,message_id=mid,receipt=check,edited_at=datetime.now(timezone.utc).isoformat()))
 db.update(receiptkey,dict(receipt,text=text,chat_id=CHAT,no_limits_edit_receipt_key=key))
print(json.dumps({'status':'edited_verified','message_ids':[787,788,794,795],'wb_writes':0,'new_messages':0}))
