"""Reject collapsed daily WB counters, keep failed reads, allow next scheduled refresh."""
import copy,hashlib,json,os
from urllib.parse import urlencode
from datetime import datetime,timezone,timedelta,date
ROOT='china_agent:morning_readiness:v1:'
class PendingAdvertisingDay(ValueError):pass

def totals(stats,day):
 out={}
 for c in stats:
  for d in c.get('days',[]):
   if d.get('date','')[:10]!=day:continue
   key=c['advertId']
   if key in out:raise ValueError('Duplicate campaign/day')
   out[key]={k:d.get(f) for k,f in [('spend','sum'),('views','views'),('clicks','clicks')]}
 return out

def references(io,day):
 out=[]
 # Immutable earlier same-day owner snapshot: use only advertising, never order money.
 p=io.get('china_agent:owner_profit_now:'+day+':v1:collection') or {}
 ad=p.get('inputs',{}).get('advertising') or {}
 if p.get('cabinet')=='token_3' and isinstance(ad.get('rows'),list):out.append(('owner_profit_now:'+day,ad['rows']))
 pointer=io.get('china_agent:hourly_sales_api:v1:latest') or {}
 if pointer.get('source_key'):
  p=io.get(pointer['source_key']) or {};ad=p.get('advertising') or {}
  if p.get('cabinet')=='token_3' and isinstance(ad.get('stats'),list):out.append((pointer['source_key'],ad['stats']))
 return out

def assess(source,day,known):
 measured=totals([c for b in source.get('batches',{}).values() for c in b.get('stats',[])],day)
 floor={};refs=[]
 for key,stats in known:
  refs.append(key)
  for cid,r in totals(stats,day).items():
   if type(r['spend']) in (int,float) and r['spend']>floor.get(cid,0):floor[cid]=r['spend']
 requested=set(source.get('ids',[]));bad=[]
 for cid,spent in floor.items():
  if cid not in requested or spent<=0:continue
  r=measured.get(cid)
  if r is None or r['spend'] is None or r['spend']==0 and r.get('views')==0 and r.get('clicks')==0:bad.append(cid)
 return dict(usable=not bad,day_msk=day,regressed_campaigns=sorted(bad),reference_keys=refs,wb_writes=0)

def ensure(io,source,report_day,source_key):
 day=(date.fromisoformat(report_day)-timedelta(days=1)).isoformat();quality=assess(source,day,references(io,day))
 if quality['usable']:source['day_quality']=quality;return quality
 raw={k:copy.deepcopy(v.get('stats')) for k,v in source.get('batches',{}).items() if 'stats' in v}
 identity=hashlib.sha256(json.dumps(raw,sort_keys=True,default=str).encode()).hexdigest()[:24]
 key=ROOT+report_day+':rejected:'+identity
 if io.get(key) is None:
  value=dict(status='rejected_incomplete_day',quality=quality,stats=raw,observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0)
  if not io.create(key,value) and io.get(key)!=value:raise ValueError('Rejected snapshot readback mismatch')
 source['status']='waiting_correct_daily_stats';source['day_quality']=quality
 for b in source.get('batches',{}).values():b.pop('stats',None)
 io.put(source_key,source)
 # The next existing scheduled prepare reads only missing stats. It never freezes zero data.
 raise PendingAdvertisingDay('WB daily counters collapsed vs earlier positive same-day slice; next scheduled prepare must refresh stats')

def enrich_economics(io,source,rough,report_day):
 """At most30 actual candidates; fresh own inputs, no marketplace writes."""
 ids=sorted({r['nm'] for c in rough.get('campaigns',[]) for r in c.get('focus',[]) if not r.get('pending_first_day') and not r.get('done','').startswith('Исключён')})
 if len(ids)>100:raise ValueError('Economic review exceeds bounded candidate scope')
 if not all(os.environ.get(k) for k in ['WB_TOKEN_3','MPSTATS_API_TOKEN','MOYSKLAD_API_TOKEN']):
  source['morning_fresh_inputs']=dict(errors={'configuration':'Read credentials not configured'},wb_writes=0);return source
 from china_analytic_dialog import Analyst,reading
 from china_intraday_analysis import rate
 from china_expected_order_profit import buyout_from_product
 last=date.fromisoformat(report_day)-timedelta(days=1);first=last-timedelta(days=29)
 class Work:
  now=datetime.now(timezone.utc)
  def get(self,k):return io.get(k)
  def save(self,k,v,**kw):
   from china_advertising_v2 import save
   return save(io,k,v)
  def db(self,method,table,params=None):
   if method!='GET' or table!='analytics_snapshots':raise ValueError('Morning context allows only analytics snapshot reads')
   return io.db(table+'?'+urlencode(params or {}))
  def catalog(self):return [(str(r['nmID']),r['vendorCode']) for r in source['catalogue']['rows']]
 w=Work();an=Analyst(w,dict(request_text='Проверить экономику утренних рекламных кандидатов'),[])
 values={};errors={}
 with reading():
  for topic in ['products','prices','stock']:
   try:
    if topic=='prices':values[topic]=current_prices(io,ids)
    elif topic=='products':
     values[topic]=an.live(topic,[],str(first),str(last))
     from china_advertising_directions import addition_shortlist
     new=addition_shortlist(dict(source,period_to=str(last)),values[topic])
     source['addition_candidate_ids']=new
     subjects={int(r['nm_id']):r.get('subject_id') for r in values[topic].get('rows',[])}
     source['addition_targets']={}
     for nm in new:
      targets=[cp['id'] for batch in source['batches'].values() for cp in batch['campaigns'].get('adverts',[]) if cp['status']==9 and cp['settings']['payment_type']=='cpc' and cp['settings']['placements'].get('recommendations') and {n['subject']['id'] for n in cp['nm_settings']}=={subjects.get(nm)}]
      if targets:source['addition_targets'][str(nm)]=min(targets)
     ids=sorted(set(ids)|set(new))
     if len(ids)>112:raise ValueError('Candidate economics scope exceeds bound')
    else:values[topic]=dict(an.collect(topic,ids,first,last),observed_at=datetime.now(timezone.utc).isoformat())
   except Exception as ex:errors[topic]=type(ex).__name__
  try:fx=float(rate(w,date.fromisoformat(report_day) if (io.get('china_agent:analysis_backend:v1')or{}).get('require_published_stock') else last)['rub_per_cny'])
  except Exception as ex:fx=None;errors['fx']=type(ex).__name__
 source['morning_fresh_inputs']=dict(selected_nm_ids=ids,source_times={k:v.get('observed_at') for k,v in values.items()},errors=errors,own_period=[str(first),str(last)],wb_writes=0)
 if errors:return source
 from china_advertising_economic_review import model_rows
 values['products'].update(period_from=str(first),period_to=str(last));values['fx']=dict(rub_per_cny=fx,date=report_day)
 policy=io.get('china_agent:new_ad_economics_policy:v1') or {};model=io.get('china_agent:expected_profit_delivery_model:v1') or {}
 source['economics']=model_rows(values,policy,model)
 if (io.get('china_agent:analysis_backend:v1')or{}).get('require_published_stock'):
  try:
   pub=published_stock(io,values['prices'],ids)
   source['morning_fresh_inputs']['published_stock_observed_at']=pub['observed_at']
   source['morning_fresh_inputs']['published_stock_missing_nm_ids']=pub['missing_nm_ids']
   for nm,e in source['economics'].get('rows',{}).items():
    e.update(published_stock=pub['amounts'].get(str(nm)),published_stock_observed_at=pub['observed_at'],fx_rub_per_cny=fx,fx_date=report_day)
  except Exception as ex:
   source['morning_fresh_inputs']['errors']['published_stock']=type(ex).__name__
 source['addition_scan']=dict(status='complete',period_from=str(first),period_to=str(last),observed_at=values['products']['observed_at'],candidate_ids=source.get('addition_candidate_ids',[]),catalogue_count=len(source['catalogue']['rows']))
 return source

def current_prices(io,ids):
 wanted=set(ids);found={}
 for offset in range(0,20000,1000):
  part=io.wb('/api/v2/list/goods/filter?limit=1000&offset='+str(offset)).get('listGoods')
  if not isinstance(part,list):raise ValueError('Price pagination incomplete')
  for p in part:
   if p.get('nmID') not in wanted:continue
   nm=p['nmID'];prices={r.get('discountedPrice') for r in p.get('sizes',[])}
   if nm in found or p.get('currencyIsoCode4217')!='CNY' or len(prices)!=1:raise ValueError('Exact seller price ambiguous')
   price=next(iter(prices))
   if type(price) not in (int,float) or price<=0:raise ValueError('Exact seller price missing')
   found[nm]=dict(nm_id=nm,article=p['vendorCode'],currency='CNY',seller_price=price,size_ids=[x['sizeID']for x in p.get('sizes',[])if type(x.get('sizeID'))is int])
  if len(part)<1000:break
 else:raise ValueError('Price page limit exceeded')
 if set(found)!=wanted:raise ValueError('Exact candidate price coverage missing')
 return dict(rows=list(found.values()),observed_at=datetime.now(timezone.utc).isoformat(),source='WB current exact candidate seller prices CNY')




def published_stock(io,prices,ids):
 """One bounded, read-only published-stock request for exact current price size IDs."""
 import requests
 if not ids:return dict(observed_at=datetime.now(timezone.utc).isoformat(),amounts={},missing_nm_ids=[])
 mapping={size:r['nm_id']for r in prices['rows']for size in r.get('size_ids',[])}
 if not mapping or len(mapping)>1000:raise ValueError('Published-stock size scope incomplete')
 r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':io.token},json={'chrtIds':sorted(mapping)},timeout=45)
 if not r.ok:raise RuntimeError('Published-stock read HTTP '+str(r.status_code))
 rows=r.json().get('stocks')
 if not isinstance(rows,list):raise ValueError('Published-stock response missing')
 seen=set();amounts={}
 for x in rows:
  size=x.get('chrtId')
  if size not in mapping or size in seen or type(x.get('amount'))is not int:raise ValueError('Published-stock identity or amount ambiguous')
  seen.add(size);nm=str(mapping[size]);amounts[nm]=amounts.get(nm,0)+x['amount']
 missing={str(n)for n in ids}-{str(mapping[s])for s in seen}
 for size in set(mapping)-seen:
  nm=str(mapping[size]);missing.add(nm);amounts.pop(nm,None)
 return dict(observed_at=datetime.now(timezone.utc).isoformat(),amounts=amounts,missing_nm_ids=sorted(missing))
