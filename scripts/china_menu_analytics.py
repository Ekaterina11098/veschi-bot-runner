"""Typed menu analytics: deterministic preparation, no model or marketplace writes."""
import base64,copy,hashlib,re
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
ROOT='china_agent:codex_bridge:v1:'
PREFIX='Общая воронка · запрос меню: '
CANDIDATES='Предложи новых кандидатов для рекламы китайского кабинета. '
LABELS={'add':'Добавление товаров','raise':'Повышение ставок','reduce':'Снижение ставок','exclude':'Исключение из РК'}
def recognized(text):return text.startswith((PREFIX,CANDIDATES))
def directions(text):
 if 'Все четыре направления:' in text:return list(LABELS)
 mapping={'add':'Новые товары для добавления','raise':'Новые повышения ставок.','reduce':'Новые снижения ставок.','exclude':'Новые исключения товаров'}
 result=[k for k,v in mapping.items() if v in text]
 if not result:raise ValueError('Направления подбора не указаны')
 return result
def freeze(w,job,answer,blobs):
 from china_table_png import KEY,PREFIX as PNG
 key=KEY+str(job['id']);parts=([answer]if job.get('sender_id')!=307200273 else [])+[PNG+key+':'+str(i) for i in range(len(blobs))]
 value=dict(status='frozen',job_id=job['id'],chat_id=job['chat_id'],answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),files=[dict(sha256=hashlib.sha256(b).hexdigest(),data=base64.b64encode(b).decode())for b in blobs],parts=parts)
 old=w.get(key)
 if old and old!=value:raise ValueError('Frozen menu result already exists')
 if not old and not w.save(key,value,insert=True):raise ValueError('Concurrent menu artifact')
 return parts
def candidate(w,job,text):
 from china_loss_execute import IO
 from china_advertising_v2 import prepare
 from china_advertising_v2_png import render
 from china_loss_control import PLAN,digest
 wanted=directions(text);day=str(datetime.now(ZoneInfo('Europe/Moscow')).date())
 io=IO()
 from china_morning_rules_review import enabled
 if not enabled(io):raise ValueError('Режим расчёта без платной модели не включён')
 bundle=prepare(io,day)
 sections=bundle['recommendation_directions'];selected=[]
 for k,s in sections.items():
  if k not in wanted:s['rows']=[];s['count']=0;s['note']='Не выбрано в этом запросе.'
  elif s.get('status')=='unavailable':raise ValueError(LABELS[k]+': проверка не завершена')
  else:selected.extend(r['action']for r in s['rows']if r.get('ready') and r.get('action'))
 signature=lambda a:tuple(a.get(k)for k in ('kind','campaign_id','nm_id','target_minor','old_minor'))
 keep={signature(a)for a in selected}
 for c in bundle['campaigns']:
  for field in ('focus','attention'):
   for r in c.get(field,[]):
    if signature(r.get('action')or{}) not in keep:r.pop('action',None)
  c.pop('owner_selected',None)
 files=[f for f in render(bundle)if f['family']=='drr']
 if not files:raise ValueError('Рекламный PNG не сформирован')
 pid='dialog-menu-'+str(job['id']);answer='Рекламный подбор · '+', '.join(LABELS[k]for k in wanted)+'. Период: '+bundle['days'][0]+' — '+bundle['days'][-1]+'. Готовых действий: '+str(len(selected))+'. Изменения только после отдельного подтверждения этого плана.'
 if selected:
  plan=dict(plan_id=pid,execution_kind='daily_ad_actions_v2',family='dialog_menu',items=selected,plan_sha256=digest(selected),created_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),report_message_ids=[],chat_id=job['chat_id'],bot_id=8780468043,source_job_id=job['id'],price_changes=False,budget_writes=False)
  old=w.get(PLAN+pid)
  if old and old['plan_sha256']!=plan['plan_sha256']:raise ValueError('Menu plan changed')
  if not old and not w.save(PLAN+pid,plan,insert=True):raise ValueError('Concurrent menu plan')
  w.save('china_agent:codex_ad_review:v1:'+str(job['id']),dict(plan_id=pid,answer=answer))
 freeze(w,job,answer,[f['bytes']for f in files])
 return answer
def history_rows(raw,nm,first,last,key,observed):
 data=raw.get('data')
 if not isinstance(data,list) or len(data)!=1 or data[0].get('product',{}).get('nmId')!=nm:raise ValueError('WB не вернул историю выбранного товара')
 history=data[0].get('history')
 if not isinstance(history,list):raise ValueError('WB не вернул дневные строки воронки')
 rows=[];seen=set()
 for item in history:
  day=item.get('date','')[:10]
  if not first<=day<=last or day in seen:raise ValueError('Даты истории WB не совпадают с запросом')
  seen.add(day)
  if any(type(item.get(k))is not int or item[k]<0 for k in ('openCount','cartCount','orderCount')):raise ValueError('Неполные счётчики WB')
  rows.append(dict(date=day,nm=str(nm),article=data[0]['product'].get('vendorCode',str(nm)),source_key=key,observed_at=observed,metrics=dict(period_from=day,period_to=day,scope='all_sources',clicks=item['openCount'],cart_count=item['cartCount'],orders=item['orderCount'])))
 return rows
def funnel(w,job,text):
 from china_wb_evidence import Reports,FUNNEL
 match=re.fullmatch(re.escape(PREFIX)+r'(\d+) (\d{4}-\d{2}-\d{2}) (\d{4}-\d{2}-\d{2})',text)
 if not match:raise ValueError('Некорректный запрос периода')
 nm=int(match[1]);first=date.fromisoformat(match[2]);last=date.fromisoformat(match[3]);today=datetime.now(ZoneInfo('Europe/Moscow')).date()
 if not 0<=(last-first).days<31 or last>=today or nm not in {int(n)for n,a in w.catalog()}:raise ValueError('Товар или завершённый период не подтверждены')
 start=str(first-timedelta(days=7));end=str(last);key='china_agent:menu_funnel:v1:'+str(nm)+':'+str(first)+':'+end
 cached=w.get(key)
 if cached and cached.get('status')=='complete' and (datetime.now(timezone.utc)-datetime.fromisoformat(cached['observed_at'])).total_seconds()<7200:rows=cached['rows']
 else:
  response=Reports(w).request(FUNNEL+'/history',dict(selectedPeriod=dict(start=start,end=end),nmIds=[nm],skipDeletedNm=False,aggregationLevel='day'))
  if not response.get('available'):raise ValueError('WB '+str(response.get('status','недоступен'))+(' · повтор после '+response['retry_at']if response.get('retry_at')else''))
  rawkey=key+':raw:'+response['observed_at'];w.save(rawkey,dict(request_nm_id=nm,period_from=start,period_to=end,response=response['data']))
  rows=history_rows(response['data'],nm,start,end,rawkey,response['observed_at'])
  w.save(key,dict(status='complete',cabinet='token_3',nm=str(nm),rows=rows,observed_at=response['observed_at'],wb_writes=0))
 byday={r['date']:r['metrics']for r in rows};fmt=lambda x:str(x).replace('.',',')
 def cr(r):return round(r['orders']*100/r['clicks'],2)if r and r['clicks']else None
 def pct(r):return fmt(cr(r))+'%'if cr(r)is not None else 'н/д'
 answer='Общая воронка · '+(rows[0]['article']if rows else str(nm))+'\n'+str(first)+' — '+end+' · полные дни МСК. Все источники, отдельно от рекламы.\n\n| Дата | Открытия | Корзины | Заказы | CR | CR днём ранее | CR неделей ранее |\n|---|---|---|---|---|---|---|\n'
 totals=dict(clicks=0,cart_count=0,orders=0);complete=True;d=first
 while d<=last:
  r=byday.get(str(d));complete=complete and r is not None
  if r:
   for k in totals:totals[k]+=r[k]
  answer+='| '+str(d)+' | '+' | '.join(str(r[k])if r else 'н/д'for k in ('clicks','cart_count','orders'))+' | '+pct(r)+' | '+pct(byday.get(str(d-timedelta(days=1))))+' | '+pct(byday.get(str(d-timedelta(days=7))))+' |\n';d+=timedelta(days=1)
 if complete:answer+='| ИТОГО | '+str(totals['clicks'])+' | '+str(totals['cart_count'])+' | '+str(totals['orders'])+' | '+pct(totals)+' | — | — |\n'
 answer+='\nCR = сумма заказов / сумма открытий. н/д — отсутствующие данные или знаменатель, не ноль. WB может запаздывать до 2 часов. Срез: '+(rows[0]['observed_at']if rows else 'пустой ответ WB')+'.'
 return answer
def prepare(w,job,inbox):
 text=inbox.get('request_text','')
 if not recognized(text):return False
 old=w.get(ROOT+'outbox:'+str(job['id']))
 if old:return True
 try:answer=funnel(w,job,text)if text.startswith(PREFIX)else candidate(w,job,text)
 except Exception as e:
  w.save('china_agent:menu_analytics:v1:'+str(job['id']),dict(status='blocked',error_type=type(e).__name__,error=str(e),wb_writes=0,model_calls=0))
  answer='Не удалось завершить '+('общую воронку'if text.startswith(PREFIX)else'подбор кандидатов')+': '+str(e)[:450]+'. Готового результата нет; изменения не выполнялись.'
 out=dict(status='ready',job_id=job['id'],chat_id=job['chat_id'],input_message_id=inbox['input_message_id'],thread_id=inbox['thread_id'],answer=answer,created_at=datetime.now(timezone.utc).isoformat(),source_channel='deterministic_menu',wb_action_permission=False,model_calls=0)
 if not w.save(ROOT+'outbox:'+str(job['id']),out,insert=True):raise ValueError('Concurrent menu outbox')
 return True