"""Exact owner-approved replacement of four erroneous bot answers; no WB requests."""
import os,json,base64,io as bytesio,requests,time
from datetime import datetime,timezone,timedelta
from china_price_apply import IO
K='china_agent:codex_reply_replacement:2026-10-25:v1';E=K+':execution'
CHAT=-1004342917488;BOT=8780468043
def run():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
 db=IO();p=db.get(K);assert p['status']=='approved' and p['source']=='explicit_human_codex_message'
 assert p['chat_id']==CHAT and p['bot_id']==BOT
 e=db.get(E)
 if e and e.get('status')=='completed':print(json.dumps(dict(status='already_completed',telegram_writes=0)));return
 assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
 def call(method,body=None,photo=None):
  url='https://api.telegram.org/bot'+db.bot+'/'+method
  if photo is None:r=requests.post(url,json=body,timeout=45)
  else:r=requests.post(url,data=body,files={'photo':('report.png',photo,'image/png')},timeout=60)
  j=r.json()
  if not r.ok or not j.get('ok'):
   raise RuntimeError('Telegram '+method+' rejected code '+str(j.get('error_code')))
  return j['result']
 assert call('getMe')['id']==BOT
 member=call('getChatMember',dict(chat_id=CHAT,user_id=p['owner_user_id']))
 assert member['status'] in ['creator','administrator','member'] and member['user']['id']==p['owner_user_id']
 receipts=[]
 for jid,mid in zip(p['job_ids'],p['message_ids']):
  key='china_agent:conversion_watch_delivery:v1:question:'+str(jid)+':0'
  receipt=db.get(key);assert receipt['chat_id']==CHAT and receipt['message_id']==mid and receipt['status']=='sent'
  receipts.append(dict(job_id=jid,key=key,receipt=receipt))
 preview=db.get('china_agent:dialog_recovery_preview:2026-10-25:v1');assert preview['status']=='verified_preview'
 source=db.get('china_agent:owner_profit_compare:2026-10-24:2026-10-25:v1')
 launch=db.get('china_agent:advertising_launch_summary:v1');assert launch['status']=='verified'
 assert preview['bundle']['intraday'] and preview['bundle']['view_only']
 assert all(not x.get('actions') for x in preview['parts'])
 day='2026-10-25';campaigns={}
 for batch in source['ad_batches']:
  for c in batch['data']:
   for d in c['days']:
    if d['date'][:10]==day:campaigns[c['advertId']]=d
 expense=sum(d['sum'] for d in campaigns.values());amount=sum(d['sum_price'] for d in campaigns.values());orders=sum(d['orders'] for d in campaigns.values())
 at=datetime.fromisoformat(source['observed_at']).astimezone(timezone(timedelta(hours=3))).strftime('%d.%m %H:%M МСК')
 def fmt(v):return f'{v:,.2f}'.replace(',',' ').replace('.',',')
 text1=('Сегодня,25.10, реклама уже расширена — исполнение подтверждено квитанциями WB.\n\n'
 'Рекомендации: добавлены120SKU:\n'
 '•41270309 — +27, всего29SKU;\n•41270471 — +13, всего16SKU;\n•41270474 — +19, всего22SKU;\n'
 '•Новая41296359 —31SKU;\n•Новая41296363 —30SKU.\n\n'
 'Отдельно запущен поиск CPC41298169 —44SKU; после согласованного исключения553 осталось43. Это отдельное размещение: складывать120 и44 в число уникальных товаров нельзя.\n\n'
 'Ставки тестов: сумки0,28¥/клик, зонты0,23¥/клик. Пополнено950¥ на рекомендательные тесты и500¥ на поиск; пополнение — не расход. Повторно добавлять уже подключённые товары не нужно. Дополнительных неподтверждённых изменений по этим сообщениям не выполнялось.')
 text2=('Результаты по сохранённому срезу '+at+' — сегодняшний день ещё не завершён.\n\n'
 'Весь рекламный кабинет: расход '+fmt(expense)+'¥; рекламная атрибуцияWB '+str(orders)+' заказов на '+fmt(amount)+'¥; ДРР '+fmt(expense/amount*100)+'%.\n\n')
 for cid in [41270309,41270471,41270474,41296359,41296363,41298169]:
  d=campaigns.get(cid)
  if not d:continue
  drr=fmt(d['sum']/d['sum_price']*100)+'%' if d['sum_price'] else 'не определена'
  text2+=str(cid)+': '+fmt(d['sum'])+'¥ / '+str(d['orders'])+' рекл.зак. / '+fmt(d['sum_price'])+'¥; ДРР '+drr+'.\n'
 text2+='\nНиже согласованный отчётPNG: общие данныеРК, затем артикулы и отдельные бюджеты. Время статистики и остатков подписано; старый срез не выдаётся за новый. ДРР — расход/сумма рекламных заказов до скидокWB. Это атрибуцияWB, не выкупы или прибыль. Новых запросов кWB и изменений рекламы при замене ответов нет.'
 texts=[(205,text1),(206,text2)]
 if not e:
  jobs=db.db('business_agent_jobs?agent_id=eq.china&id=in.(97,98,99,100)&select=id,request_text,answer,tool_trace,created_at,completed_at')
  e=dict(status='prepared',created_at=datetime.now(timezone.utc).isoformat(),original_receipts=receipts,original_jobs=jobs,texts=[dict(reply_to=reply,text=text) for reply,text in texts],deleted={},delivery={},wb_writes=0)
  assert db.create(E,e)
 def save():db.put(E,e)
 # Finish preparing/validating every replacement before removing the old answers.
 assert len(e['original_receipts'])==4 and len(preview['parts'])>0
 for item in e['original_receipts']:
  mid=item['receipt']['message_id'];key=str(mid)
  if e['deleted'].get(key,{}).get('status')=='deleted':continue
  e['deleted'][key]=dict(status='deleting',at=datetime.now(timezone.utc).isoformat());save()
  result=call('deleteMessage',dict(chat_id=CHAT,message_id=mid));assert result is True
  e['deleted'][key]=dict(status='deleted',at=datetime.now(timezone.utc).isoformat());save()
  old=db.get(item['key']);old['owner_deleted']=True;old['replacement_execution']=E;db.put(item['key'],old)
 def deliver(label,reply,text=None,photo=None,caption=None):
  prior=e['delivery'].get(label)
  if prior:
   if prior['status']=='sent':return
   raise RuntimeError('Uncertain Telegram send; no blind resend')
  e['delivery'][label]=dict(status='sending',created_at=datetime.now(timezone.utc).isoformat());save()
  try:
   body=dict(chat_id=CHAT,reply_parameters=json.dumps(dict(message_id=reply,allow_sending_without_reply=True)) if photo else dict(message_id=reply,allow_sending_without_reply=True))
   if photo:
    body['caption']=caption;msg=call('sendPhoto',body,photo)
   else:
    body.update(text=text,disable_web_page_preview=True);msg=call('sendMessage',body)
   assert msg['chat']['id']==CHAT and msg['from']['id']==BOT and type(msg['message_id'])is int
  except Exception:
   e['delivery'][label]['status']='uncertain';save();raise
  e['delivery'][label].update(status='sent',message_id=msg['message_id']);save()
 for i,(reply,text) in enumerate(texts):deliver('text:'+str(i),reply,text=text)
 families={}
 for x in preview['parts']:families[x['family']]=families.get(x['family'],0)+1
 seen={}
 for i,x in enumerate(preview['parts']):
  family=x['family'];seen[family]=seen.get(family,0)+1
  label='Китай · '+('реклама' if family=='drr' else 'бюджеты')+' · '+at+' · '+str(seen[family])+'/'+str(families[family])+'. Просмотр; изменения не применены.'
  deliver('png:'+str(i),206,photo=base64.b64decode(x['base64']),caption=label);time.sleep(1.2)
 for jid in p['job_ids']:
  answer=text1 if jid in [97,98,99] else text2
  original=next(j for j in e['original_jobs'] if j['id']==jid)
  trace=original['tool_trace']+[dict(name='owner_approved_reply_replacement',execution_key=E,original_answer_archived=True,replacement_message_ids=[v['message_id'] for v in e['delivery'].values() if v['status']=='sent'])]
  db.db('business_agent_jobs?agent_id=eq.china&id=eq.'+str(jid),'PATCH',dict(answer=answer,tool_trace=trace))
 e.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat());save()
 print(json.dumps(dict(status='completed',deleted=len(e['deleted']),sent_parts=len(e['delivery']),wb_writes=0)))
if __name__=='__main__':
 try:run()
 except Exception as exc:
  print(json.dumps(dict(status='stopped_for_private_receipt_review',error_type=type(exc).__name__,wb_writes=0)));raise SystemExit(1)
