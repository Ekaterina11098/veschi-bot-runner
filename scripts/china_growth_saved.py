"""Saved advertising evidence for discussion. Never requests WB or creates execution plans."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
def metric(raw):
 return dict(spend=raw.get('sum',0),amount=raw.get('sum_price',0),orders=raw.get('orders',0),clicks=raw.get('clicks',0))
def rate(v):return round(v['spend']/v['amount']*100,2) if v['amount'] else None
def saved(w,kind,days):
 day=str(w.now.astimezone(MSK).date())
 current=w.get('china_agent:advertising_midday_source:'+day+':v2') or {}
 if current.get('status')!='complete':current=w.get('china_agent:advertising_intraday:'+day+':v1') or {}
 historical=w.get('china_agent:advertising_source:'+day+':v2') or {}
 if current.get('batches'):
  camps=[c for b in current['batches'].values() for c in b.get('campaigns',{}).get('adverts',[])]
  stats=[r for b in current['batches'].values() for r in b.get('stats',[])]
 else:
  camps=current.get('campaigns',[]);stats=[r for b in current.get('ad_batches',[]) for r in b.get('data',[])]
 registry=w.get('china_agent:verified_campaign_state:v1') or {}
 byid={c['id']:c for c in camps}
 for cid,key in registry.items():
  receipt=w.get(key) or {}
  after=receipt.get('after') or {}
  if receipt.get('status')=='verified' and str(after.get('id'))==cid:byid[int(cid)]=after
 camps=list(byid.values())
 if not camps:
  return dict(status='diagnostic',available=True,rows=[],requires_confirmation=True,wb_reads=0,wb_writes=0,limitations=['Сохранённый актуальный состав не найден; предварительный расчёт недоступен. Не обращаться к WB повторно без необходимости.'])
 observed=current.get('completed_at') or current.get('observed_at')
 try:age=(w.now-datetime.fromisoformat(observed.replace('Z','+00:00'))).total_seconds()/3600
 except (ValueError,TypeError):age=None
 if age is None or age>24:return dict(status='diagnostic',available=True,rows=[],observed_at=observed,wb_reads=0,wb_writes=0,limitations=['Сохранённый состав старше24часов или дата не подтверждена. Нужна узкая свежая проверка; это не отсутствие всей истории.'])
 labels={int(x['nmID']):x.get('vendorCode','WB '+str(x['nmID'])) for x in (current.get('catalogue') or {}).get('rows',[])}
 if not labels:labels={int(x['nmID']):x.get('vendorCode','WB '+str(x['nmID'])) for x in (w.get('china_agent:prices:v1') or {}).get('rows',[])}
 def aggregate(raw,dates):
  out={}
  for r in raw:
   cid=r['advertId']
   for d in r.get('days',[]):
    if d['date'][:10] not in dates:continue
    for app in d.get('apps',[]):
     for n in app.get('nms',[]):
      v=out.setdefault((cid,n['nmId']),dict(spend=0,amount=0,orders=0,clicks=0))
      for k,x in metric(n).items():v[k]+=x
  return out
 dates=[str(w.now.astimezone(MSK).date()-timedelta(days=i)) for i in range(days,0,-1)]
 old=[r for b in historical.get('batches',{}).values() for r in b.get('stats',[])]
 today=aggregate(stats,{day});past=aggregate(old,set(dates))
 search={n['nm_id'] for c in camps if c['status']==9 and c['settings']['placements'].get('search') for n in c.get('nm_settings',[])}
 rows=[]
 for c in camps:
  if c['status']!=9:continue
  for n in c.get('nm_settings',[]):
   nm=n['nm_id'];a=today.get((c['id'],nm));b=past.get((c['id'],nm));orders=(a or {}).get('orders',0)+(b or {}).get('orders',0)
   if orders==0:continue
   placement='search' if c['settings']['placements'].get('search') else 'recommendations'
   if kind=='add' and (placement!='recommendations' or nm in search):continue
   rows.append(dict(nm_id=nm,article=labels.get(nm,'WB '+str(nm)),campaign_id=c['id'],placement=placement,current_minor=n.get('bids_kopecks',{}).get(placement),today=a,today_drr=rate(a) if a else None,previous_full_days=b,previous_drr=rate(b) if b else None,already_in_search=nm in search,economics_confirmed=False,execution_ready=False))
 rows.sort(key=lambda r:((r['today'] or {}).get('orders',0),(r['previous_full_days'] or {}).get('orders',0)),reverse=True)
 return dict(status='diagnostic',available=True,cached=True,observed_at=observed,period_from=dates[0],period_to=dates[-1],today=day,rows=rows[:40],total_candidates=len(rows),truncated=len(rows)>40,wb_reads=0,wb_writes=0,memory_used=True,requires_confirmation=True,execution_ready=False,limitations=['Это предварительный отбор по сохранённой статистике, не готовый план исполнения.','Текущий минимум/шаг и полная экономика перед запуском ещё проверяются.','Ставку нельзя умножать на5/ДРР и обещать пропорциональный рост заказов.','Учитывать историю изменений и исключений, собственный завершённый выкуп и все расходы.','История и текущий день имеют разные даты срезов; рекламная атрибуция не равна уникальным WBзаказам/прибыли.'])
