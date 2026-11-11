"""Addressed recovery of genuinely missing economics; no inferred zero rates/costs."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
IDS=[1900197978,2215883910,2216045897,2216111729,2216167898,2216217906,2216257724]
ROOT='china_agent:owner_economics_recovery:v1:'
def extend_catalog(w):
 today=datetime.now(ZoneInfo('Europe/Moscow')).date();source=w.get('china_agent:advertising_full_growth:'+str(today)+':v1:inputs')or{}
 labels={str(n):a for n,a in w.catalog()}
 if source.get('cabinet')=='token_3'and source.get('status')=='complete':
  for row in source.get('catalogue',{}).get('rows',[]):
   if type(row.get('nmID'))is int and isinstance(row.get('vendorCode'),str):labels[str(row['nmID'])]=row['vendorCode']
 merged=list(labels.items());w.catalog=lambda:merged
 return merged
def collect(w,job):
 from china_analytic_dialog import Analyst,reading
 from china_wb_evidence import Reports,FUNNEL,normalize_funnel
 today=datetime.now(ZoneInfo('Europe/Moscow')).date();last=today-timedelta(days=1);first=last-timedelta(days=29)
 key=ROOT+str(today);old=w.get(key)
 if old and old.get('status')=='checked'and(datetime.now(timezone.utc)-datetime.fromisoformat(old['observed_at'])).total_seconds()<3600:return old
 extend_catalog(w);a=Analyst(w,job,[])
 with reading():
  own=a.live('products',IDS,str(first),str(last));stock=a.live('stock',IDS,str(first),str(last));prices=a.live('prices',IDS,str(first),str(last))
  own_sources=[own]
  for days in (30,60):
   if all(any(r.get('nm_id')==nm and r.get('finished_orders',0)>0 for s in own_sources for r in s.get('rows',[]))for nm in IDS):break
   own_sources.append(a.live('products',IDS,str(first-timedelta(days=days)),str(last-timedelta(days=days))))
  past={'start':str(first-timedelta(days=30)),'end':str(first-timedelta(days=1))}
  response=Reports(w).request(FUNNEL,dict(selectedPeriod={'start':str(first),'end':str(last)},pastPeriod=past,nmIds=IDS,brandNames=[],subjectIds=[],tagIds=[],skipDeletedNm=False,orderBy={'field':'openCard','mode':'desc'},limit=1000,offset=0))
 if not response.get('available'):raise ValueError('Адресная общая воронка WB недоступна: '+str(response.get('status')))
 raw=response.get('data',{}).get('data',{})
 if raw.get('currency')!='CNY'or not isinstance(raw.get('products'),list):raise ValueError('Неверное покрытие адресной WB воронки')
 rawkey=key+':wb_raw:'+response['observed_at'];w.save(rawkey,dict(request_nm_ids=IDS,response=response['data']))
 funnel=normalize_funnel(raw['products'],{'start':str(first),'end':str(last)},past,rawkey)
 source=w.get('china_agent:advertising_full_growth:'+str(today)+':v1:inputs')or{}
 ownmap={r['nm_id']:r for r in own.get('rows',[])}
 for s in own_sources[1:]:
  for r in s.get('rows',[]):
   if r.get('finished_orders',0)>0 and not ownmap.get(r['nm_id'],{}).get('finished_orders'):ownmap[r['nm_id']]=dict(r,recovered_period_from=s['period_from'],recovered_period_to=s['period_to'])
 fm={r['nm_id']:r for r in funnel};pm={r['nm_id']:r for r in prices.get('rows',[])};sm={r['article'].casefold():r for r in stock.get('rows',[])}
 rows=[]
 for nm in IDS:
  p=pm.get(nm);o=ownmap.get(nm);f=fm.get(nm);st=sm.get((p or{}).get('article','').casefold())
  q=(source.get('economics',{}).get('rows')or{}).get(str(nm))or{}
  missing=[]
  if not p:missing.append('current_seller_price')
  if not st:missing.append('current_MSK_stock_COGS')
  if not f:missing.append('WB_funnel_exact_product')
  sample=(o or{}).get('finished_orders')
  if o is None:missing.append('own_completed_buyout_row_absent')
  elif not sample:missing.append('no_completed_own_buyout_sample')
  cost=(o or{}).get('average_delivery_cost')
  if not q.get('logistics_cny')and not cost:missing.append('no_observed_or_approved_logistics_model')
  rows.append(dict(nm_id=nm,article=(p or{}).get('article'),price=p,MSK=st,own_completed=sample,own_paid=(o or{}).get('is_payed'),own_average_delivery_rub=cost,WB_selected=(f or{}).get('selected'),unresolved=missing,not_zero_probability=not sample,not_zero_logistics=not cost))
 result=dict(status='checked',period_from=str(first-timedelta(days=60)),period_to=str(last),observed_at=datetime.now(timezone.utc).isoformat(),rows=rows,source_keys=[s.get('source_key')for s in own_sources]+[stock.get('source_key'),prices.get('source_key'),rawkey],coverage=dict(requested_nm_ids=IDS,WB_funnel_received=sorted(fm),own_rows_received=sorted(ownmap),own_missing_rows_are_not_zero=True),wb_writes=0,model_calls=0)
 w.save(key,result);return result