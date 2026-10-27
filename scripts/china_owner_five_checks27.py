"""Five exact requested SKU checks; read-only WB/MSK; partial economics never net profit."""
import os,json,time
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity
KEY='china_agent:owner_five_tests:2026-10-27:v1:check'
ITEMS=[(41155824,1473244998,'611-MayaBag-black'),(41155824,1473244999,'612-MayaBag-black'),(41296363,1473242577,'637-FreyaBag-grey'),(41296363,1473246054,'657-FioreBag-grey'),(41296363,1473246055,'658-FioreBag-brown')]
def stamp():return datetime.now(timezone.utc).isoformat()
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise ValueError('This proposal never writes WB')
  return super().req(path,method,body,write=False)
def stocks():
 headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']};base='https://api.moysklad.ru/api/remap/1.2'
 r=requests.get(base+'/entity/store',headers=headers,params={'limit':1000},timeout=45)
 if not r.ok:raise ValueError('Store unavailable')
 stores=[s for s in r.json().get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
 if len(stores)!=1:raise ValueError('MSK store ambiguous')
 wanted={i[2].casefold() for i in ITEMS};rows=[];offset=0
 while True:
  r=requests.get(base+'/report/stock/all',headers=headers,params={'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000,'offset':offset},timeout=50)
  if not r.ok:raise ValueError('Stock unavailable')
  data=r.json();part=data.get('rows',[])
  rows.extend({k:p.get(k) for k in ['article','stock','reserve','price']} for p in part if (p.get('article') or '').casefold() in wanted)
  if offset+len(part)>=data.get('meta',{}).get('size',offset+len(part)):break
  if not part or offset>=5000:raise ValueError('Stock incomplete')
  offset+=len(part)
 if len(rows)!=5 or {r['article'].casefold() for r in rows}!=wanted:raise ValueError('Five unique stock records required')
 return rows
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache()
 if c.get(KEY):print('Already checked; no repeated polling');return
 wb=ReadWB();validate_identity(c,wb)
 record=dict(status='checking',created_at=stamp(),wb_writes=0,telegram_calls=0)
 if not c.create(KEY,record):raise ValueError('Concurrent check')
 try:
  campaigns=wb.campaigns([41155824,41296363]);stock=stocks();prices={}
  for cid,nm,article in ITEMS:
   time.sleep(1)
   r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',headers={'Authorization':wb.token},params=dict(limit=1000,offset=0,filterNmID=nm),timeout=45)
   if not r.ok:raise ValueError('Price read unavailable')
   data=r.json()
   if data.get('error'):raise ValueError('Price read rejected')
   goods=data.get('data',data).get('listGoods',[])
   if len(goods)!=1 or goods[0]['nmID']!=nm or goods[0].get('vendorCode')!=article or goods[0].get('currencyIsoCode4217')!='CNY':raise ValueError('Exact price identity mismatch')
   prices[str(nm)]=goods[0]
  minima={}
  for cid in [41155824,41296363]:minima.update(wb.minimums(cid,[n for c,n,a in ITEMS if c==cid],'recommendations'))
  model=c.get('china_agent:new_ad_source:v1:2026-10-27') or {}
  products={int(p['nm_id']):p for p in model.get('products',[])}
  rows=[]
  for cid,nm,article in ITEMS:
   camp=campaigns[str(cid)]
   if camp['status']!=9 or camp['settings']['placements']!=dict(search=False,recommendations=True):raise ValueError('Campaign placement/status changed')
   member=next(n for n in camp['nm_settings'] if n['nm_id']==nm);old=member['bids_kopecks']['recommendations']
   st=next(s for s in stock if s['article'].casefold()==article.casefold())
   if any(not isinstance(st.get(k),(int,float)) for k in ['stock','reserve','price']):raise ValueError('Unknown stock/COGS')
   available=st['stock']-st['reserve'];pr=prices[str(nm)];sizes=pr['sizes']
   if not sizes or len({s['discountedPrice'] for s in sizes})!=1:raise ValueError('Ambiguous seller price')
   price=sizes[0]['discountedPrice'];p=products.get(nm,{})
   # Cabinet20% and tax5% are scenario assumptions from the existing policy, not observed SKU fees.
   partial=price*(1-.20-.05-.05)-st['price']/1200-10/12
   row=dict(campaign_id=cid,nm_id=nm,article=article,old_minor=old,target_minor=31,minimum_minor=minima[nm],seller_price_cny=price,stock=st,available=available,cogs_rub=st['price']/100,partial_margin_cny_at5_before_delivery_and_returns=round(partial,2),own_finished=p.get('finished_orders'),own_paid=p.get('is_payed'),own_funnel_orders=p.get('funnel_orders_count'),own_cart_events=p.get('add_to_cart_count'),own_period_from=model.get('period_from'),own_period_to=model.get('period_to'),confirmed_net_profit=None,logistics_confirmed=False)
   row['technically_possible']=old==28 and available>0 and minima[nm]<=31
   row['economics_status']='incomplete_own_buyout_and_logistics'
   rows.append(row)
  record.update(status='checked',observed_at=stamp(),campaigns=campaigns,items=rows,prices=prices,stock=stock,assumptions=dict(fx_rub_cny=12,commission_pct=20,tax_pct=5,ad_drr_pct=5,handling_rub=10),limitations='Partial margin assumes one paid sale, excludes delivery/return cost and unknown deductions; actual SKU buyout and commission not established. Not net profit or guarantee DRR. No bids changed; read-only owner request.')
 except Exception as error:record.update(status='blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=stamp())
 c.put(KEY,record)
 print(json.dumps({k:record.get(k) for k in ['status','observed_at','reason','wb_writes','telegram_calls']}))
if __name__=='__main__':run()
