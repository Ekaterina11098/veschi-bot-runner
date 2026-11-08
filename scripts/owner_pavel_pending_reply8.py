"""Owner-authorized replies to two saved Pavel questions; no WB client or model."""
import os,json
from urllib.parse import urlencode
from datetime import datetime,timezone
import requests
from china_codex_cloud import DB,CHAT,BOT
REPLIES={
264:(758,'Отдельного «прежнего агента» нет — я неверно выразился. Пишите этому же боту без /codex. Команды к актуальному PNG исполняются с проверкой WB. Ваши 7 изменений ставок уже проверены WB, результат — в ответе на команду. Исключения не выполнялись.'),
263:(754,'59, 63, 668, 527 и 144 ещё не запущены. Это было предварительное предложение, без готового плана запуска. Свежая экономика и наличие есть; ещё нужны точные РК, минимальные ставки, бюджет и проверка прежних исключений. Запрос на запуск сохраняю; выполненным его не считаю.')}
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 db=DB()
 e=db.get('china_agent:daily_ad_execution:v2:daily-2026-11-08-drr-0-bids-job265')or{}
 if e.get('wb_writes')!=7 or len(e.get('items',[]))!=7 or any(x.get('status')!='verified'for x in e['items']):raise ValueError('Seven changes not verified')
 notice=db.get('china_agent:daily_ad_result:v2:daily-2026-11-08-drr-0-bids-job265')or{}
 if notice.get('status')!='sent' or notice.get('message_id')!=762:raise ValueError('Execution notice not delivered')
 for jid,(mid,text)in REPLIES.items():
  rows=db.api('GET','business_agent_jobs',{'id':'eq.'+str(jid),'select':'id,chat_id,sender_id,tool_trace'})
  if len(rows)!=1 or rows[0].get('chat_id')!=CHAT or rows[0].get('sender_id')!=307200273:raise ValueError('Question scope changed')
  m=next((x for x in rows[0].get('tool_trace',[])if x.get('name')=='china_saved_question'),{})
  if m.get('bot_id')!=BOT or m.get('message_id')!=mid:raise ValueError('Original message changed')
  key='china_agent:owner_pavel_repair:2026-11-08:v1:'+str(jid);old=db.get(key)
  if old:print(json.dumps({'job_id':jid,'status':old['status']}));continue
  state={'status':'sending','job_id':jid,'chat_id':CHAT,'bot_id':BOT,'input_message_id':mid,'text':text,'created_at':datetime.now(timezone.utc).isoformat(),'wb_writes':0,'model_calls':0}
  db.once(key,state)
  try:
   r=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/sendMessage',json={'chat_id':CHAT,'text':text,'reply_parameters':{'message_id':mid,'allow_sending_without_reply':False}},timeout=35)
   if not r.ok:raise RuntimeError('Telegram HTTP '+str(r.status_code))
   value=r.json()
   receipt=value.get('result',{})
   if value.get('ok')is not True or receipt.get('chat',{}).get('id')!=CHAT or receipt.get('from',{}).get('id')!=BOT or type(receipt.get('message_id'))is not int:raise ValueError('Delivery scope mismatch')
   state.update(status='sent',message_id=receipt['message_id'],receipt=receipt);db.update(key,state,'sending')
   resolution={'status':'answered_by_owner','chat_id':CHAT,'message_id':receipt['message_id'],'receipt_key':key,'answer':text}
   rk='china_agent:owner_dialog_resolution:v1:job:'+str(jid)
   if not db.get(rk):db.once(rk,resolution)
   print(json.dumps({'job_id':jid,'status':'sent','message_id':receipt['message_id']}))
  except Exception as exc:
   db.update(key,state|{'status':'uncertain','error_type':type(exc).__name__},'sending');raise RuntimeError('Reply outcome uncertain; no repeat')from None
if __name__=='__main__':main()
