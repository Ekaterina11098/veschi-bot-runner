"""Evidence-linked experience: execution is not a business outcome or causal proof."""
import hashlib,json,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
ROOT='china_agent:experience:v1:'
INDEX='china_agent:experience_index:v1'
MSK=ZoneInfo('Europe/Moscow')
CONDITIONS=('seller_price','customer_price','spp','bid','stock_available','rating','reviews_count','season','delivery','promotion','traffic_mix','campaign_settings')

def compare_conditions(previous,current):
 """Missing facts are unknown; no elapsed time or correlation proves an algorithm change."""
 changes=[];unknown=[]
 for field in CONDITIONS:
  old,new=previous.get(field),current.get(field)
  if old is None or new is None:unknown.append(field)
  elif old!=new:changes.append(dict(field=field,before=old,after=new))
 return dict(changes=changes,unknown=unknown,transferability='limited' if changes or unknown else 'comparable_conditions_not_guaranteed',algorithm_change='not_established',repeat_requires_fresh_data=True,repeat_requires_confirmation=True)

def assess_candidate(experiences,nm,current):
 relevant=[e for e in experiences if nm in e.get('action',{}).get('nm_ids',[])]
 risks=[];needs_review=False
 for event in relevant:
  comparison=compare_conditions(event.get('context') or {},current)
  if event.get('business_outcome')=='negative' or event.get('advertising_outcome')=='negative' or event.get('expected_outcome')=='negative':
   risks.append(dict(event_id=event['event_id'],previous_result='negative',condition_comparison=comparison))
   if not comparison['changes']:needs_review=True
 return dict(event_ids=[e['event_id'] for e in relevant],needs_review=needs_review,risks=risks,requires_confirmation=True,note='Негативный опыт требует проверки причины/изменений; это не вечный запрет. Положительный опыт не гарантия.')
def stamp():return datetime.now(timezone.utc).isoformat()
def save(w,key,value):
 if hasattr(w,'save'):return w.save(key,value)
 return w.put(key,value) if w.get(key) else w.create(key,value)
def read_rows(w,prefix,limit=80):
 from urllib.parse import quote
 result=[]
 while len(result)<limit:
  size=min(200,limit-len(result));offset=len(result)
  if hasattr(w,'save'):part=w.db('GET','telegram_api_cache',params={'cache_key':'like.'+prefix+'*','select':'cache_key,payload,updated_at','order':'updated_at.desc,cache_key.asc','limit':size,'offset':offset}) or []
  else:part=w.db('telegram_api_cache?cache_key=like.'+quote(prefix+'*',safe='')+'&select=cache_key,payload,updated_at&order=updated_at.desc,cache_key.asc&limit='+str(size)+'&offset='+str(offset))
  result+=part
  if len(part)<size:break
 if len(result)>=5000:raise ValueError('History exceeds bounded scan; extend pagination before claiming all changes')
 return result
def identifier(source,item):return hashlib.sha256((source+'#'+str(item)).encode()).hexdigest()[:24]
def put_event(w,event):
 assert event.get('source_key') and event.get('record_type') in ['verified_action','reported_observation','operational_lesson']
 key=ROOT+event['event_id'];batch=getattr(w,'_experience_prefetched',None)
 prior=batch.get(key) if batch is not None else w.get(key)
 if prior:
  # Re-import may enrich receipt freshness, but cannot overwrite results or remove history.
  return prior
 event=dict(event,created_at=stamp(),business_outcome=event.get('business_outcome','pending'),causality='not_established',observations=event.get('observations',[]))
 save(w,key,event)
 if batch is not None:batch[key]=event
 index=w.get(INDEX) or dict(event_ids=[])
 if event['event_id'] not in index['event_ids']:index['event_ids'].append(event['event_id']);save(w,INDEX,index)
 return event
def windows(started_at,days=3):
 changed=datetime.fromisoformat(started_at.replace('Z','+00:00')).astimezone(MSK).date()
 return dict(days=days,before_from=str(changed-timedelta(days=days)),before_to=str(changed-timedelta(days=1)),after_from=str(changed+timedelta(days=1)),after_to=str(changed+timedelta(days=days)),evaluate_from=str(changed+timedelta(days=days+1)),excluded_change_day=str(changed))
def sync(w):
 marker_key='china_agent:experience_sync:v1';last=w.get(marker_key)
 if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last['at'])).total_seconds()<300:return 0
 # One snapshot replaces a network read for each already imported event.
 prefetched=read_rows(w,ROOT,limit=5000)
 w._experience_prefetched={r['cache_key']:r['payload'] for r in prefetched}
 count=0
 prefixes=['china_agent:advertising_dialog_execution:v1:','china_agent:new_ad_execution:v1:','china_agent:ad_rule_execution:','china_agent:loss_ad_execution:','china_agent:price_execution:v1:','china_agent:codex_bid_raise:','china_agent:codex_bid_revert:']
 for prefix in prefixes:
  for row in read_rows(w,prefix,limit=5000):
   key=row['cache_key'];p=row['payload'];actions=[]
   if p.get('status')=='verified' and p.get('plan',{}).get('kind')=='ad_set_bid':
    a=p['plan'];actions.append(dict(item=a['nm_id'],nm_ids=[a['nm_id']],campaign_id=a['campaign_id'],article=a['article'],kind='bid_change',before=a['old_minor'],after=a['target_minor'],started=p.get('submitted_at'),verified=p.get('verified_at')))
   for item in p.get('items',[]):
    if item.get('status') not in ['applied','verified'] or item.get('already_done'):continue
    bid=item.get('item') or {}
    if bid.get('kind')=='ad_raise_bid':
     before=item.get('before') or {};after=item.get('after') or {};nm=bid['nm_id'];cid=bid['campaign_id'];zone=bid['placement']
     old=next((n.get('bids_kopecks',{}).get(zone) for n in before.get('nm_settings',[]) if n['nm_id']==nm),None)
     new=next((n.get('bids_kopecks',{}).get(zone) for n in after.get('nm_settings',[]) if n['nm_id']==nm),None)
     if old!=new and old==bid['old_minor'] and new==bid['target_minor']:actions.append(dict(item=str(cid)+':'+str(nm),nm_ids=[nm],campaign_id=cid,article=bid['article'],kind='bid_change',before=old,after=new,started=p.get('created_at'),verified=p.get('completed_at')))
     continue
    selection=item.get('selection') or {};nm=selection.get('nm_id')
    if nm:
     actions.append(dict(item=nm,nm_ids=[int(nm)],article=selection.get('article'),kind='price_change',before=selection.get('current_cny'),after=selection.get('target_cny'),started=p.get('wb_state',{}).get('activationDate') or p.get('completed_at'),verified=p.get('completed_at')))
    elif re.fullmatch(r'\d+:\d+',str(item.get('id',''))):
     cid,nm=map(int,item['id'].split(':'));before=item.get('before') or {};after=item.get('after') or {};old=next((n.get('bids_kopecks',{}).get('recommendations') for n in before.get('nm_settings',[]) if n['nm_id']==nm),None);new=next((n.get('bids_kopecks',{}).get('recommendations') for n in after.get('nm_settings',[]) if n['nm_id']==nm),None)
     actions.append(dict(item=item['id'],nm_ids=[nm],campaign_id=cid,article=item.get('article'),kind='sku_exclusion' if new is None else 'bid_change',before=old,after=new,started=item.get('submitted_at'),verified=item.get('verified_at') or row.get('updated_at')))
   if p.get('status')=='done':
    for item in p.get('campaigns',[]):
     if item.get('status')!='launched':continue
     c=item.get('after') or {};ids=[n['nm_id'] for n in c.get('nm_settings',[])]
     if not ids:
      body=item.get('steps',{}).get('create',{}).get('body') or {};ids=body.get('nms',[])
     actions.append(dict(item=item.get('campaign_id'),nm_ids=ids,campaign_id=item.get('campaign_id'),kind='new_campaign',started=item.get('steps',{}).get('start',{}).get('at') or p.get('completed_at'),verified=item.get('verified_at')))
   if p.get('status')=='verified' and isinstance(p.get('before'),dict) and isinstance(p.get('after'),dict):
    for cid,c in p['before'].items():
     after=p['after'].get(str(cid)) or p['after'].get(cid)
     if not isinstance(c,dict) or not isinstance(after,dict) or not str(cid).isdigit():continue
     removed={n['nm_id'] for n in c.get('nm_settings',[])}-{n['nm_id'] for n in after.get('nm_settings',[])}
     for nm in removed:actions.append(dict(item=str(cid)+':'+str(nm),nm_ids=[nm],campaign_id=int(cid),kind='sku_exclusion',started=p.get('submitted_at'),verified=p.get('verified_at')))
   for a in actions:
    started=a.pop('started',None);verified=a.pop('verified',None)
    if not started:continue # Updated cache time is not the actual execution time.
    event=dict(event_id=identifier(key,a['item']),record_type='verified_action',source_key=key,action=a,started_at=started,verified_at=verified,operational_outcome='verified',business_outcome='pending',context={},limitations=['Нет автоматического доказательства причинности; проверить параллельные изменения цены, ставок, наличия, спроса и WB.'])
    event['comparison']=windows(started,4 if 'loss-20261022-107' in key else 3)
    put_event(w,event);count+=1
 save(w,marker_key,dict(at=stamp(),imported=count));return count
def age_context(event,now=None):
 at=event.get('last_observed_at') or event.get('started_at') or event.get('created_at');now=now or datetime.now(timezone.utc)
 age=max(0,(now-datetime.fromisoformat(at.replace('Z','+00:00'))).total_seconds()/86400) if at else None
 return dict(age_days=round(age,1) if age is not None else None,transferability='recheck_current_conditions',weight='historical_only' if age is not None and age>30 else 'recent_context',note='Возраст снижает переносимость, но сам не доказывает изменение алгоритмов WB. Успех/неудача похожего теста не предопределяет новый результат.')
def search(w,nm_ids=(),query='',limit=12):
 sync(w);ids=(w.get(INDEX) or {}).get('event_ids',[]);output=[]
 records={r['payload']['event_id']:r['payload'] for r in read_rows(w,ROOT,limit=5000) if r.get('payload',{}).get('event_id')}
 evaluate_saved(w,ids,records)
 for eid in reversed(ids):
  e=records.get(eid)
  if not e:continue
  selected=set(e.get('action',{}).get('nm_ids',[]))
  if nm_ids and not selected.intersection(nm_ids):continue
  if query and not nm_ids and not any(x.casefold() in json.dumps(e,ensure_ascii=False).casefold() for x in query.split()):continue
  output.append(dict(e,age=age_context(e)))
  if len(output)>=limit:break
 return dict(experiences=output,total_matching_returned=len(output),principle='Проверенные действия, наблюдаемые результаты и гипотезы раздельно. Опыт не даёт разрешения повторять или отменять действие.')

def evaluate_saved(w,ids,records=None):
 """Evaluate only due, equally complete saved advertising periods. No fresh WB calls."""
 today=getattr(w,'now',datetime.now(timezone.utc)).astimezone(MSK).date()
 cached_sources={}
 for eid in ids:
  e=records.get(eid) if records is not None else w.get(ROOT+eid);window=(e or {}).get('comparison') or {};action=(e or {}).get('action') or {}
  if not window or str(today)<window['evaluate_from'] or not action.get('campaign_id') or e.get('latest_change_observation'):continue
  if any(o.get('automatic_saved_ad_evaluation') for o in e.get('observations',[])):continue
  periods=[];source_keys=[]
  for label in ['before','after']:
   first=datetime.fromisoformat(window[label+'_from']).date();days=window['days'];daily=[]
   for i in range(days):
    day=first+timedelta(days=i);key='china_agent:advertising_source:'+str(day+timedelta(days=1))+':v1'
    if key not in cached_sources:cached_sources[key]=w.get(key)
    p=cached_sources[key]
    if not p:continue
    observations=p.get('observations',[]);mapping={}
    for o in observations:
     if o.get('tool')=='wbbidder_campaign':
      c=(o.get('data') or {}).get('campaign') or {};mapping[(o.get('arguments') or {}).get('campaign_id')]=c.get('wb_id')
    rows=[]
    for o in observations:
     args=o.get('arguments') or {}
     if o.get('tool')!='wbbidder_campaign_stats' or o.get('status')!='received' or o.get('scope_verified') is not True or args.get('report')!='products' or args.get('d1')!=str(day) or args.get('d2')!=str(day) or mapping.get(args.get('campaign_id'))!=action['campaign_id']:continue
     rows += [r for r in (o.get('data') or {}).get('data',[]) if int(r.get('nm_id',0)) in action.get('nm_ids',[])]
    if {int(r['nm_id']) for r in rows}!=set(action.get('nm_ids',[])):continue # Missing attribution rows are not proven zero expense.
    if any(r.get('ac_spending_sum') is None or r.get('ac_orders_sum') is None or r.get('ac_orders') is None for r in rows):continue
    daily.append(dict(spend=sum(r['ac_spending_sum'] for r in rows),amount=sum(r['ac_orders_sum'] for r in rows),orders=sum(r['ac_orders'] for r in rows)));source_keys.append(key)
   spend=sum(r['spend'] for r in daily);amount=sum(r['amount'] for r in daily)
   periods.append(dict(days=days,period_complete=len(daily)==days,period_from=window[label+'_from'],period_to=window[label+'_to'],currency='CNY',profit_method='unconfirmed_total_profit',total_profit=None,ad_spend=spend,ad_order_amount=amount,ad_orders=sum(r['orders'] for r in daily),ad_drr=spend/amount*100 if amount else None))
  if not all(p['period_complete'] for p in periods):continue
  updated=observe(w,eid,*periods,source_keys=sorted(set(source_keys)))
  b,a=periods[0]['ad_drr'],periods[1]['ad_drr'];trend='inconclusive' if b is None or a is None else 'negative' if a>b else 'positive' if a<b else 'unchanged'
  updated['observations'][-1].update(automatic_saved_ad_evaluation=True,advertising_direction=trend,causality='not_established',note='Только наблюдаемая эффективность рекламы; общая прибыль не подтверждена, причина не доказана')
  updated['advertising_outcome']='negative' if a is not None and a>5 else 'positive' if trend=='positive' else 'within_target' if a is not None else 'inconclusive';save(w,ROOT+eid,updated)
  if records is not None:records[eid]=updated

def decision_context(w,nm_ids=(),current=None):
 """Mandatory input to recommendations; no model-authored outcomes or permissions."""
 result=search(w,nm_ids,limit=200);now=getattr(w,'now',datetime.now(timezone.utc));today=now.astimezone(MSK).date();recent=set()
 for event in result['experiences']:
  action=event.get('action') or {};at=event.get('started_at')
  if event.get('record_type')=='verified_action' and at:
   changed=datetime.fromisoformat(at.replace('Z','+00:00')).astimezone(MSK).date()
   evaluate_from=event.get('comparison',{}).get('evaluate_from')
   if (evaluate_from and str(today)<evaluate_from) or not evaluate_from and 0<=(today-changed).days<=3:recent.update(action.get('nm_ids',[]))
  event['current_condition_comparison']=compare_conditions(event.get('context') or {},current or {})
 return dict(result,recent_changed_nm_ids=sorted(recent),rules=['Не повторять недавнее изменение до сопоставимых полных дней','Положительный и отрицательный опыт сохраняются вместе; новый результат может отличаться','Изменения алгоритмов WB — гипотеза, пока нет подтверждения','Рекомендация не разрешает WB-записи; нужен подтверждённый точный план'])
def summarize_comparison(before,after):
 if before.get('days')!=after.get('days') or before.get('period_complete') is not True or after.get('period_complete') is not True:return dict(outcome='inconclusive',reason='Нужны равные полные периоды')
 if before.get('profit_method')!=after.get('profit_method') or before.get('currency')!=after.get('currency'):return dict(outcome='inconclusive',reason='Метод прибыли/валюта не сопоставимы')
 b,a=before.get('total_profit'),after.get('total_profit')
 if b is None or a is None:return dict(outcome='inconclusive',reason='Общая прибыль не подтверждена; отсутствие суммы не0')
 delta=a-b
 if after.get('orders')==0 and abs(a)<1 and delta>0:return dict(outcome='mixed',delta_profit=delta,reason='Сокращение минуса без заказов не рост заработка')
 return dict(outcome='positive' if delta>0 else 'negative' if delta<0 else 'unchanged',delta_profit=delta,causality='not_established',method=after['profit_method'])
def observe(w,eid,before,after,source_keys,context=None):
 # Called only by deterministic scheduled evaluation, never by the language model.
 e=w.get(ROOT+eid)
 if not e or not source_keys:raise ValueError('Нужны событие и проверяемые источники')
 comparison=e.get('comparison') or {}
 for obj,label in [(before,'before'),(after,'after')]:
  if obj.get('period_from')!=comparison.get(label+'_from') or obj.get('period_to')!=comparison.get(label+'_to'):raise ValueError('Окно результата не совпадает с фактическим изменением')
 result=summarize_comparison(before,after);conditions=compare_conditions(before.get('conditions') or {},after.get('conditions') or {});record=dict(observed_at=stamp(),before=before,after=after,result=result,source_keys=source_keys,context=context or {},condition_comparison=conditions)
 e.setdefault('observations',[]).append(record);e.update(business_outcome=result['outcome'],last_observed_at=record['observed_at'],context=context or e.get('context',{}));save(w,ROOT+eid,e)
 return e


