"""Dated owner sales-decline diagnosis; read-only current conditions and closed-day ads."""
import json,requests
from datetime import datetime,date,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_advertising_state import AdvertisingIO
from china_moysklad_read import read_stock
ROOT='china_agent:owner_sales_decline:2026-11-01:evening:v1'
def main():
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Expired')
 c=Cache()
 if c.get(ROOT+':inputs'):return
 request=c.get(ROOT+':request')
 if not request or request['cabinet']!='token_3' or not request['read_only']:raise ValueError('No scoped read request')
 nms=request['nm_ids']
 if not 1<=len(nms)<=15:raise ValueError('Diagnostic SKU bound')
 if not c.create(ROOT+':lease',dict(started_at=stamp())):return
 wb=WB();validate_identity(c,wb);original=requests.sessions.Session.request
 state=dict(status='collecting',cabinet='token_3',observed_at=stamp(),errors={},wb_writes=0,telegram_calls=0,grants_action_permission=False)
 def save():c.put(ROOT+':checkpoint',json.loads(json.dumps(state)))
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json')
  db=u.scheme=='https' and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/') and (m=='GET' or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  ads=u.scheme=='https' and u.hostname=='advert-api.wildberries.ru' and ((m=='GET'and u.path in ['/adv/v1/promotion/count','/api/advert/v2/adverts','/adv/v3/fullstats'])or(m=='POST'and u.path in ['/api/advert/v2/budget','/api/advert/v1/bids/min']))
  prices=u.scheme=='https'and u.hostname=='discounts-prices-api.wildberries.ru'and m=='GET'and u.path=='/api/v2/list/goods/filter'
  stock=u.scheme=='https'and u.hostname=='marketplace-api.wildberries.ru'and m=='POST'and u.path=='/api/v3/stocks/2126188'and isinstance(body,dict)and set(body)=={'chrtIds'}
  ms=u.scheme=='https'and u.hostname=='api.moysklad.ru'and m=='GET'and u.path in ['/api/remap/1.2/entity/store','/api/remap/1.2/entity/product','/api/remap/1.2/report/stock/all']
  if not(db or ads or prices or stock or ms):raise PermissionError('Diagnostic external write blocked')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  inv=wb.req('/adv/v1/promotion/count');ids=sorted({r['advertId']for g in inv.get('adverts',[])if g['status']in[4,7,9,11]for r in g.get('advert_list',[])})
  campaigns={}
  for offset in range(0,len(ids),50):campaigns.update(wb.campaigns(ids[offset:offset+50]))
  state.update(inventory=inv,campaigns=campaigns,campaigns_at=stamp());save()
  stats=[]
  for offset in range(0,len(ids),50):
   part=wb.req('/adv/v3/fullstats?ids='+','.join(map(str,ids[offset:offset+50]))+'&beginDate=2026-10-27&endDate=2026-11-01')
   if not isinstance(part,list):raise ValueError('Statistics unavailable')
   stats.extend(part)
  state['statistics']=dict(rows=stats,missing_ids=sorted(set(ids)-{r['advertId']for r in stats}),observed_at=stamp());save()
  active=[int(cid)for cid,cp in campaigns.items()if cp['status']in[9,11]]
  state['budgets']=dict(rows=wb.req('/api/advert/v2/budget','POST',dict(advertIds=active)),observed_at=stamp());save()
  io=AdvertisingIO();raw=io.prices(nms);prices=[];sizes=[]
  for nm in nms:
   p=raw[str(nm)]
   if p.get('currencyIsoCode4217')!='CNY':raise ValueError('Price currency')
   prices.append(p);sizes.extend(s['sizeID']for s in p['sizes'])
  state['prices']=dict(rows=prices,observed_at=stamp());save()
  try:state['stock']=read_stock([p['vendorCode']for p in prices])
  except Exception as e:state['errors']['stock']=type(e).__name__
  save()
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':wb.token},json={'chrtIds':sizes},timeout=55);r.raise_for_status()
  state['published_stock']=dict(data=r.json(),observed_at=stamp());save()
  state['minimums']={}
  for cid,cp in campaigns.items():
   matched=[n['nm_id']for n in cp['nm_settings']if n['nm_id']in nms]
   if not matched or cp['status']!=9 or cp['settings'].get('payment_type')!='cpc':continue
   for placement,on in cp['settings']['placements'].items():
    if on:
     try:state['minimums'][cid+':'+placement]=wb.minimums(int(cid),matched,placement)
     except Exception as e:state['errors']['minimum:'+cid+':'+placement]=type(e).__name__
   save()
  state.update(status='complete'if not state['errors']else'partial',completed_at=stamp());state=json.loads(json.dumps(state))
  if not c.create(ROOT+':inputs',state)or c.get(ROOT+':inputs')!=state:raise ValueError('Input readback mismatch')
  print(json.dumps(dict(status=state['status'],errors=state['errors'],wb_writes=0,telegram_calls=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()
