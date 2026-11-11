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
class CurrentInputsChanged(ValueError):pass

def candidate(w,job,text):
 from china_analytic_dialog import reading
 with reading():
  try:return _candidate(w,job,text)
  except CurrentInputsChanged:return _candidate(w,job,text)
def _candidate(w,job,text):
 from china_loss_execute import IO
 from china_advertising_v2 import prepare
 from china_advertising_v2_png import render
 from china_loss_control import PLAN,digest
 wanted=directions(text);day=str(datetime.now(ZoneInfo('Europe/Moscow')).date())
 class MenuIO(IO):
  # An on-demand review must not rewrite the multi-megabyte morning source.
  # Keep its working copy in memory; dated inputs and final results still persist.
  def __init__(self):super().__init__();self.menu_sources={}
  def get(self,key):
   value=self.menu_sources[key]if key in self.menu_sources else super().get(key)
   if value and key.startswith('china_agent:advertising_full_growth:')and key.endswith(':inputs'):
    fresh=w.get('china_agent:menu_current_inputs:v1:'+str(job['id']))or{}
    if fresh.get('observed_at')and (datetime.now(timezone.utc)-datetime.fromisoformat(fresh['observed_at'])).total_seconds()<900:
     value=copy.deepcopy(value);prices={r['nm_id']:r for r in fresh['prices']['rows']};stocks={r['article'].casefold():r for r in fresh['stock']['rows']}
     for row in value['prices']['rows']:
      if row['nm_id']in prices:row.update(prices[row['nm_id']])
     for nm,p in prices.items():
      e=value['economics']['rows'].get(str(nm));st=stocks.get(p['article'].casefold())
      if not e or not st:continue
      e.update(seller_price_cny=p['seller_price'],own_cogs_rub=st['price']/100,stock_free=st['stock']-st['reserve'],price_observed_at=fresh['observed_at'],stock_observed_at=fresh['observed_at'],published_stock=fresh['published_stock']['amounts'].get(str(nm)),published_stock_observed_at=fresh['observed_at'])
      e['expected_margin_before_ads_cny']=e['buyout']*(e['seller_price_cny']*(1-(e['commission_pct']+e['tax_pct']+e.get('payment_reserve_pct',0))/100)-e['own_cogs_rub']/e['fx_rub_per_cny'])-e['logistics_cny']-e.get('handling_rub',0)/e['fx_rub_per_cny']
   return value
  def put(self,key,value):
   if key.startswith('china_agent:advertising_source:'):self.menu_sources[key]=copy.deepcopy(value)
   else:return super().put(key,value)
  def create(self,key,value):
   if key.startswith('china_agent:advertising_source:'):
    if self.get(key)is not None:return False
    self.menu_sources[key]=copy.deepcopy(value);return True
   return super().create(key,value)
 io=MenuIO()
 io.on_demand_menu=True
 from china_morning_rules_review import enabled
 if not enabled(io):raise ValueError('Режим расчёта без платной модели не включён')
 bundle=prepare(io,day)
 w.save('china_agent:menu_analytics_audit:v1:'+str(job['id']),dict(day=day,rows=[dict(campaign_id=c['id'],article=r.get('article'),nm=r.get('nm'),period=r.get('period'),comparison=r.get('comparison'),economics=r.get('economics'),decision=r.get('decision'),reason=r.get('reason'),action=r.get('action'))for c in bundle.get('campaigns',[])for r in c.get('focus',[])if r.get('action')],observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0))
 sections=bundle['recommendation_directions'];selected=[]
 for k,s in sections.items():
  if k not in wanted:s['rows']=[];s['count']=0;s['note']='Не выбрано в этом запросе.'
  elif s.get('status')=='unavailable':raise ValueError(LABELS[k]+': проверка не завершена')
  else:selected.extend(r['action']for r in s['rows']if r.get('ready') and r.get('action'))
 if not selected:
  scope=bundle.get('full_cabinet_growth_review')or{}
  missing=scope.get('missing_economics')or{}
  answer='По выбранным направлениям ('+', '.join(LABELS[k].lower()for k in wanted)+') готовых предложений сейчас нет.'
  if missing:answer+=' По '+str(len(missing))+' товарам не хватает данных собственной экономики; вывод об их пригодности не сделан.'
  answer+=' Уже выполненные действия и сегодняшние повышения не повторяю. Изменений нет.'
  w.save('china_agent:menu_analytics:v1:'+str(job['id']),dict(status='reviewed',report_kind='no_ready_actions',directions=wanted,ready_actions=0,coverage=scope,wb_writes=0,model_calls=0))
  return answer
 # Cached complete-day statistics do not establish the current campaign/price/stock.
 if selected:
  from china_advertising_v2 import http
  from china_advertising_growth import validate_raise
  from china_advertising_full_growth import validate_addition
  ids=sorted({a['campaign_id']for a in selected});current={}
  for offset in range(0,len(ids),50):
   group=ids[offset:offset+50];states=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,group))).get('adverts',[])
   if {c['id']for c in states}!=set(group):raise ValueError('Текущие РК не подтверждены полностью')
   current.update({c['id']:c for c in states})
  from china_morning_readiness import current_prices,published_stock
  from china_moysklad_read import read_stock
  wanted_nm=sorted({a['nm_id']for a in selected})
  fresh_prices=current_prices(io,wanted_nm)
  fresh_stock=read_stock(list(dict.fromkeys(a['article']for a in selected)))
  fresh_published=published_stock(io,fresh_prices,wanted_nm)
  if not fresh_stock.get('coverage_complete'):raise ValueError('Current selected-SKU stock/COGS incomplete')
  w.save('china_agent:menu_current_inputs:v1:'+str(job['id']),dict(prices=fresh_prices,stock=fresh_stock,published_stock=fresh_published,observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0))
  price_map={r['nm_id']:r for r in fresh_prices['rows']}
  stock_map={r['article'].casefold():r for r in fresh_stock['rows']}
  for a in selected:
   e=next((r.get('economics')for c in bundle['campaigns']for r in c.get('focus',[])if r.get('nm')==a['nm_id']and c['id']==a['campaign_id']),None)or a.get('growth_evidence')or{}
   st=stock_map.get(a['article'].casefold());p=price_map.get(a['nm_id'])
   if not st or not p or p['article'].casefold()!=a['article'].casefold():raise ValueError('Exact selected current identity missing')
   if e.get('seller_price_cny')is not None and abs(p['seller_price']-e['seller_price_cny'])>.0001:raise CurrentInputsChanged('Selected current price changed; recalculate before proposal')
   if e.get('own_cogs_rub')is not None and abs(st['price']/100-e['own_cogs_rub'])>.01:raise CurrentInputsChanged('Selected current COGS changed; recalculate before proposal')
  io.daily_report_current_revalidation=True
  for a in selected:
   state=current[a['campaign_id']]
   if state.get('currency')!='CNY'or state.get('status')!=9:raise ValueError('Состояние выбранной РК изменилось')
   if a.get('direction')=='add':validate_addition(io,a,state)
   else:
    member=next((n for n in state['nm_settings']if n['nm_id']==a['nm_id']),None)
    if not member:raise ValueError('Состав выбранной РК изменился')
    if a['kind']=='ad_set_bid'and member['bids_kopecks'].get(a['placement'])!=a['old_minor']:raise ValueError('Ставка выбранного товара уже изменилась')
    if a.get('direction')=='raise':validate_raise(io,a,state)
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
 data=raw if isinstance(raw,list)else raw.get('data')
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
 from china_analytic_dialog import reading
 with reading():return _funnel(w,job,text)
def _funnel(w,job,text):
 from china_wb_evidence import Reports,FUNNEL
 match=re.fullmatch(re.escape(PREFIX)+r'(\d+) (\d{4}-\d{2}-\d{2}) (\d{4}-\d{2}-\d{2})',text)
 if not match:raise ValueError('Некорректный запрос периода')
 nm=int(match[1]);first=date.fromisoformat(match[2]);last=date.fromisoformat(match[3]);today=datetime.now(ZoneInfo('Europe/Moscow')).date()
 if not 0<=(last-first).days<31 or last>=today or nm not in {int(n)for n,a in w.catalog()}:raise ValueError('Товар или завершённый период не подтверждены')
 # Official history API covers only the most recent week. Older dates stay n/d.
 start=str(max(first,today-timedelta(days=7)));end=str(last);key='china_agent:menu_funnel:v1:'+str(nm)+':'+str(first)+':'+end
 history=w.db('GET','telegram_api_cache',params={'cache_key':'like.china_agent:menu_funnel_day:v1:'+str(nm)+':*','select':'payload','limit':100,'order':'cache_key.desc'})or[]
 previous=[r['payload']for r in history if str(first-timedelta(days=7))<=r['payload'].get('date','')<=end]
 if last<today-timedelta(days=7):
  if not previous:raise ValueError('Дневная история WB доступна только за последнюю неделю; за выбранный период сохранённых данных нет')
  rows=previous;cached=dict(status='complete',observed_at=datetime.now(timezone.utc).isoformat(),rows=rows)
 else:cached=w.get(key)
 if cached and cached.get('status')=='complete' and (datetime.now(timezone.utc)-datetime.fromisoformat(cached['observed_at'])).total_seconds()<7200:rows=cached['rows']
 else:
  response=Reports(w).request(FUNNEL+'/history',dict(selectedPeriod=dict(start=start,end=end),nmIds=[nm],skipDeletedNm=False,aggregationLevel='day'))
  if not response.get('available'):raise ValueError('WB '+str(response.get('status','недоступен'))+(' · повтор после '+response['retry_at']if response.get('retry_at')else''))
  rawkey=key+':raw:'+response['observed_at'];w.save(rawkey,dict(request_nm_id=nm,period_from=start,period_to=end,response=response['data']))
  rows=history_rows(response['data'],nm,start,end,rawkey,response['observed_at'])
  for r in rows:w.save('china_agent:menu_funnel_day:v1:'+str(nm)+':'+r['date'],r)
  rows=list({r['date']:r for r in previous+rows}.values())
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
  import traceback
  w.save('china_agent:menu_analytics:v1:'+str(job['id']),dict(status='blocked',error_type=type(e).__name__,error=str(e),trace=traceback.format_exc()[-5000:],wb_writes=0,model_calls=0))
  answer='Не удалось получить все данные для '+('общей воронки'if text.startswith(PREFIX)else'подбора кандидатов')+'. Готового результата нет; изменения не выполнялись. Запрос №'+str(job['id'])+'.'
 out=dict(status='ready',job_id=job['id'],chat_id=job['chat_id'],input_message_id=inbox['input_message_id'],thread_id=inbox['thread_id'],answer=answer,created_at=datetime.now(timezone.utc).isoformat(),source_channel='deterministic_menu',wb_action_permission=False,model_calls=0)
 if not w.save(ROOT+'outbox:'+str(job['id']),out,insert=True):raise ValueError('Concurrent menu outbox')
 return True
def native_funnel_request(text,scope):
 if not isinstance(scope,dict)or set(scope)!={'nm_id','date_from','date_to'}:raise ValueError('Exact native funnel scope required')
 nm=scope['nm_id'];first=scope['date_from'];last=scope['date_to']
 if type(nm)is not int or not isinstance(first,str)or not isinstance(last,str)or not re.search(r'(?<!\d)'+str(nm)+r'(?!\d)',text)or first not in text or last not in text or not re.search(r'funnel|воронк',text,re.I):raise ValueError('Native funnel scope does not match original human request')
 return PREFIX+str(nm)+' '+first+' '+last
def recover(job_id,native_funnel_scope=None):
 from conversion_watches import runtime,saved_network_guard
 from china_codex_ad_review import bind
 w=runtime();rows=w.db('GET','business_agent_jobs',params={'id':'eq.'+str(job_id),'agent_id':'eq.china','chat_id':'eq.-1004342917488','select':'id,status,sender_id,chat_id,request_text,tool_trace'})
 if len(rows)!=1 or rows[0]['sender_id']not in (5122667182,307200273):raise ValueError('Exact original menu request unavailable')
 job=rows[0];inbox=w.get(ROOT+'inbox:'+str(job_id))or{}
 if inbox.get('job_id')!=job_id:raise ValueError('Original message scope missing')
 text=inbox.get('request_text','')
 if native_funnel_scope is not None:text=native_funnel_request(text,native_funnel_scope)
 elif not recognized(text):raise ValueError('Original menu scope missing')
 key='china_agent:menu_result:v1:'+str(job_id);old=w.get(key)or{}
 if old.get('status')=='sent'and(native_funnel_scope is None or old.get('png_verified')):return dict(status='already_sent',job_id=job_id,message_ids=old['message_ids'])
 if native_funnel_scope is not None and old.get('status')=='sent':w.save(key+':before-native-png',old,insert=True)
 artifact_job=dict(job,id='native-funnel-'+str(job_id))if native_funnel_scope is not None else job
 w.active_question_id=artifact_job['id'];w.reply_id=inbox['input_message_id']
 with saved_network_guard():
  answer=old.get('answer')or(candidate(w,job,text)if text.startswith(CANDIDATES)else funnel(w,job,text))
  w.save(key,dict(status='prepared',job_id=job_id,answer=answer,wb_writes=0,model_calls=0))
  from china_table_png import delivery_parts
  from conversion_watches import split_message
  parts=delivery_parts(w,artifact_job,answer,split_message)
  if native_funnel_scope is not None and old.get('status')=='sent':parts=[part for part in parts if part.startswith('CHINA_TABLE_PNG:')]
  if native_funnel_scope is not None and not any(part.startswith('CHINA_TABLE_PNG:')for part in parts):raise ValueError('Native funnel final PNG missing')
  ids=list(old.get('message_ids',[]))if native_funnel_scope is not None and old.get('status')=='sent'else[]
  for i,part in enumerate(parts):
   receipt_key='menu_result:'+str(job_id)+(':native_funnel:'if native_funnel_scope is not None else':')+str(i)
   status=w.send_once(receipt_key,job['chat_id'],part);receipt=w.get('china_agent:conversion_watch_delivery:v1:'+receipt_key)or{}
   if status!='sent'or receipt.get('status')!='sent'or not receipt.get('message_id'):raise ValueError('Menu result delivery not verified')
   ids.append(receipt['message_id'])
  bind(w,job_id,ids,answer)
  w.save(key,dict(status='sent',job_id=job_id,answer=answer,message_ids=ids,png_verified=native_funnel_scope is not None,wb_writes=0,model_calls=0))
 return dict(status='sent',job_id=job_id,message_ids=ids)
def verify_funnel(nm):
 from conversion_watches import runtime,saved_network_guard
 from china_table_png import blocks,render
 w=runtime();today=datetime.now(ZoneInfo('Europe/Moscow')).date()
 with saved_network_guard():answer=funnel(w,{},PREFIX+str(nm)+' '+str(today-timedelta(days=7))+' '+str(today-timedelta(days=1)))
 files=[blob for kind,data in blocks(answer)if kind=='table'for blob in render(*data)]
 if not files:raise ValueError('Funnel PNG missing')
 w.save('china_agent:menu_funnel_qa:v1:'+str(nm),dict(status='complete',answer=answer,files=[base64.b64encode(b).decode()for b in files],wb_writes=0,model_calls=0))
 return dict(status='complete',nm_id=nm,png_parts=len(files))
def correct_empty_result(job_id):
 from conversion_watches import runtime,saved_network_guard
 w=runtime();key='china_agent:menu_result:v1:'+str(job_id);prior=w.get(key)or{}
 if prior.get('status')!='sent'or 'Готовых действий: 0.'not in prior.get('answer',''):raise ValueError('No verified empty result to clarify')
 inputs=w.get('china_agent:advertising_full_growth:'+str(datetime.now(ZoneInfo('Europe/Moscow')).date())+':v1:inputs')or{}
 if inputs.get('status')!='complete':raise ValueError('Completed review inputs missing')
 missing=inputs.get('economics',{}).get('missing')or{}
 answer='Уточнение к подбору: готовых добавлений и повышений сейчас не выделено. По '+str(len(missing))+' товарам не хватает собственной экономики; это не означает, что они не подходят. Предыдущий PNG — статистика РК, а не новый план действий. Изменений нет.'
 receipt_key='menu_result:'+str(job_id)+':empty_clarification';w.reply_id=(w.get(ROOT+'inbox:'+str(job_id))or{})['input_message_id']
 with saved_network_guard():
  if w.send_once(receipt_key,-1004342917488,answer)!='sent':raise ValueError('Clarification delivery not verified')
 receipt=w.get('china_agent:conversion_watch_delivery:v1:'+receipt_key)or{}
 if receipt.get('status')!='sent'or not receipt.get('message_id'):raise ValueError('Clarification receipt missing')
 w.save(key+':initial',prior,insert=True)
 w.save(key,dict(status='sent',job_id=job_id,answer=answer,message_ids=[receipt['message_id']],supersedes_message_ids=prior['message_ids'],wb_writes=0,model_calls=0))
 return dict(status='sent',job_id=job_id,message_ids=[receipt['message_id']])
if __name__=='__main__':
 import argparse,json
 p=argparse.ArgumentParser();p.add_argument('--recover-job',type=int,required=True);args=p.parse_args()
 from pathlib import Path
 request=json.loads(Path('china-conversion-watches-request.json').read_text())
 if request.get('correct_empty_result'):print(json.dumps(correct_empty_result(args.recover_job)))
 else:
  if request.get('verify_funnel_nm_id'):print(json.dumps(verify_funnel(int(request['verify_funnel_nm_id']))))
  print(json.dumps(recover(args.recover_job,request.get('native_funnel_scope'))))