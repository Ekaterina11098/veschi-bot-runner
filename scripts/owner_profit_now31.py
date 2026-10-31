"""One owner-requested expected profit snapshot. WB reads only, no Telegram."""
import copy,json,os,time,collections,xml.etree.ElementTree as ET
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import requests
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import Analyst,reading,allowed_read
from china_moysklad_read import read_stock
from china_expected_order_profit import buyout_from_product
ROOT='china_agent:owner_profit_now:2026-10-31:v1'
MSK=ZoneInfo('Europe/Moscow')
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 c=Cache()
 if c.get(ROOT):return
 w=WB();validate_identity(c,w)
 now=datetime.now(timezone.utc);today=now.astimezone(MSK).date()
 if today.isoformat()!='2026-10-31':raise ValueError('Owner request date expired')
 state=dict(status='collecting',observed_at=stamp(),cabinet='token_3',wb_writes=0,telegram_sends=0,errors={},inputs={},grants_action_permission=False)
 if not c.create(ROOT+':collection',state):raise ValueError('Prior collection exists; do not blindly repeat')
 def save():c.put(ROOT+':collection',copy.deepcopy(state))
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  from urllib.parse import urlparse
  u=urlparse(url);m=method.upper()
  if url.startswith(c.url):
   body=kw.get('json') or {}
   if m=='GET' or m in ['POST','PATCH'] and str(body.get('cache_key',ROOT)).startswith(ROOT):return original(session,method,url,**kw)
  if m=='GET' and u.hostname=='www.cbr.ru' and u.path=='/scripts/XML_daily.asp':return original(session,method,url,**kw)
  if m=='POST' and u.hostname=='marketplace-api.wildberries.ru' and u.path=='/api/v3/orders/status' and set(kw.get('json')or{})=={'orders'}:return original(session,method,url,**kw)
  if allowed_read(m,url,kw.get('json')):return original(session,method,url,**kw)
  raise ValueError('Non-read endpoint blocked')
 requests.sessions.Session.request=guard
 try:
  cutoff=datetime.now(timezone.utc);start=datetime.combine(today,datetime.min.time(),MSK);orders={};cursor=0
  with reading():
   for page in range(40):
    r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',params={'limit':1000,'next':cursor,'dateFrom':int(start.timestamp()),'dateTo':int(cutoff.timestamp())},headers={'Authorization':w.token},timeout=55);r.raise_for_status();j=r.json();part=j.get('orders')
    if not isinstance(part,list):raise ValueError('Orders array absent')
    for x in part:
     at=datetime.fromisoformat(x['createdAt'].replace('Z','+00:00')).astimezone(MSK)
     if at.date()!=today:raise ValueError('Unexpected order creation date')
     projected={k:x.get(k) for k in ['id','nmId','article','createdAt','price','currencyCode','convertedPrice','convertedCurrencyCode']}
     if x['id'] in orders and orders[x['id']]!=projected:raise ValueError('Conflicting order ID')
     orders[x['id']]=projected
    nxt=j.get('next')
    if not part or not nxt:break
    if nxt==cursor:raise ValueError('Order pagination stuck')
    cursor=nxt;time.sleep(1)
   else:raise ValueError('Orders pagination incomplete')
   state['inputs']['orders']=dict(rows=list(orders.values()),complete=True,observed_at=stamp(),cutoff_msk=cutoff.astimezone(MSK).isoformat())
   save()
   try:
    rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/orders/status',json={'orders':list(orders)},headers={'Authorization':w.token},timeout=55);rr.raise_for_status();statuses=rr.json()['orders']
    if {r['id'] for r in statuses}!=set(orders):raise ValueError('Order status coverage incomplete')
    state['inputs']['statuses']=dict(rows=statuses,complete=True,observed_at=stamp())
   except Exception as ex:state['errors']['statuses']=type(ex).__name__
   rr=requests.get('https://www.cbr.ru/scripts/XML_daily.asp',params={'date_req':'31/10/2026'},timeout=45);rr.raise_for_status();xml=ET.fromstring(rr.content)
   if xml.attrib.get('Date')!='31.10.2026':raise ValueError('CBR effective date mismatch')
   val=next(v for v in xml.findall('Valute') if v.findtext('CharCode')=='CNY')
   fx=float(val.findtext('Value').replace(',','.'))/int(val.findtext('Nominal'))
   state['inputs']['fx']=dict(rub_per_cny=fx,effective_date='2026-10-31',source='CBR XML_daily',observed_at=stamp())
   class Work:
    now=datetime.now(timezone.utc)
    def get(self,key):return c.get(key)
    def save(self,key,v):raise ValueError('Collector cannot write production analytic cache')
    def catalog(self):return [(str(p['nmID']),p['vendorCode']) for p in (c.get('china_agent:prices:v1')or{}).get('rows',[])]
   an=Analyst(Work(),dict(request_text='Предварительная прибыль сегодня'),[])
   first=today-timedelta(days=30);last=today-timedelta(days=1)
   own=an.collect('products',[],first,last)
   state['inputs']['own_products']=dict(own,observed_at=stamp(),period_from=str(first),period_to=str(last));save()
   prices=an.collect('prices',[],first,last)
   state['inputs']['prices']=dict(prices,observed_at=stamp());save()
   articles=sorted({x['article'] for x in orders.values()})
   state['inputs']['stock']=read_stock(articles);save()
   cfg=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=45);cfg.raise_for_status()
   if cfg.json().get('currency')!='CNY':raise ValueError('Advertising currency unknown')
   inv=w.req('/adv/v1/promotion/count');catalogue=sorted({r['advertId'] for g in inv.get('adverts',[]) for r in g.get('advert_list',[])})
   if not catalogue or len(catalogue)>1000:raise ValueError('Invalid advertising coverage')
   stats=[]
   for offset in range(0,len(catalogue),50):
    part=w.req('/adv/v3/fullstats?ids='+','.join(map(str,catalogue[offset:offset+50]))+'&beginDate='+str(today)+'&endDate='+str(today))
    if not isinstance(part,list):raise ValueError('Advertising stats incomplete')
    stats+=part
   returned={r['advertId'] for r in stats};missing=sorted(set(catalogue)-returned)
   state['inputs']['advertising']=dict(rows=stats,observed_at=stamp(),catalogue=catalogue,missing_campaign_ids=missing,all_statuses_included=True);save()
  state.update(status='complete' if not state['errors'] else 'partial',completed_at=stamp());save()
 except Exception as ex:
  state.update(status='failed',error=type(ex).__name__,completed_at=stamp());save();raise
 finally:requests.sessions.Session.request=original
 policy=c.get('china_agent:new_ad_economics_policy:v1') or {};delivery=c.get('china_agent:expected_profit_delivery_model:v1') or {}
 own={int(p['nm_id']):p for p in state['inputs']['own_products']['rows']}
 prices={int(p['nm_id']):p for p in state['inputs']['prices']['rows']}
 costs={p['article'].casefold():p for p in state['inputs']['stock']['rows']}
 status={s['id']:s for s in state['inputs'].get('statuses',{}).get('rows',[])}
 fallback=collections.Counter();missing=[];tot=collections.defaultdict(float);details=[]
 for o in orders.values():
  nm=o['nmId'];article=o['article'];p=own.get(nm);pr=prices.get(nm);st=costs.get(article.casefold(),{})
  try:
   probability=buyout_from_product(p);q=float(probability['probability'])
   if probability['source']=='fallback':fallback['buyout50_orders']+=1
   if probability['sample_size']<20:fallback['small_completed_sample_orders']+=1
   s=status.get(o['id'],{});cancelled=s.get('supplierStatus')=='cancel' or s.get('wbStatus') in ['canceled','canceled_by_client','declined']
   if cancelled:q=0
   if not pr or pr.get('currency')!='CNY' or pr.get('article','').casefold()!=article.casefold():raise ValueError('Seller price unknown')
   price=pr['seller_price'];cost=st.get('price')
   if not isinstance(cost,(int,float)) or cost<=0:
    cost=p.get('cost_price')
    if not isinstance(cost,(int,float)) or cost<=0:raise ValueError('Own COGS missing')
    fallback['cogs_own_mpstats_orders']+=1
   else:cost=cost/100
   fee=p.get('total_commission_without_spp_in_sales')
   if not isinstance(fee,(int,float)) or not 0<fee<100:fee=policy['commission_pct'];fallback['commission_policy_orders']+=1
   log=policy.get('logistics_by_nm',{}).get(str(nm))
   if not log:
    log=delivery.get('rows',{}).get(article)
    fallback['delivery_model_orders']+=1
   if not log or not isinstance(log.get('delivery_cny'),(int,float)):raise ValueError('Delivery model missing')
   z=dict(orders=1,cancelled_orders=int(cancelled),model_seller_amount_cny=price,expected_buyouts=q,expected_seller_revenue_cny=q*price,cogs_cny=q*cost/fx,commission_cny=q*price*fee/100,tax_cny=q*price*policy['tax_pct']/100,logistics_cny=log['delivery_cny'],handling_cny=policy['handling_rub']/fx)
   z['pre_ad_profit_cny']=z['expected_seller_revenue_cny']-sum(z[k] for k in ['cogs_cny','commission_cny','tax_cny','logistics_cny','handling_cny'])
   for k,v in z.items():tot[k]+=v
   details.append(dict(nm_id=nm,article=article,own_completed=probability['sample_size'],buyout=q,**z))
  except (ValueError,KeyError,TypeError) as ex:missing.append(dict(nm_id=nm,article=article,error=str(ex) if isinstance(ex,ValueError) else type(ex).__name__))
 spend=0;seen=set()
 for cp in stats:
  if cp.get('currency')!='CNY':raise ValueError('Ad stats currency mismatch')
  for d in cp.get('days',[]):
   if d.get('date','')[:10]!=str(today):continue
   key=(cp['advertId'],d['date'][:10])
   if key in seen or not isinstance(d.get('sum'),(int,float)) or d['sum']<0:raise ValueError('Ad cost duplicate/missing')
   seen.add(key);spend+=d['sum']
 tot['advertising_cny']=spend;tot['forecast_profit_cny']=tot['pre_ad_profit_cny']-spend;tot['forecast_profit_rub']=tot['forecast_profit_cny']*fx
 result=dict(status='complete_model' if not missing and not state['errors'] and not state['inputs']['advertising']['missing_campaign_ids'] else 'partial_model',cabinet='token_3',cutoff_msk=state['inputs']['orders']['cutoff_msk'],inputs_source=ROOT+':collection',fx=state['inputs']['fx'],created_orders=len(orders),modelled_orders=len(details),totals=dict(tot),unmodelled=missing,fallbacks=dict(fallback),source_times={k:v.get('observed_at') for k,v in state['inputs'].items()},errors=state['errors'],missing_ad_campaigns=state['inputs']['advertising']['missing_campaign_ids'],details=details,assumptions=['Expected profit of today-created FBS order cohort, not settled net profit or proven whole cabinet','Current seller CNY prices are proxy for seller price at order time; buyer convertedPrice not revenue','Own prior30completed-day buyout;50% only with no finished sample;true0% retained','Own historical fee, policy20%if missing; tax5%,handling10RUB/order assumptions','Historical logistics reserved for every created order incl cancelled; reverse/shared costs unknown','Whole campaign ad spending incl closed campaigns deducted once; no budget top-ups deducted'],wb_writes=0,telegram_sends=0,grants_action_permission=False,completed_at=stamp())
 if not c.create(ROOT,result) or c.get(ROOT)!=result:raise ValueError('Private model readback mismatch')
 print(json.dumps({k:result[k] for k in ['status','created_orders','modelled_orders','fallbacks','wb_writes','telegram_sends']}))
if __name__=='__main__':main()
