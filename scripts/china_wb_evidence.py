"""Official China WB report reads. No marketplace mutations, no Telegram transport."""
import base64,hashlib,json,os,math
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from urllib.parse import urlparse
ROOT='china_agent:wb_evidence:v1:'
FUNNEL='https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products'
FINANCE='https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed'
SALE={'销售','Продажа','Sale'}
RETURN={'退货','Возврат','Return'}
DELIVERY={'配送','Логистика','Доставка','Delivery'}
DEDUCTION={'扣款','Удержание','Удержания','Deduction'}

def now():return datetime.now(timezone.utc)
def jwt(token):
 try:return json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
 except Exception:return {}
def money(value):
 if value is None or isinstance(value,bool):raise ValueError('Missing monetary field')
 try:d=Decimal(str(value))
 except InvalidOperation:raise ValueError('Invalid monetary field') from None
 if not d.is_finite():raise ValueError('Nonfinite monetary field')
 return d
def dates(first,last):
 a,b=date.fromisoformat(first),date.fromisoformat(last)
 if not 0<=(b-a).days<=30 or b>now().astimezone(timezone(timedelta(hours=3))).date():raise ValueError('WB evidence needs exact dates, maximum31 days')
 return a,b
def digest(body):return hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()[:24]
def allowed_read(method,url,body):
 return method.upper()=='POST' and url in (FUNNEL,FINANCE) and isinstance(body,dict) and ('selectedPeriod' in body if url==FUNNEL else {'dateFrom','dateTo','rrdId','period'}<=set(body))

class Reports:
 def __init__(self,w,send=None):self.w=w;self.send=send
 def request(self,url,body):
  if not allowed_read('POST',url,body):raise PermissionError('Only official report reads')
  general=os.environ['WB_TOKEN_3'];token=(os.environ.get('WB_FINANCE_TOKEN_3') or general) if url==FINANCE else general
  a,b=jwt(general),jwt(token)
  if not a.get('sid') or a.get('sid')!=b.get('sid'):raise ValueError('China seller identity unverified')
  interval=(43201 if url==FINANCE else 1801) if b.get('acc')==1 else (61 if url==FINANCE else 21)
  service='finance' if url==FINANCE else 'funnel';key=ROOT+'rate:'+service;clock=now();old=self.w.get(key) or {}
  retry=old.get('retry_at')
  if retry and datetime.fromisoformat(retry)>clock:return dict(available=False,status='cooldown',retry_at=retry)
  slot=ROOT+'rate_claim:'+service+':'+str(int(clock.timestamp())//interval)
  claim=self.w.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body=dict(cache_key=slot,payload={'started_at':clock.isoformat()},expires_at=(clock+timedelta(days=1)).isoformat()),prefer='resolution=ignore-duplicates,return=representation')
  if not claim:return dict(available=False,status='rate_claimed',retry_at=(clock+timedelta(seconds=interval)).isoformat())
  self.w.save(key,dict(retry_at=(clock+timedelta(seconds=interval)).isoformat()))
  send=self.send
  if send is None:
   import requests
   send=requests.post
  response=send(url,headers={'Authorization':token},json=body,timeout=90,allow_redirects=False)
  result=dict(status_code=response.status_code,available=response.status_code in (200,204),observed_at=clock.isoformat())
  if response.status_code==204:result['data']=[]
  elif response.status_code==200:result['data']=response.json()
  else:
   result['status']='WB_HTTP_'+str(response.status_code)
   if response.status_code==429:
    try:delay=max(interval,int(response.headers.get('Retry-After',interval)))
    except (ValueError,TypeError):delay=interval
    self.w.save(key,dict(retry_at=(clock+timedelta(seconds=delay)).isoformat()))
   # Never pass arbitrary upstream response text/identifiers into public logs/model.
  return result
 def funnel(self,first,last):
  a,b=dates(first,last);n=(b-a).days+1;past={'start':str(a-timedelta(days=n)),'end':str(a-timedelta(days=1))}
  body=dict(selectedPeriod={'start':first,'end':last},pastPeriod=past,nmIds=[],brandNames=[],subjectIds=[],tagIds=[],skipDeletedNm=False,orderBy={'field':'openCard','mode':'desc'},limit=1000,offset=0)
  key=ROOT+'funnel:'+first+':'+last;state=self.w.get(key)
  if state is None and first==last=='2026-10-22':
   probe=self.w.get('china_agent:wb_evidence_probe:v1:funnel:2026-10-23')
   if probe and probe.get('status')==200:
    raw=probe['data']['data'];rows=normalize_funnel(raw['products'],body['selectedPeriod'],past,'china_agent:wb_evidence_probe:v1:funnel:2026-10-23')
    state=dict(rows=rows,offset=len(rows),complete=len(rows)<1000,source=FUNNEL,cabinet='token_3',period_from=first,period_to=last,comparison=past,observed_at=probe['observed_at'],currency='CNY',source_key=key,total_impressions_available=False,update_delay_hours=2)
    self.w.save(key,state)
  if state and state.get('complete') and (now()-datetime.fromisoformat(state['observed_at'])).total_seconds()<7200:return state
  state=state if state and not state.get('complete') else dict(rows=[],offset=0,source=FUNNEL,cabinet='token_3',period_from=first,period_to=last,comparison=past)
  body['offset']=state['offset'];response=self.request(FUNNEL,body)
  if not response['available']:return dict(response,rows=state['rows'],source_key=key,complete=False)
  raw=response.get('data',{});data=raw.get('data',{});products=data.get('products')
  if not isinstance(products,list) or data.get('currency','').upper()!='CNY':raise ValueError('WB funnel shape/currency')
  raw_key=ROOT+'raw:funnel:'+digest(body)+':'+response['observed_at'];self.w.save(raw_key,dict(request=body,response=raw))
  rows=normalize_funnel(products,body['selectedPeriod'],past,raw_key)
  if {r['nm_id'] for r in state['rows']}&{r['nm_id'] for r in rows}:raise ValueError('WB pagination duplicates')
  state['rows']+=rows;state.update(offset=state['offset']+len(products),complete=len(products)<1000,observed_at=response['observed_at'],source_key=key,currency='CNY',update_delay_hours=2,
   total_impressions_available=False,missing='WB API products/CSV schema has no total impressions; do not use openCount or ad views as impressions',wb_writes=0)
  self.w.save(key,state);return state
 def finance(self,first,last):
  dates(first,last);key=ROOT+'finance:'+first+':'+last;state=self.w.get(key)
  pointer=self.w.get(ROOT+'finance_latest') or {};cover=self.w.get(pointer['source_key']) if pointer.get('source_key') else None
  if cover and cover.get('complete') and cover['period_from']<=first<=last<=cover['period_to'] and (now()-datetime.fromisoformat(cover['observed_at'])).total_seconds()<21600:return cover
  if state and state.get('complete') and (now()-datetime.fromisoformat(state['observed_at'])).total_seconds()<21600:return state
  state=state if state and not state.get('complete') else dict(rows=[],rrd_id=0,source=FINANCE,cabinet='token_3',period_from=first,period_to=last,complete=False,source_keys=[])
  # Reuse the already privately collected owner-requested page, never spend another request for it.
  probe=self.w.get('china_agent:wb_evidence_probe:v1:finance:2026-10-23') if first=='2026-09-23' and last=='2026-10-22' and not state['rows'] else None
  if probe and probe.get('status')==200:
   response=dict(available=True,status_code=200,data=probe['data'],observed_at=probe['observed_at']);body=probe['request']
  else:
   body=dict(dateFrom=first,dateTo=last,period='daily',limit=100000,rrdId=state['rrd_id']);response=self.request(FINANCE,body)
  if not response['available']:return dict(state,status=response.get('status'),retry_at=response.get('retry_at'),available=False,source_key=key)
  page=response['data']
  if not isinstance(page,list):raise ValueError('Finance page shape')
  if not page and response['status_code']!=204:raise ValueError('Empty Finance200 is not a documented terminal cursor')
  raw_key=ROOT+'raw:finance:'+digest(body)+':'+response['observed_at'];self.w.save(raw_key,dict(request=body,response=page));state['source_keys'].append(raw_key)
  seen={int(r['rrdId']) for r in state['rows']}
  for row in page:
   rid=int(row['rrdId'])
   if rid in seen or rid<=state['rrd_id']:raise ValueError('Finance cursor did not advance or duplicate operation')
   if str(row.get('currency','')).upper()!='CNY':raise ValueError('China Finance currency mismatch')
   seen.add(rid)
  state['rows']+=page
  if page:state['rrd_id']=int(page[-1]['rrdId'])
  state.update(complete=response['status_code']==204,available=True,observed_at=response['observed_at'],source_key=key,currency='CNY',wb_writes=0,
   note='Only HTTP204 closes pagination. Published operation dates are not order cohort dates or proof of no future adjustments.')
  self.w.save(key,state)
  if state['complete']:self.w.save(ROOT+'finance_latest',dict(source_key=key))
  elif probe:return self.finance(first,last) # Seeded private page did not consume a new API read.
  return state

def normalize_funnel(products,selected,past,source_id):
 result=[];seen=set()
 for product in products:
  p=product['product'];nm=p['nmId']
  if type(nm) is not int or nm in seen:raise ValueError('WB funnel product identity')
  seen.add(nm);periods={}
  for name,period in [('selected',selected),('past',past)]:
   s=product['statistic'][name]
   if s['period']!=period:raise ValueError('WB funnel period mismatch')
   for field in ['openCount','cartCount','orderCount','buyoutCount','cancelCount']:
    if type(s.get(field)) is not int or s[field]<0:raise ValueError('Missing WB funnel counter')
   periods[name]=dict(period_from=period['start'],period_to=period['end'],clicks=s['openCount'],cart_count=s['cartCount'],orders=s['orderCount'],order_amount_cny=float(money(s['orderSum'])),
    buyouts=s['buyoutCount'],cancellations=s['cancelCount'],click_order_pct=100*s['orderCount']/s['openCount'] if s['openCount'] else None,total_impressions=None,organic_impressions=None,total_ctr_pct=None,
    scope='all_sources',source_id=source_id,source='WB sales funnel',update_delay_hours=2)
  result.append(dict(nm_id=nm,article=p['vendorCode'],feedback_rating=p.get('feedbackRating'),product_rating=p.get('productRating'),**periods))
 return result

def settlement(state,first,last,ids=None,costs=None,fx=12,tax_rate=.05):
 """Published settlement contribution, separate from closed cohorts and expected ad-day profit."""
 dates(first,last)
 if money(fx)<=0:raise ValueError('Invalid FX')
 costs=costs or {};selected=set(ids or []);rows=[];seen=set();currencies=set();missing=set();units={};parts={k:Decimal(0) for k in ['seller_net','delivery','rebill','storage','acceptance','penalty','deduction','additional','cogs','tax']};shared_ad=Decimal(0)
 for r in state.get('rows',[]):
  if not first<=str(r.get('rrDate',''))[:10]<=last:continue
  nm=int(r.get('nmId') or 0)
  if selected and nm not in selected:continue
  rid=int(r['rrdId'])
  if rid in seen:raise ValueError('Duplicate finance operation')
  seen.add(rid);rows.append(r);currencies.add(str(r.get('currency','')).upper());op=r.get('sellerOperName');doc=r.get('docTypeName');sign=1 if op in SALE and doc in SALE else -1 if op in RETURN and doc in RETURN else 0
  if op not in SALE|RETURN|DELIVERY|DEDUCTION:missing.add('Unclassified Finance operation '+str(op))
  try:
   forpay=money(r.get('forPay'))
   if forpay and not sign:missing.add('Unclassified nonzero seller payout')
   parts['seller_net']+=sign*forpay
   for key,field in [('delivery','deliveryService'),('rebill','rebillLogisticCost'),('storage','paidStorage'),('acceptance','paidAcceptance'),('penalty','penalty'),('deduction','deduction'),('additional','additionalPayment')]:parts[key]+=money(r.get(field))
   if sign:
    q=int(r['quantity']);units[nm]=units.get(nm,0)+sign*q
    if tax_rate is not None:parts['tax']+=sign*q*money(r.get('retailPriceWithDisc'))*money(tax_rate)
    if nm not in costs or costs[nm] is None:missing.add('Missing own COGS for nm '+str(nm))
    else:parts['cogs']+=sign*q*money(costs[nm])/money(fx)
   if 'wb promotion' in str(r.get('bonusTypeName','')).lower():shared_ad+=money(r.get('deduction'))
  except (ValueError,KeyError,TypeError):missing.add('Missing/invalid monetary inputs in Finance operation')
 if currencies and currencies!={'CNY'}:raise ValueError('Finance currencies cannot be mixed')
 if not state.get('complete'):missing.add('Finance pagination not closed by HTTP204')
 if not rows:missing.add('No published operations for requested period; not proof of zero profit')
 if selected:missing.add('Cabinet shared charges are not allocated to these SKUs')
 if tax_rate is None:missing.add('Tax calculation policy not supplied')
 missing.add('Historical COGS and external return-to-RF/other expenses not fully verified')
 cash=parts['seller_net']+parts['additional']-sum(parts[k] for k in ['delivery','rebill','storage','acceptance','penalty','deduction'])
 contribution=cash-parts['cogs']-parts['tax'];known=not any('Missing own COGS' in x or 'monetary' in x or 'Unclassified' in x for x in missing) and bool(rows) and state.get('complete') is True
 return dict(period_from=first,period_to=last,basis='published_operation_date',is_closed_order_cohort=False,is_full_net_profit=False,currency='CNY',conversion_rub_per_cny=fx,
  wb_cash_cny=round(float(cash),2) if rows else None,accounted_contribution_rub=round(float(contribution)*fx,2) if known else None,calculated_profit_rub=round(float(contribution)*fx,2) if known else None,
  tax_rate=tax_rate,tax_basis='Seller price after seller discount, before WB discount; signed sales minus returns',tax_source='Owner-approved China5% calculation policy, not tax filing',cogs_source='Own current MoySklad COGS, converted to CNY at stated FX',label='Расчётная прибыль по опубликованным операциям WB; предварительная',
  net_profit_rub=None,parts_cny={k:round(float(v),2) for k,v in parts.items()},wb_promotion_included_cny=float(shared_ad),ad_spend_subtracted_again=False,
  commission_subtracted_again=False,acquiring_subtracted_again=False,operation_count=len(rows),publication_latest=max((r.get('createDate','') for r in rows),default=None),
  operation_latest=max((r.get('rrDate','') for r in rows),default=None),source_ids=state.get('source_keys',[]),missing=sorted(missing),wb_writes=0)

def context(w,ids,first,last,costs=None):
 """Same source cache reused by free analysis and observation; unavailable is never zero."""
 reports=Reports(w);out=dict(cabinet='token_3',wb_writes=0)
 if costs is None:
  try:
   from china_analytic_dialog import Analyst
   stock=Analyst(w,{},[]).live('stock',ids,first,last);by_article={r['article'].casefold():r.get('cost_rub') for r in stock.get('rows',[])}
   costs={int(nm):by_article.get(article.casefold()) for nm,article in w.catalog()}
   out['cogs_source']={k:stock.get(k) for k in ['source','source_key','observed_at']}
  except Exception as ex:out['cogs_missing']=type(ex).__name__
 for name in ['funnel','finance']:
  try:
   state=getattr(reports,name)(first,last)
   if name=='funnel':out[name]=dict(state,rows=[r for r in state.get('rows',[]) if not ids or r['nm_id'] in ids])
   else:out[name]=settlement(state,first,last,ids,costs);out[name]['collection_status']='complete' if state.get('complete') else state.get('status','pagination_pending');out[name]['retry_at']=state.get('retry_at')
  except Exception as ex:out[name]=dict(available=False,error=type(ex).__name__,missing=str(ex)[:200] if isinstance(ex,ValueError) else 'WB transport unavailable',value=None)
 return out

def daily(w):
 """One bounded continuation in existing morning workflow/backups; no new schedule."""
 today=now().astimezone(timezone(timedelta(hours=3))).date();last=today-timedelta(days=1);first=last-timedelta(days=29)
 with __import__('china_analytic_dialog').reading():
  reports=Reports(w);finance=reports.finance(str(first),str(last));funnel=reports.funnel(str(last),str(last))
 summary=dict(observed_at=now().isoformat(),finance_complete=finance.get('complete',False),finance_status=finance.get('status'),finance_rows=len(finance.get('rows',[])),funnel_complete=funnel.get('complete',False),funnel_products=len(funnel.get('rows',[])),total_impressions_available=False,wb_writes=0,telegram_sends=0)
 w.save(ROOT+'latest_collection',summary);return summary

if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 from conversion_watches import runtime
 print(json.dumps(daily(runtime())))

