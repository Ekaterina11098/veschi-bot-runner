"""Finalize previously collected owner read-only evidence without repeating data reads."""
import json,requests
from datetime import datetime,date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_mass_growth:2026-11-01:v1'
def main():
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Expired')
 c=Cache()
 if c.get(ROOT+':inputs'):return
 if not c.create(ROOT+':finalize_lease',dict(started_at=stamp())):return
 state=c.get(ROOT+':checkpoint')
 required=['stock','prices','published_stock','general_funnel','statistics','minimums','campaigns','budgets']
 if not state or any(k not in state for k in required)or state['errors']:raise ValueError('Collected inputs incomplete')
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
  r=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':wb.token},timeout=45);r.raise_for_status()
  state['config']=r.json()
  if state['config'].get('currency')!='CNY'or not state['config'].get('cpcStep'):raise ValueError('CPC config unknown')
  state['config_at']=stamp();state.update(status='complete',completed_at=stamp())
  state=json.loads(json.dumps(state))
  if not c.create(ROOT+':inputs',state)or c.get(ROOT+':inputs')!=state:raise ValueError('Readback mismatch')
  print(json.dumps(dict(status='complete',wb_writes=0,telegram_calls=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()
