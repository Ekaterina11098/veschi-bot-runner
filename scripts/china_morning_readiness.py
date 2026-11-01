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
 ids=sorted({r['nm'] for c in rough.get('campaigns',[]) for r in c.get('focus',[]) if not r.get('pending_first_day') and not r.get('done','').startswith('Исключён')},key=lambda nm:-max((r.get('period') or {}).get('spend',0) for c in rough['campaigns'] for r in c.get('focus',[]) if r['nm']==nm))[:30]
 if not ids:return source
 if not all(os.environ.get(k) for k in ['WB_TOKEN_3','MPSTATS_API_TOKEN','MOYSKLAD_API_TOKEN']):
  source['morning_fresh_inputs']=dict(errors={'configuration':'Read credentials not configured'},wb_writes=0);return source
 from china_analytic_dialog import Analyst,reading
 from china_intraday_analysis import rate
 from china_expected_order_profit import buyout_from_product
 last=date.fromisoformat(report_day)-timedelta(days=1);first=last-timedelta(days=29)
 class Work:
  now=datetime.now(timezone.utc)
  def get(self,k):return io.get(k)
  def save(self,k,v,**kw):return io.put(k,v)
  def db(self,method,table,params=None):
   if method!='GET' or table!='analytics_snapshots':raise ValueError('Morning context allows only analytics snapshot reads')
   return io.db(table+'?'+urlencode(params or {}))
  def catalog(self):return [(str(r['nmID']),r['vendorCode']) for r in source['catalogue']['rows']]
 w=Work();an=Analyst(w,dict(request_text='Проверить экономику утренних рекламных кандидатов'),[])
 values={};errors={}
 with reading():
  for topic in ['products','prices','stock']:
   # A paginated price list avoids up to30 per-SKU requests and rate-limit failures.
   try:values[topic]=an.live(topic,[] if topic=='prices' else ids,str(first),str(last))
   except Exception as ex:errors[topic]=type(ex).__name__
  try:fx=float(rate(w,last)['rub_per_cny'])
  except Exception as ex:fx=None;errors['fx']=type(ex).__name__
 source['morning_fresh_inputs']=dict(selected_nm_ids=ids,source_times={k:v.get('observed_at') for k,v in values.items()},errors=errors,own_period=[str(first),str(last)],wb_writes=0)
 if errors:return source
 own={int(p['nm_id']):p for p in values['products'].get('rows',[])};prices={int(p['nm_id']):p for p in values['prices'].get('rows',[])};stock={p['article'].casefold():p for p in values['stock'].get('rows',[])}
 policy=io.get('china_agent:new_ad_economics_policy:v1') or {};model=io.get('china_agent:expected_profit_delivery_model:v1') or {}
 rows=source.setdefault('economics',{}).setdefault('rows',{})
 for nm in ids:
  try:
   p=own[nm];pr=prices[nm];st=stock[pr['article'].casefold()];b=buyout_from_product(p)
   if b['source']=='fallback':continue
   log=policy.get('logistics_by_nm',{}).get(str(nm)) or model.get('rows',{}).get(pr['article']) or {};q=float(b['probability'])
   price=pr['seller_price'];cost=st['cost_rub']/fx;fee=p.get('total_commission_without_spp_in_sales')
   if type(fee) not in (int,float) or not 0<=fee<100:continue
   pre=q*(price*(1-(fee+policy['tax_pct'])/100)-cost)-log['delivery_cny']-policy['handling_rub']/fx
   old=rows.get(str(nm)) or {}
   rows[str(nm)]=dict(old,observed_at=values['products']['observed_at'],own_cogs_rub=st['cost_rub'],seller_revenue_rub=price*fx,stock_free=st['available'],stock_observed_at=values['stock']['observed_at'],seller_price_cny=price,expected_margin_before_ads_cny=pre,sample_reliable=b['sample_size']>=20,sample_size=b['sample_size'],buyout=q,owner_strategy_review=True,source_ids=[values[k].get('source_key',k) for k in values],unknown_reverse_and_shared_costs=True,period_from=str(first),period_to=str(last))
  except (KeyError,TypeError,ValueError,ZeroDivisionError):continue
 return source

