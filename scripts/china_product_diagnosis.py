"""Product-wide, read-only decline evidence. No mutations or automatic decisions."""
import os,re,math,hashlib,json
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:product_diagnosis:v1:'
FIELDS=('views','clicks','carts','orders','spend','amount')
def num(x):return type(x) in (int,float) and math.isfinite(x) and x>=0
def ratio(a,b):return 100*a/b if num(a) and num(b) and b>0 else None
def combine(rows):
 return {k:sum(r[k] for r in rows) if rows and all(num(r.get(k)) for r in rows) else None for k in FIELDS}
def ad_campaigns(rows,nm,days):
 result={};seen=set()
 for row in rows:
  if row.get('level')!='SKU_app' or row.get('nm_id')!=nm or row.get('date') not in days:continue
  key=(row['campaign_id'],row['date'],nm,row.get('app_id'))
  if row.get('app_id') is None:raise ValueError('Advertising application identity missing')
  if key in seen:raise ValueError('Duplicate SKU/application attribution')
  seen.add(key)
  result.setdefault(row['campaign_id'],{}).setdefault(row['date'],[]).append(row)
 return {cid:{day:combine(ds[day]) if day in ds else {k:None for k in FIELDS} for day in days} for cid,ds in result.items()}
def normalize_ads(raw,ids,first,last):
 rows=[];seen=set()
 for c in raw:
  cid=c['advertId']
  if cid in seen or c.get('currency')!='CNY':raise ValueError('Campaign duplicate/currency mismatch')
  seen.add(cid)
  for d in c.get('days',[]):
   day=d['date'][:10]
   if not first<=day<=last:raise ValueError('Advertising period mismatch')
   for index,app in enumerate(d.get('apps',[])):
    app_id=app.get('appType',index)
    for n in app.get('nms',[]):
     if n.get('nmId') not in ids:continue
     rows.append(dict(campaign_id=cid,date=day,nm_id=n['nmId'],app_id=app_id,level='SKU_app',**dict(zip(FIELDS,[n.get(k) for k in ['views','clicks','atbs','orders','sum','sum_price']]))))
 return rows,seen
def all_ads(w,ids,first,last):
 key=ROOT+'ads:'+hashlib.sha256(json.dumps([sorted(ids),first,last]).encode()).hexdigest()[:20]
 saved=w.get(key)
 if saved and saved.get('cabinet')=='token_3' and 0<=(w.now-datetime.fromisoformat(saved['observed_at'])).total_seconds()<900:return saved
 from china_analytic_dialog import reading
 import requests
 with reading():
  r=requests.get('https://advert-api.wildberries.ru/adv/v1/promotion/count',headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=35,allow_redirects=False)
  if not r.ok:raise RuntimeError('Campaign catalogue HTTP '+str(r.status_code))
  groups=r.json().get('adverts')
  if not isinstance(groups,list) or any(not isinstance(g.get('advert_list'),list) or g.get('count',len(g['advert_list']))!=len(g['advert_list']) for g in groups):raise ValueError('Incomplete campaign catalogue')
  catalogue=sorted({a['advertId'] for g in groups for a in g['advert_list']})
  if any(type(cid)is not int or cid<=0 for cid in catalogue):raise ValueError('Invalid campaign catalogue identity')
  if len(catalogue)>100:raise ValueError('More than100 campaigns: coverage not complete within bounded read')
  raw=[];returned=set()
  for start in range(0,len(catalogue),50):
   batch=catalogue[start:start+50]
   r=requests.get('https://advert-api.wildberries.ru/adv/v3/fullstats',headers={'Authorization':os.environ['WB_TOKEN_3']},params={'ids':','.join(map(str,batch)),'beginDate':first,'endDate':last},timeout=45,allow_redirects=False)
   if not r.ok:raise RuntimeError('Advertising HTTP '+str(r.status_code))
   body=r.json()
   if not isinstance(body,list):raise ValueError('Advertising response shape')
   if any(c.get('advertId') not in batch for c in body):raise ValueError('Campaign outside requested catalogue')
   raw+=body;returned.update(c['advertId'] for c in body)
 rows,seen=normalize_ads(raw,ids,first,last)
 result=dict(source='WB fullstats, catalogue all statuses',source_key=key,observed_at=w.now.isoformat(),cabinet='token_3',currency='CNY',period_from=first,period_to=last,rows=rows,catalogue_count=len(catalogue),catalogue_ids=catalogue,catalogue_all_statuses=True,returned_campaign_count=len(returned),missing_campaign_ids=sorted(set(catalogue)-returned),coverage_complete=returned==set(catalogue),wb_writes=0)
 w.save(key,result);return result
def funnel_rows(state,ids,days):
 if not state.get('complete') or state.get('cabinet')!='token_3':raise ValueError('Incomplete/cross-cabinet funnel')
 result={};seen=set()
 for p in state.get('rows',[]):
  nm=p['nm_id']
  if nm not in ids:continue
  if nm in seen:raise ValueError('Duplicate funnel SKU')
  seen.add(nm);result[nm]={}
  for part,day in [('past',days[0]),('selected',days[1])]:
   r=p[part]
   if r.get('period_from')!=day or r.get('period_to')!=day or r.get('scope')!='all_sources':raise ValueError('Funnel scope/period mismatch')
   values=dict(opens=r.get('clicks'),carts=r.get('cart_count'),orders=r.get('orders'))
   if not all(num(v) for v in values.values()):raise ValueError('Missing/invalid funnel counter')
   result[nm][day]=values
 return result
def fbs_daily(source,ids,days):
 result={n:{d:0 for d in days} for n in ids};seen={};rows=source.get('orders')
 if source.get('available') is False or not isinstance(rows,list):return {n:{d:None for d in days} for n in ids}
 for r in rows:
  oid=r.get('id');nm=r.get('nmId')
  if oid is None or nm not in ids:raise ValueError('FBS identity/scope mismatch')
  if oid in seen:
   if seen[oid]!=r:raise ValueError('Conflicting FBS order identity')
   continue
  seen[oid]=r
  day=datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(MSK).date().isoformat()
  if day not in days:raise ValueError('FBS period mismatch')
  result[nm][day]+=1
 return result
def history_state(events,nm,days,complete):
 found=[];uncertain=[];waiting=False
 for e in events:
  if nm not in e.get('action',{}).get('nm_ids',[]):continue
  if e.get('record_type')!='verified_action' or e.get('operational_outcome')!='verified' or not e.get('source_key') or not e.get('verified_at'):
   uncertain.append(e.get('event_id'));continue
  when=e.get('started_at')
  try:day=datetime.fromisoformat(when.replace('Z','+00:00')).astimezone(MSK).date()
  except (AttributeError,ValueError):uncertain.append(e.get('event_id'));continue
  waiting=waiting or bool(e.get('comparison',{}).get('evaluate_from') and e['comparison']['evaluate_from']>str(datetime.fromisoformat(days[-1]).date()+timedelta(days=1)))
  found.append(dict(date=str(day),first_full_day=str(day+timedelta(days=1)),kind=e.get('action',{}).get('kind'),source_key=e['source_key']))
 latest=max((e['date'] for e in found),default=None)
 contaminated=waiting or bool(latest and latest>=days[0])
 return dict(verified_changes=found,history_complete=complete,uncertain_events=uncertain,comparison_confounded=contaminated,repeat_ready=complete and not uncertain and not contaminated,causality='not_established')
def diagnose(before,after,ads,history):
 if history['comparison_confounded']:return dict(signal='recent_change',recommendation='Не повторять изменение: день изменения исключить; оценить первый полный следующий день и отложенные заказы.')
 if not before or not after:return dict(signal='unknown',recommendation='Нет полной общей воронки; не менять рекламу по отсутствующей строке.')
 if not all(num(x.get(k)) for x in (before,after) for k in ('opens','carts','orders')):return dict(signal='unknown',recommendation='Неполные счётчики воронки не считать нулём; решение не подтверждено.')
 if num(ads.get('views')) and ads['views']>0 and ads.get('clicks')==0:return dict(signal='ad_clicks',recommendation='Показы есть без кликов: кандидат на тест первого фото и релевантности размещения; повышение ставки само по себе этот этап не исправляет.')
 if before['opens'] and after['opens']==0:return dict(signal='traffic',recommendation='В общей воронке нет переходов: кандидат на восстановление видимости, но запуск/ставку выбирать только после проверки доступности товара и экономики.')
 if before['opens'] and after['opens']<before['opens'] and (ratio(after['carts'],after['opens']) or 0)>=(ratio(before['carts'],before['opens']) or 0):
  return dict(signal='traffic',recommendation='Кандидат на ограниченный тест восстановления охвата: переходов стало меньше, переход в корзину не ухудшился. Ставку/бюджет выбирать только отдельным планом с экономикой.')
 old,new=ratio(before['carts'],before['opens']),ratio(after['carts'],after['opens'])
 if old is not None and new is not None and new<old:
  return dict(signal='card_cart',recommendation='Кандидат на тест подачи товара в карточке и соответствия трафика; не наращивать прежний трафик вслепую.')
 old,new=ratio(before['orders'],before['carts']),ratio(after['orders'],after['carts'])
 if old is not None and new is not None and new<old:
  return dict(signal='cart_order',recommendation='Не считать корзины потерянными заказами: учитывать отложенный выбор и позднюю атрибуцию. Не отключать отдельную РК только из-за распределения заказов между размещениями.')
 return dict(signal='not_localized',recommendation='По этим двум дням конкретный провал этапа не подтверждён; менять размещения без дополнительного основания не предлагаю.')
def build(ids,labels,days,ads,funnel,orders,events=(),history_complete=False):
 rows=[]
 for nm in ids:
  campaigns=ad_campaigns(ads.get('rows',[]),nm,days);campaign_summaries=[]
  for cid,ds in sorted(campaigns.items()):
   total=combine(list(ds.values()))
   campaign_summaries.append(dict(campaign_id=cid,daily=ds,**total,drr_pct=ratio(total['spend'],total['amount'])))
  total=combine(campaign_summaries);hist=history_state(events,nm,days,history_complete);general=funnel.get(nm,{})
  before,after=general.get(days[0]),general.get(days[1]);last_ad=combine([c[days[1]] for c in campaigns.values()])
  d=diagnose(before,after,last_ad,hist)
  if hist['uncertain_events']:d['recommendation']+=' Есть неопределённое действие: не повторять его без канонической квитанции.'
  if not hist['history_complete']:d['recommendation']+=' История изменений неполна: повторный тест пока не согласовывать.'
  rows.append(dict(nm_id=nm,article=labels[nm],days=days,all_FBS_orders=orders.get(nm,{d:None for d in days}),general_funnel=general,campaigns=campaign_summaries,advertising_totals=total,advertising_drr_pct=ratio(total['spend'],total['amount']),coverage_complete=ads.get('coverage_complete') is True,history=hist,diagnosis=d,small_sample=not after or not num(after.get('carts')) or after['carts']<20,causality='not_established'))
 return dict(rows=rows,period_from=days[0],period_to=days[1],wb_writes=0,definitions='FBS orders, funnel ordered units, and advertising attribution are separate. Never add them; ad attribution counters are not unique order IDs. All-RK spend coverage requires a complete catalogue response.')
def render(result):
 lines=[f'Диагностика по завершённым дням {result["period_from"]} → {result["period_to"]}.']
 def n(x):return 'нет данных' if x is None else f'{x:,.2f}'.rstrip('0').rstrip('.').replace(',',' ')
 for r in result['rows']:
  a,b=r['days'];f=r['general_funnel'];t=r['advertising_totals']
  lines.append(f'\\n{r["article"]}: FBS-заказы {n(r["all_FBS_orders"].get(a))} → {n(r["all_FBS_orders"].get(b))}; не выкупы.')
  lines.append('Общая воронка (переходы / корзины / заказанные товары): '+' → '.join(' / '.join(n(f.get(d,{}).get(k)) for k in ['opens','carts','orders']) for d in [a,b])+'.')
  lines.append('Расход по доступным РК: '+n(t['spend'])+' CNY; сумма рекламной атрибуции '+n(t['amount'])+' CNY; учётная ДРР '+(n(r['advertising_drr_pct'])+'%' if r['advertising_drr_pct'] is not None else 'не определена')+'.')
  for c in r['campaigns']:lines.append(f'РК {c["campaign_id"]}: расход {n(c["spend"])} CNY; атрибутировано {n(c["orders"])} заказов на {n(c["amount"])} CNY.')
  if not r['campaigns']:lines.append('Строк SKU в рекламе нет; это не подтверждённый нулевой расход.')
  if not r['coverage_complete']:lines.append('Полнота охвата всех РК не подтверждена; общий расход может быть выше.')
  lines.append(r['diagnosis']['recommendation'])
  if r['small_sample']:lines.append('Малая выборка корзин: вывод предварительный.')
 lines.append('\\nРекламные заказы не складываю с FBS. Причинность не доказана; экономика, наличие и текущие минимумы здесь не проверялись, точных изменений ставок/цен не предлагаю.')
 return '\n'.join(lines).replace('\\n','\n')
def requested(text):
 return bool(re.search(r'причин.*просад|почему.*(?:упал|пада|нет.*заказ|просел)|разбер.*(?:заказ|просад|продаж)|(?:все|всех).*рк|общ.*расход.*товар',text,re.I)) and not re.search(r'подними|повысь|пополн|отключи|добавь|примени',text,re.I)
def handle(w,job,history):
 from china_article_diagnostic_read import handle as legacy
 if not requested(job.get('request_text','')):return legacy(w,job,history)
 from china_article_diagnostic import scope
 from china_analytic_dialog import Analyst,reading
 from china_wb_evidence import Reports
 ids=scope(w,job,history)
 if not ids and re.search(r'\b\d+-[a-z]',job.get('request_text',''),re.I):return legacy(w,job,history)
 if len(ids)>5:return None # Let the bounded report route handle larger requests.
 last=w.now.astimezone(MSK).date()-timedelta(days=1);days=[str(last-timedelta(days=1)),str(last)]
 analyst=Analyst(w,job,history);labels={int(n):a for n,a in w.catalog()};gaps=[];sources=[]
 def attempt(name,fn,default):
  try:
   value=fn();sources.append(dict(name=name,observed_at=value.get('observed_at'),source_key=value.get('source_key')));return value
  except Exception as ex:gaps.append(dict(source=name,error=type(ex).__name__));return default
 if not ids:
  overview=attempt('WB FBS decline selection',lambda:analyst.live('orders',[],days[0],days[1]),{})
  ids=[r['nm_id'] for r in overview.get('top_yesterday_declines',[])[:5] if r.get('nm_id') in labels]
  if not ids:
   text='Подбор просевших товаров за '+days[0]+'–'+days[1]+(' не завершён: источник заказов недоступен.' if gaps else ': в полученной ленте не найдены товары с меньшим числом созданных FBS-заказов. Реклама и общая воронка для них ещё не проверялись.')
   return text,[dict(name='product_wide_diagnosis',result=dict(status='partial' if gaps else 'no_decliners',sources=sources,gaps=gaps),read_only=True)]
 orders=attempt('WB FBS',lambda:analyst.live('orders',ids,days[0],days[1]),{})
 ads=attempt('All-catalogue WB advertising',lambda:all_ads(w,ids,*days),{})
 with reading():f=attempt('WB funnel',lambda:Reports(w).funnel(days[1],days[1]),{})
 funnel=attempt('Funnel validation',lambda:dict(data=funnel_rows(f,ids,days)),{}).get('data',{})
 counts=attempt('FBS validation',lambda:dict(data=fbs_daily(orders,ids,days)),{}).get('data',{})
 events=[];history_complete=False
 try:
  from china_experience import decision_context
  h=decision_context(w,ids);events=h.get('experiences',[]);history_complete=isinstance(h.get('experiences'),list) and h.get('total_matching_returned')==len(events) and len(events)<200
 except Exception as ex:gaps.append(dict(source='Verified history',error=type(ex).__name__))
 try:result=build(ids,labels,days,ads,funnel,counts,events,history_complete)
 except ValueError as ex:
  gaps.append(dict(source='Advertising validation',error=type(ex).__name__))
  ads=dict(rows=[],coverage_complete=False)
  result=build(ids,labels,days,ads,funnel,counts,events,history_complete)
 result.update(observed_at=w.now.isoformat(),sources=sources,gaps=gaps,status='complete' if not gaps and ads.get('coverage_complete') and history_complete and all(r['diagnosis']['signal']!='unknown' and r['advertising_totals']['spend'] is not None and all(v is not None for v in r['all_FBS_orders'].values()) for r in result['rows']) else 'partial')
 key=ROOT+'job:'+str(job['id']);result['source_key']=key;w.save(key,result)
 return render(result),[dict(name='product_wide_diagnosis',result=result,read_only=True)]
