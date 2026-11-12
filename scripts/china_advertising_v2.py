"""Owner-approved daily format: live China readbacks, ratio-of-sums and exact new actions."""
import copy,json,math,statistics,time
from decimal import Decimal,InvalidOperation
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
MSK=ZoneInfo('Europe/Moscow');VERSION='grouped_campaigns_v2';FORMAT='china_agent:advertising_format:v2'
def stamp():return datetime.now(timezone.utc).isoformat()
def save(io,k,v):
 if io.get(k) is None:
  if not io.create(k,v):raise RuntimeError('Concurrent daily state')
 else:io.put(k,v)
def http(io,path,method='GET',body=None):
 import requests
 allowed=(method=='GET' and path.split('?')[0] in ['/adv/v1/promotion/count','/api/advert/v2/adverts','/adv/v3/fullstats','/api/advert/v1/config']) or (method=='POST' and path in ['/api/advert/v2/budget','/api/advert/v1/bids/min'])
 if not allowed:raise ValueError('Daily generator is read-only')
 time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=60)
 if not r.ok:raise RuntimeError('China advertising read HTTP '+str(r.status_code))
 return r.json() if r.content else {}
def compact_execution_records(records):
 """Keep exactly the receipt fields consumed by history() and verified funding summaries."""
 fields=('status','kind','amount_cny','before','after','verified_at','completed_at','items','groups','campaigns','readback','selection','request','cid','nm','old','target','steps')
 def shrink(value):
  if isinstance(value,list):return [shrink(x) for x in value]
  if not isinstance(value,dict):return value
  if isinstance(value.get('id'),int) and isinstance(value.get('nm_settings'),list):
   return dict(id=value['id'],status=value.get('status'),currency=value.get('currency'),settings=dict(placements=(value.get('settings')or{}).get('placements',{})),nm_settings=[dict(nm_id=n['nm_id'],bids_kopecks=n.get('bids_kopecks',{}))for n in value['nm_settings']])
  if any(k in value for k in ('status','before','after')):return {k:shrink(v)for k,v in value.items()if k in fields or k in ('path','body','submitted_at')}
  return {k:shrink(v)for k,v in value.items()}
 out=[]
 for record in records:
  payload=record.get('payload',record)
  # Unanchored legacy maps are traversed generically; retain them without assumptions.
  if not isinstance(payload,dict) or not any(k in payload for k in ('status','before','after')):
   out.append(copy.deepcopy(record));continue
  compact={k:shrink(payload[k]) for k in fields if k in payload}
  if 'payload' in record:
   value=copy.deepcopy({k:v for k,v in record.items() if k!='payload'});value['payload']=compact
  else:value=compact
  out.append(value)
 return out

def read_price_experience(io,page_size=300,max_pages=100):
 """Load complete ordered price history; a page limit is not a total-history limit."""
 query='telegram_api_cache?cache_key=like.china_agent:experience:v1:*&payload->action->>kind=eq.price_change&select=action:payload->action,started_at:payload->>started_at&order=cache_key.asc&limit='+str(page_size)
 records=[]
 for page_index in range(max_pages):
  page=io.db(query+'&offset='+str(page_index*page_size))
  if not isinstance(page,list):raise ValueError('Price experience page malformed')
  records.extend(page)
  if len(page)<page_size:return records
 raise ValueError('Price experience history exceeds safe pagination bound')

def read_economics(io):
 model=io.get('china_agent:loss_economics:latest:v1') or {};result=dict(status='unavailable',rows={})
 try:
  observed=event_time(model['observed_at'])
  if not 0<=(datetime.now(timezone.utc)-observed).total_seconds()<=48*3600:return result
  from china_loss_policy import evaluate
  assessed={}
  for row in model.get('records',[]):
   try:
    value=evaluate(row)
    assessed[str(row['nm_id'])]=dict(value,period_from=row.get('period_from'),period_to=row.get('period_to'),source_ids=row.get('source_ids'),own_cogs_rub=row.get('own_cogs_rub'),seller_revenue_rub=row.get('seller_revenue_rub'),fx_rub_cny=row.get('fx_rub_cny'),basis='preliminary_model')
   except (ValueError,KeyError,TypeError):continue
  return dict(status='available',observed_at=model['observed_at'],rows=assessed)
 except (KeyError,ValueError,TypeError,ImportError):return result

def refresh_budget_context(io,source,day):
 """Cached morning receipts cannot establish the current post-change test window."""
 s=copy.deepcopy(source);since=(date.fromisoformat(day)-timedelta(days=14)).isoformat()
 query='telegram_api_cache?or=(cache_key.like.china_agent:ad_rule_execution:*,cache_key.like.china_agent:loss_ad_execution:*,cache_key.like.china_agent:codex_*:execution,cache_key.like.china_agent:owner_*:execution,cache_key.like.china_agent:price_execution:v1:*,cache_key.like.china_agent:new_ad_execution:*,cache_key.like.china_agent:hourly_cloud:execution:*,cache_key.like.china_agent:daily_ad_execution:v2:*,cache_key.like.china_agent:advertising_dialog_execution:v1:*,cache_key.like.china_agent:bid_resume:*)&updated_at=gte.'+since+'&select=cache_key,payload&order=cache_key.asc&limit=100'
 query=query.replace('or=(', 'or=(cache_key.like.china_agent:*:execution,',1)
 records=[]
 for offset in range(0,2000,100):
  page=io.db(query+'&offset='+str(offset))
  if not isinstance(page,list):raise ValueError('Current execution context unavailable')
  records+=page
  if len(page)<100:break
 else:raise ValueError('Current execution history incomplete')
 # Canonical receipts can have recovery prefixes outside the historical scan.
 # Never infer the latest change day from a prefix-filtered subset alone.
 registry=io.get('china_agent:verified_campaign_state:v1') or {}
 known={r.get('cache_key') for r in records}
 for cid,key in registry.items():
  if key in known:continue
  receipt=io.get(key)
  if receipt and receipt.get('status')=='verified' and str(receipt.get('after',{}).get('id'))==str(cid):
   records.append(dict(cache_key=key,payload=receipt));known.add(key)
 s['executions']=compact_execution_records(records)
 s['experience']=read_price_experience(io)
 s['economics']=read_economics(io)
 return s

def collect(io,day,current=False):
 policy=io.get(FORMAT)
 if not policy or policy.get('status')!='approved' or policy.get('version')!=VERSION:raise ValueError('Approved daily advertising format missing')
 key=('china_agent:advertising_midday_source:' if current else 'china_agent:advertising_source:')+day+':v2';s=io.get(key)
 if current and s:
  try:
   age=(datetime.now(timezone.utc)-event_time(s.get('observed_at'))).total_seconds()
   fresh=0<=age<=120 and s.get('period_from')==day and s.get('period_to')==day
  except (ValueError,TypeError,AttributeError):fresh=False
  if not fresh:
   # Preserve the source that produced an earlier report; never relabel it as current.
   save(io,key+':rejected_stale:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'),s)
   s=None
 if s and s.get('status')=='complete':
  if not current:
   # A complete transport response can omit active campaigns. Refresh only those
   # identities on the next preparation; never replace their missing data by zero.
   returned={r['advertId'] for b in s['batches'].values() for r in b.get('stats',[])}
   missing=[c['id'] for b in s['batches'].values() for c in b['campaigns'].get('adverts',[]) if c['status']==9 and c['id'] not in returned]
   for offset in range(0,len(missing),50):
    ids=missing[offset:offset+50]
    rows=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate='+s['period_from']+'&endDate='+s['period_to'])
    if any(r.get('advertId') not in ids for r in rows):raise ValueError('Scoped missing campaign identity mismatch')
    for b in s['batches'].values():
     wanted={c['id']for c in b['campaigns'].get('adverts',[])}
     b['stats'] += [r for r in rows if r['advertId']in wanted]
   save(io,key,s)
   from china_morning_readiness import ensure
   ensure(io,s,day,key)
  return s
 end=date.fromisoformat(day) if current else date.fromisoformat(day)-timedelta(days=1);start=end if current else end-timedelta(days=6)
 if not s:s=dict(status='collecting',version=VERSION,cabinet='token_3',observed_at=stamp(),period_from=str(start),period_to=str(end),wb_writes=0);save(io,key,s)
 if 'ids' not in s:
  j=http(io,'/adv/v1/promotion/count');s['ids']=sorted({x['advertId'] for g in j.get('adverts',[]) if g.get('status') in [4,9,11] for x in g.get('advert_list',[])});save(io,key,s)
 if not s['ids'] or len(s['ids'])>1000:raise ValueError('Campaign catalogue incomplete')
 s.setdefault('batches',{})
 for pos in range(0,len(s['ids']),50):
  ids=s['ids'][pos:pos+50];b=s['batches'].setdefault(str(pos),{})
  for name,path,method,body in [('campaigns','/api/advert/v2/adverts?ids='+','.join(map(str,ids)),'GET',None),('budgets','/api/advert/v2/budget','POST',dict(advertIds=ids)),('stats','/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate='+str(start)+'&endDate='+str(end),'GET',None)]:
   if name not in b:b[name]=http(io,path,method,body);save(io,key,s)
 if 'config' not in s:s['config']=http(io,'/api/advert/v1/config');save(io,key,s)
 if s['config'].get('currency')!='CNY':raise ValueError('Wrong advertising currency')
 cat=io.get('china_agent:prices:v1') or {}
 if cat.get('cabinet')!='token_3':raise ValueError('China article catalogue unavailable')
 s['catalogue']=cat
 if 'executions' not in s:
  since=(date.fromisoformat(day)-timedelta(days=14)).isoformat()
  query='telegram_api_cache?or=(cache_key.like.china_agent:ad_rule_execution:*,cache_key.like.china_agent:loss_ad_execution:*,cache_key.like.china_agent:codex_*:execution,cache_key.like.china_agent:owner_*:execution,cache_key.like.china_agent:price_execution:v1:*,cache_key.like.china_agent:new_ad_execution:*,cache_key.like.china_agent:hourly_cloud:execution:*,cache_key.like.china_agent:daily_ad_execution:v2:*,cache_key.like.china_agent:advertising_dialog_execution:v1:*,cache_key.like.china_agent:bid_resume:*)&updated_at=gte.'+since+'&select=cache_key,payload&order=cache_key.asc&limit=100'
  query=query.replace('or=(', 'or=(cache_key.like.china_agent:*:execution,',1)
  s['executions']=[]
  for offset in range(0,2000,100):
   page=io.db(query+'&offset='+str(offset));s['executions']+=page
   if len(page)<100:break
  else:raise ValueError('Execution history exceeds safe pagination bound')
  s['executions']=compact_execution_records(s['executions']);save(io,key,s)
 else:
  compacted=compact_execution_records(s['executions'])
  if compacted!=s['executions']:s['executions']=compacted;save(io,key,s)
 if 'experience' not in s:
  s['experience']=read_price_experience(io)
  save(io,key,s)
 if 'economics' not in s:s['economics']=read_economics(io)
 if not current:
  from china_morning_readiness import ensure
  ensure(io,s,day,key)
 s['status']='complete';s['completed_at']=stamp();save(io,key,s);return s

def never_started_draft(c):
 # Missing launch metadata is unknown; only an explicit never-launched draft is hidden.
 timestamps=c.get('timestamps') or {}
 return c.get('status')==4 and 'started' in timestamps and timestamps['started'] is None

def validnum(x):
 if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0:raise ValueError('Unknown advertising amount is not zero')
 return x
def sums(rows):
 out=dict(spend=0,amount=0,orders=0,views=0,clicks=0)
 for row in rows:
  for k in out:out[k]+=row[k]
 return out
def ratio(row):return row['spend']/row['amount']*100 if row and row['amount']>0 else None
def daily_metrics(raw):
 return {k:validnum(raw.get(f)) for k,f in [('spend','sum'),('amount','sum_price'),('orders','orders'),('views','views'),('clicks','clicks')]}
def event_time(at):
 if not isinstance(at,str) or not at.strip():raise ValueError('Receipt timestamp is missing or not a string')
 if at.endswith(' UTC'):at=at[:-4]+'+00:00'
 value=datetime.fromisoformat(at.replace('Z','+00:00'))
 if value.tzinfo is None:raise ValueError('Receipt timestamp needs timezone')
 return value

def verified_ui_funding(payload,cid):
 """Read a verified owner UI funding receipt without inventing an API request."""
 if payload.get('status')!='verified' or payload.get('kind')!='owner_oneoff_budget_topup':return None
 if (payload.get('before') or {}).get('id')!=cid or (payload.get('after') or {}).get('id')!=cid:return None
 try:
  amount=validnum(payload.get('amount_cny'));at=payload.get('verified_at')
  if amount<=0:return None
  parsed=event_time(at)
  if at.endswith(' UTC'):at=parsed.isoformat()
  return at,amount
 except (ValueError,TypeError):return None

def history(records):
 """Normalize verified campaign diffs, mapped bid receipts and verified price readbacks."""
 found=[]
 verified={'verified','verified_active','verified_draft'}
 def walk(x,root):
  if isinstance(x,list):
   for z in x:walk(z,root)
   return
  if not isinstance(x,dict):return
  status=x.get('status');before=x.get('before');after=x.get('after')
  root_ok=root.get('status') in verified
  ok=status in verified
  # A price worker verifies individual applied items by an exact WB readback.
  price_ok=ok or (status=='applied' and (root_ok or root.get('status')=='done'))
  at=x.get('verified_at') or x.get('completed_at') or root.get('verified_at') or root.get('completed_at')
  if at:
   try:
    parsed=event_time(at)
    if at.endswith(' UTC'):at=parsed.isoformat()
   except (ValueError,TypeError):at=None
  if ok and at and isinstance(after,dict) and isinstance(after.get('id'),int):
   cid=after['id']
   old={n['nm_id']:n for n in (before or {}).get('nm_settings',[])}
   new={n['nm_id']:n for n in after.get('nm_settings',[])}
   for nm in old.keys()-new.keys():found.append(dict(cid=cid,nm=nm,kind='excluded',at=at,text='Исключён из РК'))
   for nm in new.keys()-old.keys():
    if before:found.append(dict(cid=cid,nm=nm,kind='added',at=at,text='Добавлен в РК'))
   for nm in old.keys()&new.keys():
    for zone in ['search','recommendations']:
     a=old[nm].get('bids_kopecks',{}).get(zone);b=new[nm].get('bids_kopecks',{}).get(zone)
     if type(a)is int and type(b)is int and a!=b:found.append(dict(cid=cid,nm=nm,kind='bid',at=at,zone=zone,old=a,target=b,text=f'Ставка {a/100:g} → {b/100:g} ¥'))
  # Owner-approved bid batches may have an after map instead of before/after per item.
  if ok and at and isinstance(after,dict) and 'id' not in after:
   for item in x.get('items',[]):
    if not isinstance(item,dict):continue
    cid=item.get('cid');nm=item.get('nm');old=item.get('old');target=item.get('target')
    state=after.get(str(cid),{})
    if state.get('id')!=cid or not all(type(v)is int for v in [cid,nm,old,target]) or old==target:continue
    member=next((n for n in state.get('nm_settings',[]) if n.get('nm_id')==nm),{})
    for zone in ['search','recommendations']:
     if state.get('settings',{}).get('placements',{}).get(zone) and member.get('bids_kopecks',{}).get(zone)==target:
      found.append(dict(cid=cid,nm=nm,kind='bid',at=at,zone=zone,old=old,target=target,text=f'Ставка {old/100:g} → {target/100:g} ¥'))
  price_after=after if isinstance(after,dict) and 'nmID' in after else x.get('readback')
  if price_ok and at and isinstance(before,dict) and isinstance(price_after,dict):
   nm=before.get('nmID')
   if type(nm)is int and price_after.get('nmID')==nm and before.get('currencyIsoCode4217')==price_after.get('currencyIsoCode4217')=='CNY':
    prices=lambda obj:{v.get('discountedPrice') for v in obj.get('sizes',[])}
    a=prices(before);b=prices(price_after)
    if len(a)==len(b)==1 and None not in a|b and a!=b:
     found.append(dict(cid=None,nm=nm,kind='price',at=at,text=f'Цена {next(iter(a)):g} → {next(iter(b)):g} ¥'))
  # Current price worker keeps the approved before value in selection and an exact WB readback.
  if status=='applied' and root.get('status') in verified|{'done','partial'} and at and before is None and isinstance(price_after,dict):
   selection=x.get('selection') or {};request=x.get('request') or {};nm=request.get('nmID')
   try:
    old=Decimal(str(selection['current_cny']));target=Decimal(str(selection['target_cny']))
    sizes=price_after.get('sizes') or []
    actual={Decimal(str(v['discountedPrice'])) for v in sizes}
    exact=bool(sizes) and all(Decimal(str(v['price']))==Decimal(str(request['price'])) for v in sizes)
    if (type(nm)is int and str(selection.get('nm_id'))==str(nm) and price_after.get('nmID')==nm
        and price_after.get('currencyIsoCode4217')=='CNY' and price_after.get('discount')==request.get('discount')
        and actual=={target} and exact and old.is_finite() and target.is_finite() and old>0 and target>0 and old!=target):
     found.append(dict(cid=None,nm=nm,kind='price',at=at,text=f'Цена {old:g} → {target:g} ¥'))
   except (KeyError,TypeError,ValueError,InvalidOperation):pass
  for key in ['items','groups','campaigns']:walk(x.get(key,[]),root)
  if not any(k in x for k in ['status','before','after']):
   for v in x.values():
    if isinstance(v,(dict,list)):walk(v,root)
 for r in records:walk(r.get('payload',r),r.get('payload',r))
 dedup={(x['cid'],x['nm'],x['kind'],x['at']):x for x in found}
 return sorted(dedup.values(),key=lambda x:event_time(x['at']))

def price_map(cat):
 out={}
 for x in cat.get('rows',[]):
  sizes=x.get('sizes',[]);p=x.get('price')
  if p is None and sizes:p=sizes[0].get('discountedPrice')
  out[int(x['nmID'])]=dict(article=x.get('vendorCode') or 'WB '+str(x['nmID']),price=p)
 return out

def recommend(c,n,ds,days,changes,minimum,price):
 """A complete post-change day, trend and expense signals precede any proposed write."""
 nm=n['nm_id'];zone='search' if c['settings']['placements'].get('search') else 'recommendations';old=n.get('bids_kopecks',{}).get(zone)
 if c['status']!=9 or type(old)is not int or old<=0:return None
 rows=[ds.get(d,dict(spend=0,amount=0,orders=0,views=0,clicks=0)) for d in days];period=sums(rows);last=rows[-1];drr=ratio(period);ratios=[ratio(x) for x in rows]
 relevant=[x for x in changes if x['nm']==nm and x['kind'] in ['bid','added','price','returned','relaunch']]
 started=c.get('timestamps',{}).get('started')
 if started:
  event_time(started)
  relevant.append(dict(cid=c['id'],nm=nm,kind='launch',at=started))
 latest=max(relevant,key=lambda x:event_time(x['at'])) if relevant else None
 action=None;reason='';decision='';changed=False;comparison=None;pending_first_day=False
 if latest:
  first=datetime.fromisoformat(latest['at'].replace('Z','+00:00')).astimezone(MSK).date()+timedelta(days=1);end=date.fromisoformat(days[-1])
  if end<first:
   # Newly added products without a full reporting day stay in the campaign summary, not 120 empty SKU rows.
   if latest['kind']=='added':return None
   pending_first_day=True;decision=f'Сохранить {old/100:g} ¥ до {first:%d.%m}; оценка {first+timedelta(days=1):%d.%m}.';reason='Первый полный день теста ещё не завершён.';changed=True
  else:
   postdays=[d for d in sorted(ds) if first.isoformat()<=d<=days[-1]][-3:]
   if postdays:
    post=sums(ds[d] for d in postdays);before_end=first-timedelta(days=2);prekeys=[(before_end-timedelta(days=i)).isoformat() for i in range(len(postdays))]
    if all(d in ds for d in prekeys):
     pre=sums(ds[d] for d in prekeys);a=ratio(pre);b=ratio(post);comparison=dict(before=pre,after=post,from_days=prekeys,to_days=postdays)
     if b is not None and b<=5 and ratio(last) is not None and ratio(last)<=5:return None
     if a is not None and b is not None and a>5 and b<a*.8 and post['orders']>0:
      decision=f'Сохранить {old/100:g} ¥ ещё один полный день; оценка {date.fromisoformat(days[-1])+timedelta(days=2):%d.%m}.';reason=f'ДРР после изменений {a:.2f} → {b:.2f}%; улучшение {(a-b)/a*100:.0f}%.';changed=True
    period_for_decision=post
   else:period_for_decision=period
 else:period_for_decision=period
 if not decision:
  decision_period=period_for_decision
  if latest and 'postdays' in locals() and postdays:
   decision_rows=[ds[d] for d in postdays];ratios=[ratio(x) for x in decision_rows];drr=ratio(decision_period)
  sustained=sum(x is not None and x>5 for x in ratios)>=2
  rising=len(ratios)==3 and all(x is not None for x in ratios) and ratios[0]<ratios[1]<ratios[2] and ratios[2]>5
  threshold=price*.05 if isinstance(price,(int,float)) and price>0 else None
  no_orders=decision_period['orders']==0 and threshold is not None and decision_period['spend']>=threshold
  if no_orders and minimum and old>minimum:
   recent_bid=next((x for x in reversed(changes) if x['cid']==c['id'] and x['nm']==nm and x['kind']=='bid' and x.get('target')==old and x.get('old',old)<old),None)
   target=max(minimum,recent_bid['old'] if recent_bid else int(old*.8))
   action=dict(id=str(c['id'])+':'+str(nm),article='',kind='ad_set_bid',campaign_id=c['id'],nm_id=nm,placement=zone,old_minor=old,target_minor=target);decision=f'Снизить {old/100:g} → {target/100:g} ¥.';reason=f'После изменения: {decision_period["spend"]:.2f} ¥ без рекламных заказов.'
  elif no_orders and latest and period['orders']>0 and len(postdays if 'postdays' in locals() else [])<2 and decision_period['spend']<price*.10:
   decision=f'Сохранить {old/100:g} ¥ до {date.fromisoformat(days[-1])+timedelta(days=1):%d.%m}; при повторении отсутствия заказов — исключение.';reason=f'Первый полный день без заказов: {decision_period["spend"]:.2f} ¥; ранее за 3 дня {period["orders"]:g} заказов.'
  elif no_orders or ((drr is not None and drr>10) and sustained and latest and old<=minimum):
   if len(c['nm_settings'])>1 and c.get('restrictions',{}).get('can_change_nms'):
    action=dict(kind='ad_exclude_sku',campaign_id=c['id'],nm_id=nm,placement=zone,old_minor=old);decision='Исключить SKU из этой РК.'
   else:decision='Предложение паузы всей РК — в отчёте бюджетов.'
   reason=(f'После изменения, за {len(postdays)} полн. дн.: ' if latest else 'За 3 дня: ')+f'расход {decision_period["spend"]:.2f} ¥; рекламных заказов {decision_period["orders"]:g}.'
   if decision_period['orders']>0:reason+=f' ДРР {drr:.2f}%; превышение повторяется, ставка на минимуме WB.'
  elif drr is not None and drr>5 and (sustained or rising):
   if minimum and old>minimum:
    target=max(minimum,int(old*.8));action=dict(kind='ad_set_bid',campaign_id=c['id'],nm_id=nm,placement=zone,old_minor=old,target_minor=target);decision=f'Снизить {old/100:g} → {target/100:g} ¥.'
    reason=(f'Рост ДРР {ratios[0]:.2f} → {ratios[-1]:.2f}%.' if rising else f'ДРР периода {drr:.2f}%; превышение повторяется.')
   elif last['spend']>0:
    decision=f'Сохранить минимум {old/100:g} ¥ до {date.fromisoformat(days[-1])+timedelta(days=1):%d.%m}; затем оценить исключение.';reason=f'ДРР периода {drr:.2f}%; новый более низкий CPC недоступен.'
  elif ratios[-1] is not None and ratios[-1]>5:
   decision=f'Сохранить {old/100:g} ¥; оценка {date.fromisoformat(days[-1])+timedelta(days=2):%d.%m}.';reason=f'Единичное превышение; ДРР периода {drr:.2f}%.'
 if not decision:return None
 if action:action['id']=str(c['id'])+':'+str(nm);action['article']=''
 return dict(nm=nm,daily=rows,period=period,period_drr=ratio(period),decision=decision,reason=reason,action=action,changed=changed,comparison=comparison,pending_first_day=pending_first_day)

def guard_sku_exclusion(row, evidence, context, report_day):
 """Zero direct orders alone do not establish a loss or identify the entry click."""
 if not row or (row.get('action') or {}).get('kind')!='ad_exclude_sku':return row
 review=dict(context);review['economics']=evidence;row['exclusion_review']=review
 blockers=[]
 def fresh(value):
  try:
   at=event_time(value);end=datetime.combine(date.fromisoformat(report_day)+timedelta(days=1),datetime.min.time(),MSK)
   if evidence.get('owner_strategy_review') is True:end=max(end,datetime.now(timezone.utc))
   return 0<=(end-at.astimezone(MSK)).total_seconds()<=48*3600
  except (ValueError,TypeError,KeyError):return False
 if not evidence or not fresh(evidence.get('observed_at')):blockers.append('нет свежей собственной экономики')
 if evidence.get('stock_free') is None or not fresh(evidence.get('stock_observed_at')):blockers.append('нет свежего остатка за вычетом резерва')
 if evidence.get('expected_margin_before_ads_cny') is None:blockers.append('не рассчитан запас маржи до рекламы')
 if evidence.get('sample_reliable') is not True:blockers.append('малая или отсутствующая выкупная выборка')
 post=(row.get('comparison') or {}).get('after') or row['period']
 if isinstance(evidence.get('expected_margin_before_ads_cny'),(int,float)) and evidence['expected_margin_before_ads_cny']>0 and post.get('spend',0)<evidence['expected_margin_before_ads_cny']:blockers.append('расход ещё меньше предварительной маржи одного заказа')
 if post.get('clicks',0)<100:blockers.append('мало кликов для автоматического исключения')
 if context.get('other_sku_orders',0)>0 and evidence.get('entry_sku_attribution_verified') is not True:
  blockers.append('заказы других товаров нельзя распределить между входными SKU')
 if context.get('orders_on_this_sku_other_campaigns',0)>0:blockers.append('товар получает заказы из других РК')
 if evidence.get('owner_strategy_review') is True and fresh(evidence.get('observed_at')) and evidence.get('stock_free') is not None and fresh(evidence.get('stock_observed_at')) and isinstance(evidence.get('expected_margin_before_ads_cny'),(int,float)) and post.get('clicks',0)>=100 and post.get('spend',0)>=max(0,evidence['expected_margin_before_ads_cny']):
  row['economic_risk_warnings']=list(blockers)
  row['reason']+=' Предложение ограничения расходов по стратегии владельца, не доказанный убыток. Малая выборка/ассоциированные заказы и неизвестные расходы сохраняются; исполнение только после ответа на этот PNG.'
  blockers=[]
 if blockers:
  row['candidate_for_manual_review']=True;row['action']=None
  row['decision']='Продолжить тест без повышения; исключение требует проверки.'
  row['reason']='; '.join(blockers)+'. Прямые заказы SKU не отражают весь результат РК.'
 return row

def include_archived(io,source,day):
 """Archive changes eligibility, never historical expense coverage. No budget reads for closed campaigns."""
 s=copy.deepcopy(source)
 inventory=http(io,'/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inventory.get('adverts',[]) if g.get('status')==7 for x in g.get('advert_list',[])})
 known={c['id'] for b in s['batches'].values() for c in b['campaigns'].get('adverts',[]) if c['status']==7}
 missing=[cid for cid in ids if cid not in known]
 # A campaign archived after the cached source was built must move, not duplicate.
 for b in s['batches'].values():
  b['campaigns']['adverts']=[c for c in b['campaigns'].get('adverts',[]) if c['id']not in missing]
  b['stats']=[r for r in b['stats']if r['advertId']not in missing]
  b['budgets']['adverts']=[r for r in b['budgets'].get('adverts',[])if r and r['advertId']not in missing]
 for pos in range(0,len(missing),50):
  batch=missing[pos:pos+50]
  campaigns=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,batch)))
  if {c['id'] for c in campaigns.get('adverts',[])}!=set(batch):raise ValueError('Archived campaign catalogue incomplete')
  stats=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,batch))+'&beginDate='+s['period_from']+'&endDate='+s['period_to'])
  s['batches']['archive:'+','.join(map(str,batch))]=dict(campaigns=campaigns,stats=stats,budgets=dict(adverts=[]))
 s['ids']=sorted(set(s['ids'])|set(ids));s['archived_campaign_ids']=ids
 returned={x['advertId'] for b in s['batches'].values() for x in b['stats']}
 s['archived_missing_stats_ids']=[cid for cid in ids if cid not in returned]
 s['archive_coverage_observed_at']=stamp()
 save(io,'china_agent:advertising_source:'+day+':v2',s)
 return s

def build(s,minima=None):
 minima=minima or {};end=date.fromisoformat(s['period_to']);days=[str(end-timedelta(days=i)) for i in [2,1,0]];labels=price_map(s['catalogue']);changes=history(s['executions'])+list(s.get('verified_composition_changes',[]));cs=[];budgets={};raw=[]
 for b in s['batches'].values():cs+=b['campaigns'].get('adverts',[]);raw+=b['stats'];budgets.update({x['advertId']:x for x in b['budgets'].get('adverts',[]) if x is not None})
 if {c['id'] for c in cs}!=set(s['ids']) or len(cs)!=len(s['ids']):raise ValueError('Campaign readback incomplete')
 for rec in s.get('experience',[]):
  event=rec.get('payload',rec);act=event.get('action',{});at=event.get('started_at')
  if act.get('kind')!='price_change' or not at:continue
  for nm in act.get('nm_ids',[]):
   for c in cs:
    if any(n['nm_id']==nm for n in c.get('nm_settings',[])):changes.append(dict(cid=c['id'],nm=nm,kind='price',at=at,text='Цена '+str(act.get('before'))+' → '+str(act.get('after'))+' ¥'))
 changes.sort(key=lambda x:x['at'])
 global_prices=[x for x in changes if x['cid'] is None and x['kind']=='price']
 changes=[x for x in changes if x['cid'] is not None]+[dict(x,cid=c['id']) for x in global_prices for c in cs if any(n['nm_id']==x['nm'] for n in c.get('nm_settings',[]))]
 # WB's verified launch timestamp establishes a new campaign's first complete day too.
 for c in cs:
  at=c.get('timestamps',{}).get('started') or c.get('timestamps',{}).get('created')
  if at and event_time(at).astimezone(MSK).date().isoformat()>=days[0]:
   for n in c.get('nm_settings',[]):changes.append(dict(cid=c['id'],nm=n['nm_id'],kind='added',at=at,text='Запуск РК'))
 changes.sort(key=lambda x:event_time(x['at']))
 stat={c['advertId']:c for c in raw};out=[]
 for c in cs:
  if never_started_draft(c):continue
  if c.get('currency')!='CNY':raise ValueError('Campaign currency mismatch')
  bid=c['settings']['payment_type'];zone='поиск' if c['settings']['placements'].get('search') else 'рекомендации';cp=stat.get(c['id']);byday={};byproduct={}
  if cp:
   for d in cp.get('days',[]):
    day=d['date'][:10];byday[day]=daily_metrics(d)
    for app in d.get('apps',[]):
     for n in app.get('nms',[]):
      target=byproduct.setdefault(n['nmId'],{});v=target.setdefault(day,dict(spend=0,amount=0,orders=0,views=0,clicks=0))
      for k,x in daily_metrics(n).items():v[k]+=x
  created=c.get('timestamps',{}).get('created','')[:10];new=created>=s['period_to']
  # Missing days within a returned WB daily series have zero activity; a missing campaign response remains unknown.
  zeros=dict(spend=0,amount=0,orders=0,views=0,clicks=0)
  if cp:
   for d in days:byday.setdefault(d,dict(zeros))
   for ds in byproduct.values():
    for i in range(7):ds.setdefault(str(end-timedelta(days=i)),dict(zeros))
  period=sums(byday[d] for d in days) if cp else None;last=byday.get(days[-1]);balance=budgets.get(c['id'])
  if c['status']==7:balance=dict(total=None,currency='CNY') # not a zero budget or missing historical spend
  elif not balance or balance.get('currency')!='CNY':raise ValueError('Campaign balance missing')
  focus=[]
  for n in c.get('nm_settings',[]):
   if c['status']==7:continue # historical totals retained; never propose actions on archives
   if new:continue
   nm=n['nm_id'];ds=byproduct.get(nm,{})
   if not ds:continue
   minimum=minima.get(str(c['id'])+':'+str(nm),0)
   r=recommend(c,n,ds,days,changes,minimum,labels.get(nm,{}).get('price'))
   if r:
    r['article']=labels.get(nm,{}).get('article','WB '+str(nm));recent=[x for x in changes if x['cid']==c['id'] and x['nm']==nm];r['done']=recent[-1]['text']+' · '+datetime.fromisoformat(recent[-1]['at'].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m %H:%M') if recent else 'Нет подтверждённых изменений'
    if r['action']:
     if r['article'].startswith('WB '):r['action']=None;r['decision']='Нет точного артикула: действие не готово.'
     else:r['action']['article']=r['article']
    if (r.get('action') or {}).get('kind')=='ad_exclude_sku':
     members={m['nm_id'] for m in c['nm_settings']}
     external=sum(sums(ds0.get(d,zeros) for d in days)['orders'] for key,ds0 in byproduct.items() if key not in members)
     elsewhere=0
     for other in raw:
      if other['advertId']==c['id']:continue
      for day0 in other.get('days',[]):
       if day0['date'][:10] not in days:continue
       elsewhere+=sum(x.get('orders',0) for app in day0.get('apps',[]) for x in app.get('nms',[]) if x['nmId']==nm)
     evidence=(s.get('economics',{}).get('rows',{}).get(str(nm)) or {}).copy()
     evidence.setdefault('observed_at',s.get('economics',{}).get('observed_at'))
     r=guard_sku_exclusion(r,evidence,dict(other_sku_orders=external,orders_on_this_sku_other_campaigns=elsewhere,attribution='campaign_totals_only'),s['period_to'])
    focus.append(r)
  # Show recent confirmed exclusions without proposing to exclude them again.
  for x in changes:
   if x['cid']!=c['id'] or x['kind']!='excluded' or x['nm'] in {n['nm_id'] for n in c.get('nm_settings',[])}:continue
   at=datetime.fromisoformat(x['at'].replace('Z','+00:00')).astimezone(MSK).date()
   if (date.fromisoformat(s['period_to'])+timedelta(days=1)-at).days not in [0,1]:continue
   ds=byproduct.get(x['nm'],{});pp=sums(ds.get(d,zeros) for d in days)
   if any(r['nm']==x['nm'] for r in focus):continue
   focus.append(dict(nm=x['nm'],article=labels.get(x['nm'],{}).get('article','WB '+str(x['nm'])),daily=[ds.get(d,zeros) for d in days],period=pp,period_drr=ratio(pp),decision='Выполнено. Повторно не исключать.',reason='',action=None,done=x['text']+' · '+datetime.fromisoformat(x['at'].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m %H:%M')))
  all_excluded={r['nm'] for r in focus if r['action'] and r['action']['kind']=='ad_exclude_sku'}=={n['nm_id'] for n in c['nm_settings']}
  if all_excluded:
   for r in focus:
    if r['action']:r['action']=None;r['decision']='Приостановить всю РК; подтверждение в отчёте бюджетов.'
  focus.sort(key=lambda r:(r['action'] is None,r['article']))
  member_days=[sum(byproduct.get(n['nm_id'],{}).get(d,zeros)['spend'] for n in c.get('nm_settings',[])) for d in days] if cp else []
  rate=max(member_days[-1],sum(member_days)/3) if member_days else None
  latest_adds=[x for x in changes if x['cid']==c['id'] and x['kind']=='added' and x['at'][:10]>=days[0]]
  incomplete_composition=new or any(datetime.fromisoformat(x['at'].replace('Z','+00:00')).astimezone(MSK).date()+timedelta(days=1)>end for x in latest_adds)
  forecast=None if incomplete_composition else rate*3 if rate is not None else None
  bdrr=ratio(period);action=None;recommendation='Не пополнять: первый полный день нового состава ещё не оценён.' if incomplete_composition else 'Не пополнять сейчас.'
  if c['status']!=9:recommendation='Архив: исторические расходы сохранены; не запускать и не пополнять.' if c['status']==7 else 'Сохранить текущую паузу/черновик; не пополнять.'
  elif cp and len(c['nm_settings'])==1 and period['orders']==0 and period['spend']>0 and not any(r.get('pending_first_day') for r in focus):
   nm=c['nm_settings'][0]['nm_id'];price=labels.get(nm,{}).get('price')
   if isinstance(price,(int,float)) and period['spend']>=price*.05 and not incomplete_composition:
    action=dict(id='pause:'+str(c['id']),kind='pause_campaign',campaign_id=c['id'],status_before=9,nm_ids=sorted(n['nm_id'] for n in c['nm_settings']));recommendation='Приостановить РК. За 3 дня '+f'{period["spend"]:.2f} ¥; 0 рекламных заказов.'
  if c['status']==9 and all_excluded and not incomplete_composition:
   action=dict(id='pause:'+str(c['id']),kind='pause_campaign',campaign_id=c['id'],status_before=9,nm_ids=sorted(n['nm_id'] for n in c['nm_settings']));recommendation='Приостановить РК: все текущие SKU требуют исключения; расход 3 дней '+str(round(period['spend'],2))+' ¥.'
  econ=s.get('economics',{});econrows=econ.get('rows',{});econ_ok=econ.get('status')=='available' and all(econrows.get(str(n['nm_id']),{}).get('expected_total_profit_rub',-1)>=0 for n in c['nm_settings'])
  if not action and c['status']==9 and forecast is not None and bdrr is not None and bdrr<=5 and period['orders']>=3 and forecast>balance['total'] and not econ_ok:
   missing=sum(str(n['nm_id']) not in econrows for n in c['nm_settings']);recommendation='Пополнение не готово: '+str(missing)+' SKU без свежей подтверждённой модели прибыли.' if missing else 'Не пополнять: модель прибыли содержит отрицательный или устаревший результат.'
  if not action and c['status']==9 and forecast is not None and bdrr is not None and bdrr<=5 and period['orders']>=3 and forecast>balance['total'] and econ_ok and not any(r['action'] for r in focus):
   amount=max(math.ceil(s['config']['minTopUp']/100),math.ceil((forecast-balance['total'])/50)*50)
   action=dict(id='topup:'+str(c['id']),kind='topup_campaign',campaign_id=c['id'],amount_cny=amount,balance_before=balance['total'],target_balance=balance['total']+amount,status_before=9,nm_ids=sorted(n['nm_id'] for n in c['nm_settings']));recommendation=f'Пополнить на {amount} ¥. Расчёт на 3 дня: {forecast:.2f} ¥.'
  elif not action and bdrr is not None and bdrr>5 and not incomplete_composition:recommendation='Не пополнять: ДРР '+f'{bdrr:.2f}%. '+('Сначала изменения SKU из рекламного отчёта.' if any(r['action'] for r in focus) else 'Сохранить бюджет до следующей оценки.')
  funds=[]
  for rec in s['executions']:
   payload=rec.get('payload',rec)
   def funding_steps(z):
    if isinstance(z,dict):
     ui_funding=verified_ui_funding(z,c['id'])
     if ui_funding:funds.append(ui_funding)
     st=z.get('steps',{})
     if isinstance(st,dict):
      for label,v in st.items():
       if not isinstance(v,dict) or v.get('status') not in ['verified','accepted']:continue
       path=v.get('path','');body=v.get('body') or {}
       if path=='/adv/v1/budget/deposit?id='+str(c['id']) and body.get('sum'):
        at=v.get('submitted_at') or payload.get('completed_at') or payload.get('verified_at')
        if at:funds.append((at,body['sum']))
     for k in ['items','campaigns','groups']:
      v=z.get(k,[])
      for child in v.values() if isinstance(v,dict) else v if isinstance(v,list) else []:funding_steps(child)
   funding_steps(payload)
  recent_funds=[f for f in funds if f[0][:10]>=days[-1]]
  funding_done='; '.join('+'+str(f[1])+' ¥ · '+datetime.fromisoformat(f[0].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m %H:%M') for f in sorted(set(recent_funds))) or 'Нет новых подтверждённых пополнений'
  out.append(dict(budget_reference_need=rate*3 if rate is not None else None,budget_review_required=bool(c['status']==9 and rate is not None and rate*3>balance['total']),minimum_topup_cny=s['config']['minTopUp']/100,funding_done=funding_done,id=c['id'],name=c['settings']['name'],zone=zone,payment=bid,status=c['status'],period=period,last=last,drr=bdrr,focus=focus,balance=balance['total'],forecast=forecast,coverage=balance['total']/rate if c['status']!=7 and rate and not incomplete_composition else None,budget_recommendation=recommendation,budget_action=action,new_composition=incomplete_composition,missing_stats=cp is None,created=created))
 bundle=dict(version=VERSION,day=str(end+timedelta(days=1)),days=days,source_observed_at=datetime.fromisoformat(s['observed_at'].replace('Z','+00:00')).astimezone(MSK).strftime('%d.%m.%Y %H:%M МСК'),campaigns=out,wb_writes=0)
 from china_budget_reserve import attach_completed_evidence,apply
 return apply(attach_completed_evidence(bundle,s,changes),s['config']['minTopUp']/100)

def prepare(io,day):
 s=dict(collect(io,day));s['intraday']=io.get('china_agent:advertising_intraday:'+day+':v1') or {};minimums={}
 s=include_archived(io,s,day)
 if getattr(io,'on_demand_menu',False):
  ids=sorted({cp['id']for b in s['batches'].values()for cp in b['campaigns']['adverts']});states={}
  for offset in range(0,len(ids),50):
   group=ids[offset:offset+50];rows=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,group))).get('adverts',[])
   if {cp['id']for cp in rows}!=set(group):raise ValueError('Current menu campaign coverage incomplete')
   states.update({cp['id']:cp for cp in rows})
  for batch in s['batches'].values():batch['campaigns']['adverts']=[states[cp['id']]for cp in batch['campaigns']['adverts']]
  s['current_state_observed_at']=stamp()
 s=refresh_budget_context(io,s,day)
 from china_campaign_pause_reason import attach_previous
 s=attach_previous(io,s)
 # Query minima only for existing products with a meaningful signal, on their actual campaign/placement.
 rough=build(s)
 from china_morning_readiness import enrich_economics
 from china_advertising_full_growth import enabled as full_growth_enabled,collect as collect_full_growth
 s=collect_full_growth(io,s,day) if full_growth_enabled(io) else enrich_economics(io,s,rough,day)
 save(io,'china_agent:advertising_source:'+day+':v2',s)
 for c in rough['campaigns']:
  members={n['nm_id']for b in s['batches'].values()for cp in b['campaigns']['adverts']if cp['id']==c['id']for n in cp.get('nm_settings',[])}
  ids=sorted({r['nm'] for r in c['focus'] if r['nm']in members and not r.get('pending_first_day') and 'Выполнено.' not in r['decision']})
  if not ids or c['status']!=9 or c['payment']!='cpc':continue
  zone='search' if c['zone']=='поиск' else 'recommendation'
  j=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=ids,payment_type='cpc',placement_types=[zone]))
  returned=set()
  for x in j.get('bids',[]):
   returned.add(x['nm_id'])
   v=[b['value'] for b in x.get('bids',[]) if b.get('type')==zone and b.get('currency')=='CNY']
   if len(v)!=1:raise ValueError('Campaign minimum is ambiguous')
   minimums[str(c['id'])+':'+str(x['nm_id'])]=v[0]
  if returned!=set(ids):raise ValueError('Incomplete campaign minima')
 from china_advertising_cards import enhance
 # Exact non-member quotes are required before an addition appears in the PNG.
 if not s.get('full_growth_inputs'):
  s['addition_bid_quotes']={};s['addition_quote_errors']={}
  for nm in s.get('addition_candidate_ids',[]):
   cid=(s.get('addition_targets')or{}).get(str(nm))
   if not cid:continue
   try:
    response=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[nm],payment_type='cpc',placement_types=['recommendation']))
    quotes=[bid['value'] for row in response.get('bids',[])if row.get('nm_id')==nm for bid in row.get('bids',[])if bid.get('type')=='recommendation'and bid.get('currency')=='CNY']
    if len(quotes)!=1 or type(quotes[0])is not int or quotes[0]<=0 or quotes[0]%s['config']['cpcStep']:raise ValueError('Exact addition bid unconfirmed')
    s['addition_bid_quotes'][str(nm)]=dict(campaign_id=cid,target_minor=quotes[0],bid_verified=True,observed_at=stamp())
   except Exception as ex:s['addition_quote_errors'][str(nm)]=type(ex).__name__
 save(io,'china_agent:advertising_source:'+day+':v2',s)
 from china_advertising_growth import enrich
 from china_advertising_economic_review import apply as economic_review
 result=economic_review(enhance(build(s,minimums),s),s,minimums) if s.get('full_growth_inputs') else economic_review(enrich(io,s,enhance(build(s,minimums),s)),s,minimums)
 if s.get('full_growth_inputs'):
  from china_advertising_full_growth import enrich as full_growth_review
  result=full_growth_review(io,s,result)
 if s.get('morning_fresh_inputs',{}).get('errors') or result.get('economic_review_blockers') and not s.get('full_growth_inputs'):
  from china_morning_readiness import PendingAdvertisingDay
  raise PendingAdvertisingDay('Recommendation inputs incomplete; preserve source and retry instead of freezing an unfinished report')
 from china_advertising_directions import attach
 from china_budget_page_actions import owner_policy
 result=owner_policy(io,attach(result,s))
 from china_morning_rules_review import enabled as no_model_enabled,review as no_model_review
 if no_model_enabled(io):result=no_model_review(io,result,s)
 else:
  from china_codex_reports import review_advertising
  result=review_advertising(io,result,s,'advertising:'+day+':morning')
 from china_sales_growth_review import attach as sales_review
 result=sales_review(result)
 result['mandatory_campaign_format']=(io.get(FORMAT)or{}).get('mandatory') is True
 from china_new_campaign_reporting import attach as attach_new_campaign_reporting
 return attach_new_campaign_reporting(io,result)







