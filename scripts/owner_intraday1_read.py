"""Owner-requested dated read-only review. Immutable private inputs, no delivery."""
import copy,json,requests,time
from datetime import datetime,date,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import reading,allowed_read
from china_advertising_state import AdvertisingIO
from china_advertising_v2 import refresh_budget_context
from china_moysklad_read import read_stock
ROOT='china_agent:owner_intraday_review:2026-11-01:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 c=Cache()
 if c.get(ROOT+':inputs'):return
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Expired dated reader')
 if not c.create(ROOT+':lease',dict(started_at=stamp())):return
 old=c.get('china_agent:owner_report_review:2026-11-01:v2:inputs')
 if not old or old.get('status')!='complete':raise ValueError('Completed own economics required')
 w=WB();validate_identity(c,w);original=requests.sessions.Session.request
 state=dict(status='collecting',cabinet='token_3',inputs={},errors={},observed_at=stamp(),wb_writes=0,telegram_sends=0,grants_action_permission=False)
 def save():c.put(ROOT+':checkpoint',json.loads(json.dumps(state)))
 def guard(session,method,url,**kw):
  if url.startswith(c.url) and method.upper() in ['GET','POST','PATCH']:return original(session,method,url,**kw)
  if allowed_read(method,url,kw.get('json')):return original(session,method,url,**kw)
  raise ValueError('External write blocked')
 requests.sessions.Session.request=guard
 try:
  with reading():
   io=AdvertisingIO();source=refresh_budget_context(io,copy.deepcopy(old['source']),'2026-11-01')
   state['source']=source
   inv=w.req('/adv/v1/promotion/count');state['inventory']=inv
   ids=sorted(set(source['ids'])|{x['advertId'] for g in inv.get('adverts',[]) if g['status'] in [4,7,9,11] for x in g.get('advert_list',[])})
   if len(ids)>50:raise ValueError('Campaign scope exceeds bounded reader')
   campaigns=w.campaigns(ids);state['inputs']['campaigns']=dict(rows=list(campaigns.values()),observed_at=stamp());save()
   stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-11-01&endDate=2026-11-01')
   if not isinstance(stats,list):raise ValueError('Statistics shape')
   state['today']=dict(rows=stats,day='2026-11-01',observed_at=stamp(),requested_ids=ids,missing_ids=sorted(set(ids)-{r['advertId'] for r in stats}));save()
   nms=sorted({n['nm_id'] for cp in campaigns.values() if cp['status']==9 for n in cp['nm_settings']})
   raw=io.prices(nms);prices=[];sizes=[]
   for nm in nms:
    p=raw[str(nm)];values={s.get('discountedPrice') for s in p.get('sizes',[])}
    if p.get('currencyIsoCode4217')!='CNY' or len(values)!=1:raise ValueError('Selected price currency or variants')
    price=next(iter(values))
    if type(price) not in (int,float) or price<=0:raise ValueError('Selected price missing')
    prices.append(dict(nm_id=nm,article=p['vendorCode'],currency='CNY',seller_price=price))
    sizes.extend(dict(nm_id=nm,size_id=s['sizeID']) for s in p['sizes'])
   state['inputs']['prices']=dict(rows=prices,observed_at=stamp(),missing_ids=[]);save()
   state['inputs']['stock']=read_stock(sorted({p['article'] for p in prices}));save()
   state['inputs']['products']=old['inputs']['products'];state['inputs']['fx']=old['inputs']['fx']
   rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':w.token},json={'chrtIds':[s['size_id'] for s in sizes]},timeout=50);rr.raise_for_status()
   state['published_stock']=dict(rows=rr.json()['stocks'],sizes=sizes,observed_at=stamp());save()
   state['minimums']={}
   for cp in campaigns.values():
    if cp['status']!=9 or cp['settings'].get('payment_type')!='cpc':continue
    for zone,on in cp['settings']['placements'].items():
     if on and zone in ['search','recommendations']:
      state['minimums'][str(cp['id'])+':'+zone]=w.minimums(cp['id'],[n['nm_id'] for n in cp['nm_settings']],zone)
    save()
   state['minimums_at']=stamp()
   state['inputs']['budgets']=dict(w.req('/api/advert/v2/budget','POST',dict(advertIds=ids)),observed_at=stamp());save()
  state.update(status='complete',completed_at=stamp())
  state=json.loads(json.dumps(state))
  if not c.create(ROOT+':inputs',state) or c.get(ROOT+':inputs')!=state:raise ValueError('Private readback mismatch')
  print(json.dumps(dict(status=state['status'],campaigns=len(campaigns),stats=len(stats),missing_ids=state['today']['missing_ids'],wb_writes=0,telegram_sends=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

