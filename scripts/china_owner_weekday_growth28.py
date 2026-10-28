"""Same-weekday comparison and fresh evidence for growth candidates; no mutations."""
import os,json,copy
from datetime import datetime
import requests
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
from china_bid_proposals import fresh_stock
from china_advertising_plans import economics
ROOT='china_agent:owner_sales_ads_review:2026-10-28:afternoon:v1'
KEY=ROOT+':weekday_growth'
class ReadWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write or method!='GET' and not(method=='POST' and path=='/api/advert/v1/bids/min'):raise ValueError('Read only')
  return super().req(path,method,body,write=False)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache()
 if c.get(KEY):print('Existing weekday growth evidence');return
 base=c.get(ROOT);cut=base['cutoff_msk'][11:19];w=ReadWB();validate_identity(c,w)
 out=dict(status='collecting',cutoff_msk=base['cutoff_msk'],reference_day='2026-10-21',observed_at=stamp(),wb_writes=0,telegram_sends=0,errors=[])
 c.put(KEY,out)
 for kind in ['orders','sales']:
  r=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/'+kind,params=dict(dateFrom='2026-10-21',flag=1),headers={'Authorization':w.token},timeout=80)
  if not r.ok:out['errors'].append(kind+' HTTP '+str(r.status_code));continue
  raw=r.json()
  if not isinstance(raw,list) or len(raw)>=80000:raise ValueError('Reference scope incomplete')
  rows=[x for x in raw if x.get('date','')[:10]=='2026-10-21'];dedup={}
  for x in rows:
   ident=x.get('srid') if kind=='orders' else x.get('saleID')
   if not ident:raise ValueError('Missing reference identity')
   if ident not in dedup or x.get('lastChangeDate','')>dedup[ident].get('lastChangeDate',''):dedup[ident]=x
  def total(items):
   if kind=='orders':
    active=[x for x in items if x.get('isCancel') is False]
    return dict(created=len(items),not_cancelled=len(active),cancelled=len(items)-len(active),created_amount_rub=sum(x['priceWithDisc'] for x in items),not_cancelled_amount_rub=sum(x['priceWithDisc'] for x in active))
   sales=[x for x in items if str(x['saleID']).startswith('S')];returns=[x for x in items if str(x['saleID']).startswith('R')]
   return dict(buyouts=len(sales),returns=len(returns),buyout_amount_rub=sum(abs(x['priceWithDisc']) for x in sales),return_amount_rub=sum(abs(x['priceWithDisc']) for x in returns))
  out[kind]=dict(full=total(list(dedup.values())),same_hour=total([x for x in dedup.values() if x['date'][11:19]<=cut]))
  c.put(KEY,out)
 st=w.req('/adv/v3/fullstats?ids='+','.join(map(str,base['campaign_ids']))+'&beginDate=2026-10-21&endDate=2026-10-21')
 out['advertising_reference_full_day']={k:sum(d.get(f,0) for a in st for d in a.get('days',[]) if d['date'][:10]=='2026-10-21') for k,f in dict(spend='sum',amount='sum_price',orders='orders',clicks='clicks').items()}
 c.put(KEY,out)
 source=copy.deepcopy(c.get('china_agent:new_ad_source:v1:2026-10-28'));wanted={1473245494,1473244340,1473244337}
 products={int(p['nm_id']):p for p in source['products']}
 articles=[products[n]['sa_name'] for n in wanted]
 stock=fresh_stock(source,articles)
 p=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params=dict(limit=1000,offset=0),headers={'Authorization':w.token},timeout=60)
 if not p.ok:raise ValueError('Fresh prices HTTP '+str(p.status_code))
 prices=p.json().get('data',{}).get('listGoods',[])
 if len(prices)>=1000:raise ValueError('Price pagination incomplete')
 source['stock']=stock;source['prices']=prices
 camp=w.campaigns([40933588])['40933588']
 mins=w.minimums(40933588,sorted(wanted),'recommendations')
 out['growth']=[]
 for nm in sorted(wanted):
  member=next((m for m in camp['nm_settings'] if m['nm_id']==nm),None)
  row=dict(nm=nm,article=products[nm]['sa_name'],member=member,minimum_minor=mins.get(nm),stock_observed_at=stamp(),stock=next((x for x in stock if x['article'].casefold()==products[nm]['sa_name'].casefold()),None))
  try:row['economics']=economics(source,nm)
  except (ValueError,KeyError,TypeError) as e:row['economics_blocker']=str(e)
  out['growth'].append(row)
 out.update(status='complete',completed_at=stamp());c.put(KEY,out);print(json.dumps(dict(status='complete',errors=out['errors'],growth=len(out['growth']),wb_writes=0)))
if __name__=='__main__':main()
