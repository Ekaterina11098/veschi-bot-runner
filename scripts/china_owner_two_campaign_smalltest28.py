"""Read-only exact small-traffic bid proposal, with current availability/minimum and conservative economics."""
import os,time,copy,json,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_bid_proposals import fresh_stock,sources
KEY='china_agent:two_campaign_small_traffic_proposal:2026-10-28:v1'
NMS=[1473242759,1473242764,1473243822,1473245498]
old_get=requests.get
def reconnect_get(*a,**kw):
 for attempt in range(3):
  try:return old_get(*a,**kw)
  except requests.exceptions.ConnectionError:
   if attempt==2:raise
   time.sleep(2*(attempt+1))
requests.get=reconnect_get
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write or (method!='GET' and not(method=='POST' and path=='/api/advert/v1/bids/min')):raise ValueError('Read only')
  return super().req(path,method,body,False)
class History:
 def __init__(self,c):self.c=c;self.now=datetime.now(timezone.utc)
 def get(self,k):return self.c.get(k)
 def save(self,*a,**kw):raise ValueError('No history write')
 def db(self,method,table,params=None,**kw):
  if method!='GET' or table!='telegram_api_cache':raise ValueError('Read-only cache')
  return self.c.req('GET',params)
def main():
 c=Cache()
 if c.get(KEY):return
 w=ReadWB();validate_identity(c,w);out=dict(status='collecting',stage='stock',created_at=stamp(),items=[],blocked=[],wb_writes=0,telegram_sends=0)
 try:
  source=c.get('china_agent:new_ad_source:v1:2026-10-28');products={p['nm_id']:p for p in source['products'] if p['nm_id'] in NMS}
  stock=fresh_stock({},[p['sa_name'] for p in products.values()]);sm={x['article']:x for x in stock};out['stock_at']=stamp();out['stage']='prices'
  r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params={'limit':1000,'offset':0},headers={'Authorization':w.token},timeout=45)
  if not r.ok:raise ValueError('Prices HTTP '+str(r.status_code))
  goods=r.json().get('data',{}).get('listGoods',[])
  if len(goods)>=1000:raise ValueError('Price pagination incomplete')
  pr={p['nmID']:p for p in goods if p['nmID'] in NMS}
  if len(pr)!=len(NMS):raise ValueError('Price identity incomplete')
  sizes={s['sizeID']:p['nmID'] for p in pr.values() for s in p['sizes']}
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',json={'chrtIds':list(sizes)},headers={'Authorization':w.token},timeout=45)
  if not r.ok:raise ValueError('WB stock HTTP '+str(r.status_code))
  published={}
  for row in r.json().get('stocks',[]):published.setdefault(sizes[row['chrtId']],[]).append(row.get('amount'))
  out['wb_stock_at']=stamp();out['stage']='membership and minima'
  camp=w.campaigns([41296359])['41296359'];ns={n['nm_id']:n for n in camp['nm_settings']}
  mins=w.minimums(41296359,NMS,'recommendations');out['minimums']=mins
  hist=sources(History(c));changes=[x for x in hist['changes'] if x.get('nm') in NMS];out['changes']=changes
  for nm,p in products.items():
   try:
    st=sm[p['sa_name']];price=pr[nm]['sizes'][0]['discountedPrice'];fee=p.get('total_commission_without_spp_in_sales')
    log=source['policy'].get('logistics_by_nm',{}).get(str(nm),{}).get('delivery_cny')
    if pr[nm]['vendorCode']!=p['sa_name'] or pr[nm]['currencyIsoCode4217']!='CNY':raise ValueError('Price identity mismatch')
    if st.get('stock') is None or st.get('reserve') is None or st.get('price') is None or st['stock']-st['reserve']<5:raise ValueError('Free MS stock below5 or unknown')
    if nm not in published or any(type(v)is not int for v in published[nm]) or sum(published[nm])<=0:raise ValueError('Published WB stock absent or zero')
    if nm not in ns or ns[nm]['bids_kopecks'].get('recommendations')!=28 or mins[nm]>34:raise ValueError('Current bid or minimum mismatch')
    recent=[x for x in changes if x.get('kind') in ['bid','price','added'] and str(x.get('at',''))[:10]>='2026-10-27']
    if recent:raise ValueError('Recent verified change; first full next day pending')
    if not p.get('finished_orders') or p.get('is_payed') is None or fee is None or log is None or not p.get('price_after_discount') or p.get('price_after_spp') is None:raise ValueError('Own unit model incomplete')
    q=min(p['is_payed']/p['finished_orders'],.5)
    expected=q*(price*(1-fee/100-.05*p['price_after_spp']/p['price_after_discount'])-st['price']/1200)-log-10/12-.05*price
    if expected<=0:raise ValueError('Conservative scenario negative')
    out['items'].append(dict(nm_id=nm,article=p['sa_name'],campaign_id=41296359,placement='recommendations',old_minor=28,target_minor=34,minimum_minor=mins[nm],price_cny=price,available_msk=st['stock']-st['reserve'],published_wb=sum(published[nm]),cogs_kopecks=st['price'],own_paid=p['is_payed'],own_finished=p['finished_orders'],scenario_buyout=q,expected_cny_per_order_at_drr5=round(expected,2),rating='unconfirmed_no_received_reviews',test_kind='small_traffic_experiment_not_proven_low_drr',assumptions='FX12RUB/CNY,tax5%,handling10RUB,dated historical logistics; buyout50% is scenario not measured forecast; DRR5% not guaranteed'))
   except (ValueError,KeyError,TypeError) as e:out['blocked'].append(dict(nm_id=nm,article=p['sa_name'],reason=str(e)))
  out.update(status='proposal_only',expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),observed_at=stamp())
 except Exception as e:out.update(status='blocked',reason=str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__,observed_at=stamp())
 c.put(KEY,out);print(json.dumps(dict(status=out['status'],stage=out['stage'],items=len(out['items']),reason=out.get('reason'))))
if __name__=='__main__':main()
