"""Owner migration shadow checks, existing private data only. No WB or Telegram credentials."""
import os,json,base64,hashlib
from datetime import datetime,timezone
from china_codex_cloud import DB,Worker,INSTRUCTIONS,envelope,CHAT,SENDERS,CLOUD
from china_codex_analysis import Core,digest
from china_codex_reports import review_advertising,review_price
from china_midday_completed_review import merge_completed
from china_advertising_midday import only_completed_day_actions,render_midday
ROOT='china_agent:cloud_migration:2026-11-03:v1'
def main():
 db=DB()
 if (db.get(ROOT+':approval')or{}).get('owner_user_id')!=5122667182:raise ValueError('Migration approval missing')
 if db.get(ROOT+':shadow_result'):print('Already checked');return
 state={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'wb_writes':0,'telegram_sends':0}
 if not db.get(ROOT+':shadow_state'):db.once(ROOT+':shadow_state',state)
 try:
  old=db.get('china_agent:owner_midday_corrected:2026-11-03:v1:reviewed_completed')
  observed=db.get('china_agent:owner_midday_corrected:2026-11-03:v1:reviewed_artifacts')['bundle']
  reviewed=review_advertising(None,old['review'],old['source'],'migration-shadow-ad3',observed,True)
  b=only_completed_day_actions(merge_completed(observed,reviewed,reviewed['codex_analysis']['key']))
  for c in b['campaigns']:
   match=next(x for x in reviewed['campaigns']if x['id']==c['id'])
   c['codex_research_recommendations']=match.get('codex_research_recommendations',[])
  b['codex_analysis']=reviewed['codex_analysis'];pages=render_midday(b)
  db.once(ROOT+':shadow_advertising',dict(status='complete',bundle=b,files=[dict(kind=f['kind'],b64=base64.b64encode(f['bytes']).decode(),sha256=hashlib.sha256(f['bytes']).hexdigest())for f in pages],source_channel='codex_cloud',wb_writes=0,telegram_sends=0))
  class Price:
   day='2026-11-03';mode='intraday';audit={'mode':'intraday','status':'sources_incomplete'}
   def get(self,key):return db.get(key)
  price_answer,trace=review_price(Price(),'Повышение: нет\n\nСнижение: нет данных',[],True)
  db.once(ROOT+':shadow_price',dict(answer=price_answer,trace=trace,status='complete',source_channel='codex_cloud'))
  sidkey='china_agent:codex_cloud:v2:session';session=db.get(sidkey)
  worker=Worker(db)
  if not session:
   with worker.sdk().beta.agents.sessions.create(agent={'model':'gpt-6.1-sol','instructions':INSTRUCTIONS},environment={'type':'none'},input='Это новая версия продолжающегося рабочего диалога VESCHI Китай. Общая рабочая память и последние ответы придут перед каждым вопросом. Ничего не отправляй и не меняй. Ответь только: Готова.',stream=True).with_result_collection() as events:
    for event in events:
     if event.type.endswith(('.failed','.cancelled')):raise RuntimeError('V2 bootstrap failed')
    sid=events.get_final_result().session_id
   session=dict(status='active',session_id=sid,created_at=datetime.now(timezone.utc).isoformat(),model='gpt-6.1-sol',version=2,environment='none',tools=[],instructions_revision='cloud-migration3')
   db.once(sidkey,session)
  token='migration3-read-protocol'
  request='Техническая проверка нового протокола без отправки людям. Нужен адресный свежий остаток МСК nm1535337770, результата stock в этом тестовом контексте нет. Верни ровно read JSON, topic stock, nm_ids [1535337770], date_from2026-11-03, date_to2026-11-03; реальный сбор этот тест не запускает.'
  text=worker.generate(session['session_id'],json.dumps(dict(job_token=token,request=request),ensure_ascii=False),token)
  parsed=envelope(text)
  if parsed.get('kind')!='read' or parsed.get('nm_ids')!=[1535337770]:raise ValueError('Read protocol failed')
  pointer=db.get('china_agent:hourly_sales_api:v1:latest');snap=db.get(pointer['source_key']);totals=snap['advertising']['totals']
  ctx=worker.context(dict(job_id=0,request_text='Какой расход и ДРР за сегодня?',sender_id=307200273))
  token='migration3-pavel-brief'
  text=worker.generate(session['session_id'],json.dumps(dict(job_token=token,runtime_scope=dict(sender_id=307200273,chat_id=CHAT,wb_action_permission=False),dated_work_context=ctx,untrusted_telegram_question='Какой расход и ДРР за сегодня? Ответь только этими двумя показателями с временем среза, очень кратко.'),ensure_ascii=False),token)
  parsed=envelope(text)
  if parsed.get('kind')!='answer' or len(parsed['answer'])>450:raise ValueError('Pavel brief check failed')
  db.once(ROOT+':shadow_pavel',dict(status='complete',answer=parsed['answer'],expected_ad_totals=totals,source_key=pointer['source_key'],source_channel='codex_cloud',session_key=sidkey))
  result=dict(status='verified',advertising_key=ROOT+':shadow_advertising',price_key=ROOT+':shadow_price',pavel_key=ROOT+':shadow_pavel',session_key=sidkey,completed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0)
  db.once(ROOT+':shadow_result',result);db.update(ROOT+':shadow_state',state|result);print(json.dumps(result))
 except Exception as ex:
  db.update(ROOT+':shadow_state',state|dict(status='blocked',error_type=type(ex).__name__,detail=str(ex)[:500],finished_at=datetime.now(timezone.utc).isoformat()))
  raise
if __name__=='__main__':main()
