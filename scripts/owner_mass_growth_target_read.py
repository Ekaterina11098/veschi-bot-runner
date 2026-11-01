"""Owner requested targeted final checks; no external mutations or Telegram."""
import json,requests
from datetime import datetime,date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_moysklad_read import read_stock
ROOT='china_agent:owner_mass_growth:2026-11-01:v1'
def main():
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Expired')
 c=Cache()
 if c.get(ROOT+':target_inputs'):return
 req=c.get(ROOT+':target_request')
 if not req or not req['read_only']or not 1<=len(req['rows'])<=20:raise ValueError('Exact scope missing')
 if not c.create(ROOT+':target_lease',dict(started_at=stamp())):return
 wb=WB();validate_identity(c,wb);original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json')
  db=u.scheme=='https' and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/') and (m=='GET' or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  ads=u.scheme=='https' and u.hostname=='advert-api.wildberries.ru' and ((m=='GET'and u.path in ['/adv/v1/promotion/count','/api/advert/v2/adverts','/adv/v3/fullstats','/api/advert/v1/config'])or(m=='POST'and u.path in ['/api/advert/v2/budget','/api/advert/v1/bids/min']))
  prices=u.scheme=='https'and u.hostname=='discounts-prices-api.wildberries.ru'and m=='GET'and u.path=='/api/v2/list/goods/filter'
  stock=u.scheme=='https'and u.hostname=='marketplace-api.wildberries.ru'and m=='POST'and u.path=='/api/v3/stocks/2126188'and isinstance(body,dict)and set(body)=={'chrtIds'}
  ms=u.scheme=='https'and u.hostname=='api.moysklad.ru'and m=='GET'and u.path in ['/api/remap/1.2/entity/store','/api/remap/1.2/entity/product','/api/remap/1.2/report/stock/all']
  funnel=u.scheme=='https'and u.hostname=='seller-analytics-api.wildberries.ru'and m=='POST'and u.path=='/api/analytics/v3/sales-funnel/products'
  if not(db or ads or prices or stock or ms or funnel):raise PermissionError('Diagnostic external write blocked')
  return original(session,method,url,*a,**kw)

 requests.sessions.Session.request=guard
 try:
  full=c.get(ROOT+':inputs')or c.get(ROOT+':checkpoint')
  if not full or not full.get('prices')or not full.get('general_funnel'):raise ValueError('Broad evidence missing')
  ids={r['nm_id']for r in req['rows']};prices=[r for r in full['prices']['rows']if r['nmID']in ids]
  if {r['nmID']for r in prices}!=ids:raise ValueError('Price coverage')
  state=dict(status='collecting',cabinet='token_3',wb_writes=0,telegram_calls=0,grants_action_permission=False,errors={},prices=dict(rows=prices,observed_at=full['prices']['observed_at']))
  state['stock']=read_stock([r['article']for r in req['rows']]);c.put(ROOT+':target_checkpoint',state)
  sizes=[s['sizeID']for p in prices for s in p['sizes']]
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':wb.token},json={'chrtIds':sizes},timeout=55);r.raise_for_status()
  state['published_stock']=dict(data=r.json(),observed_at=stamp());state['minimums']={}
  for key,nms in req['new_groups'].items():
   cid,zone=key.split(':')
   try:state['minimums'][key]=wb.minimums(int(cid),nms,zone)
   except Exception as ex:state['errors'][key]=type(ex).__name__
   c.put(ROOT+':target_checkpoint',state)
  state.update(status='complete'if not state['errors']else'partial',completed_at=stamp())
  state=json.loads(json.dumps(state))
  if not c.create(ROOT+':target_inputs',state)or c.get(ROOT+':target_inputs')!=state:raise ValueError('Readback')
  print(json.dumps(dict(status=state['status'],stock_rows=len(state['stock']['rows']),errors=state['errors'],wb_writes=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()
