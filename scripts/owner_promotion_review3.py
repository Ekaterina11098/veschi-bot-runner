"""One-off owner promotion analysis; external reads only."""
import os,json,time,math,collections,requests,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_moysklad_read import read_stock
ROOT='china_agent:owner_promotion_review:2026-11-03:v2'
def main():
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(ROOT+':inputs'):return
 if not c.create(ROOT+':lease',dict(started_at=stamp(),wb_writes=0)):return
 rows=c.get(ROOT+':file')
 if len(rows)!=239:raise ValueError('Exact file scope missing')
 ids={r['nm'] for r in rows};articles=[r['article'] for r in rows]
 out=dict(status='collecting',observed_at=stamp(),cabinet='token_3',wb_writes=0,telegram_calls=0,errors={})
 def save():c.put(ROOT+':checkpoint',out)
 def read(url,method='GET',body=None,params=None):
  time.sleep(1.1)
  r=requests.request(method,url,headers={'Authorization':w.token},json=body,params=params,timeout=50)
  if not r.ok:raise RuntimeError('Read HTTP '+str(r.status_code))
  return r.json()
 try:
  prices=[]
  for offset in range(0,2000,1000):
   part=read('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params={'limit':1000,'offset':offset})['data']['listGoods']
   prices.extend(p for p in part if p['nmID'] in ids)
   if len(part)<1000:break
  if {p['nmID'] for p in prices}!=ids:raise ValueError('Price coverage incomplete')
  out['prices']=dict(rows=prices,observed_at=stamp());save()
  sizes=[s['sizeID'] for p in prices for s in p['sizes']]
  pub=read('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188','POST',{'chrtIds':sizes})
  if {r['chrtId'] for r in pub['stocks']}!=set(sizes):raise ValueError('Published stock coverage incomplete')
  out['published_stock']=dict(rows=pub['stocks'],observed_at=stamp());save()
  out['stock']=read_stock(articles);save()
  first=datetime(2026,10,27,tzinfo=ZoneInfo('Europe/Moscow'));last=datetime(2026,11,3,tzinfo=ZoneInfo('Europe/Moscow'))
  orders={};cursor=0;counts=collections.Counter();daily=collections.defaultdict(collections.Counter)
  for page in range(20):
   j=read('https://marketplace-api.wildberries.ru/api/v3/orders',params={'dateFrom':int(first.timestamp()),'dateTo':int(last.timestamp()),'next':cursor,'limit':1000})
   part=j.get('orders')
   if not isinstance(part,list):raise ValueError('Order coverage unknown')
   for r in part:
    at=datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow'))
    if first<=at<last and r['id'] not in orders:
     orders[r['id']]=True
     if r['nmId'] in ids:counts[str(r['nmId'])]+=1;daily[str(r['nmId'])][str(at.date())]+=1
   nxt=j.get('next')
   if not part or not nxt:break
   if nxt==cursor:raise ValueError('Order cursor repeated')
   cursor=nxt
  else:raise ValueError('Order pages incomplete')
  out['orders']=dict(counts=dict(counts),daily={k:dict(v) for k,v in daily.items()},period_from='2026-10-27',period_to='2026-11-02',scope='FBS created tasks, all returned statuses; not buyouts or proven whole-cabinet funnel',coverage_complete=True,observed_at=stamp(),pages=page+1,total_all_products=len(orders));save()
  old=c.get('china_agent:owner_profit_forecast:2026-11-02T22:codex224:v1:inputs:today')['inputs']['own_products']
  out['own_products']=old
  # CBR exact current analysis date; keep dated ruble/CNY quote.
  rr=requests.get('https://www.cbr.ru/scripts/XML_daily.asp',params={'date_req':'03/11/2026'},timeout=45);rr.raise_for_status();tree=ET.fromstring(rr.content)
  v=next(x for x in tree.findall('Valute') if x.findtext('CharCode')=='CNY')
  out['fx']=dict(rub_per_cny=float(v.findtext('Value').replace(',','.'))/int(v.findtext('Nominal')),date=tree.get('Date'),observed_at=stamp())
  out.update(status='complete',completed_at=stamp());c.create(ROOT+':inputs',out);save()
 except Exception as ex:
  out['errors']['collection']=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__;out.update(status='partial',completed_at=stamp());save()
 print(json.dumps(dict(status=out['status'],errors=out['errors'],wb_writes=0)))
if __name__=='__main__':main()
