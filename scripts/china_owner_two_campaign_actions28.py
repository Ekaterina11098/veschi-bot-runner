"""Read-only actionable screening of current two-campaign SKU availability and completed-day evidence."""
import os,json,copy,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_bid_proposals import fresh_stock,sources
from china_advertising_plans import economics
KEY='china_agent:two_campaign_action_review:2026-10-28:1840:v1'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if method!='GET' or write:raise ValueError('Read only')
  return super().req(path,method,body,False)
class History:
 def __init__(self,c):self.c=c;self.now=datetime.now(timezone.utc)
 def get(self,k):return self.c.get(k)
 def save(self,*a,**kw):raise ValueError('No history writes')
 def db(self,method,table,params=None,**kw):
  if method!='GET' or table!='telegram_api_cache':raise ValueError('Read only cache')
  return self.c.req('GET',params)
def main():
 c=Cache()
 if c.get(KEY):return
 w=ReadWB();validate_identity(c,w);out=dict(status='collecting',observed_at=stamp(),wb_writes=0,telegram_sends=0)
 try:
  camps=w.campaigns([41296359,41155824]);ids={n['nm_id'] for cp in camps.values() for n in cp['nm_settings']}
  src=c.get('china_agent:new_ad_source:v1:2026-10-28') or {};products={p['nm_id']:p for p in src.get('products',[]) if p['nm_id'] in ids}
  if len(products)!=len(ids):raise ValueError('Own product identity incomplete')
  stock=fresh_stock({},[p['sa_name'] for p in products.values()]);out['stock_at']=stamp()
  r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params={'limit':1000,'offset':0},headers={'Authorization':w.token},timeout=60)
  if not r.ok:raise ValueError('Prices HTTP '+str(r.status_code))
  goods=r.json().get('data',{}).get('listGoods',[])
  if len(goods)>=1000:raise ValueError('Prices pagination incomplete')
  prices={p['nmID']:p for p in goods if p['nmID'] in ids}
  sizes={s['sizeID']:p['nmID'] for p in prices.values() for s in p.get('sizes',[])}
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',json={'chrtIds':list(sizes)},headers={'Authorization':w.token},timeout=60)
  if not r.ok:raise ValueError('WB stock HTTP '+str(r.status_code))
  wbrows=r.json().get('stocks',[]);wbstock={}
  for r in wbrows:wbstock.setdefault(sizes[r['chrtId']],[]).append(r.get('amount'))
  out['wb_stock_at']=stamp()
  stats=w.req('/adv/v3/fullstats?ids=41296359,41155824&beginDate=2026-10-25&endDate=2026-10-27');out['stats']=stats
  history=sources(History(c));out['changes']=[v for v in history['changes'] if v.get('nm') in ids]
  model=copy.deepcopy(src);model.update(stock=stock,prices=goods)
  rows=[]
  for cid,cp in camps.items():
   for n in cp['nm_settings']:
    nm=n['nm_id'];p=products[nm]
    try:ec=economics(model,nm)
    except Exception as error:ec=dict(status='unconfirmed',reason=str(error) if isinstance(error,ValueError) else type(error).__name__)
    row=dict(nm_id=nm,article=p['sa_name'],campaign_id=int(cid),current_bids=n['bids_kopecks'],wb_stock=sum(wbstock[nm]) if nm in wbstock and all(type(v)is int for v in wbstock[nm]) else None,
      economics=ec,own_paid=p.get('is_payed'),own_finished=p.get('finished_orders'),price=prices.get(nm,{}).get('sizes',[{}])[0].get('discountedPrice'),
      price_changed_today=prices.get(nm,{}).get('sizes',[{}])[0].get('discountedPrice')!=next((v for v in src['prices'] if v['nmID']==nm),{}).get('sizes',[{}])[0].get('discountedPrice'))
    rows.append(row)
  out.update(status='complete',rows=rows,observed_at=stamp(),missing_stock_rows=len(ids)-len(wbstock))
 except Exception as e:out.update(status='blocked',reason=str(e) if isinstance(e,ValueError) else type(e).__name__)
 c.put(KEY,out);print(json.dumps(dict(status=out['status'],reason=out.get('reason'),wb_writes=0)))
if __name__=='__main__':main()
