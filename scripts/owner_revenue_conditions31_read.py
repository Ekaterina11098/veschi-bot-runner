"""Dated owner-requested top revenue-loss preflight. No marketplace writes or messages."""
import os, json, requests
from datetime import datetime, timezone
from china_cloud_cost_control import Cache, validate_identity, stamp
from china_hourly_sales_read import ReadOnlyWB
from china_moysklad_read import read_stock
ROOT='china_agent:revenue_diagnosis:2026-10-31:13:v1:conditions'
TARGETS={1473245494:'143-ReginaBag-black',1473245509:'588-ReginaBag-dbrown',1473243825:'52-NoelBag-fuchsia',1473243239:'542-CelineaBag-darkbrown',1473245499:'282-KiraBag-gray'}
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or datetime.now(timezone.utc).date().isoformat()!='2026-10-31':raise ValueError('Dated public owner read only')
 c=Cache(); w=ReadOnlyWB()
 if c.get(ROOT):print('Existing immutable conditions preserved');return
 validate_identity(c,w)
 e=dict(status='reading',cabinet='token_3',started_at=stamp(),wb_writes=0,telegram_calls=0,moysklad_writes=0,workflow_run=os.environ.get('GITHUB_RUN_ID'))
 def safe(ex):return str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__
 try:
  ids=[40933588,41298169,41270309,41332083]
  e['campaigns']=w.campaigns(ids);e['campaigns_observed_at']=stamp()
 except Exception as ex:e['campaign_error']=safe(ex)
 try:
  r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params={'limit':1000,'offset':0},headers={'Authorization':w.token},timeout=55)
  if not r.ok:raise ValueError('Price read HTTP '+str(r.status_code))
  goods=r.json().get('data',{}).get('listGoods')
  if not isinstance(goods,list) or len(goods)>=1000:raise ValueError('Price coverage incomplete')
  goods=[g for g in goods if g['nmID']in TARGETS]
  if {g['nmID']for g in goods}!=set(TARGETS)or any(g['currencyIsoCode4217']!='CNY'for g in goods):raise ValueError('Target price identity/coverage mismatch')
  e.update(prices=goods,prices_observed_at=stamp())
  sm={s['sizeID']:g['nmID']for g in goods for s in g['sizes']}
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',json={'chrtIds':list(sm)},headers={'Authorization':w.token},timeout=50)
  if not r.ok:raise ValueError('Published stock read HTTP '+str(r.status_code))
  pub={};seen=set()
  for s in r.json().get('stocks',[]):
   if s['chrtId']not in sm or type(s.get('amount'))is not int:raise ValueError('Stock response scope invalid')
   seen.add(s['chrtId']);nm=str(sm[s['chrtId']]);pub[nm]=pub.get(nm,0)+s['amount']
  e.update(published_stock=pub,published_stock_complete=seen==set(sm),published_stock_observed_at=stamp())
 except Exception as ex:e['price_stock_error']=safe(ex)
 try:e['stock']=read_stock(list(TARGETS.values()))
 except Exception as ex:e['moysklad_error']=safe(ex)
 e.update(status='complete'if not any(k.endswith('_error')for k in e)and e.get('published_stock_complete')and e['stock']['coverage_complete']else'partial',completed_at=stamp())
 if not c.create(ROOT,e)or c.get(ROOT)!=e:raise ValueError('Private conditions readback failed')
 print(json.dumps({k:e.get(k)for k in['status','wb_writes','telegram_calls','moysklad_writes']}))
if __name__=='__main__':run()
