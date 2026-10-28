"""Read-only price shortlist after owner asks whether any further increases are due."""
import os,json,copy,collections
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
from china_bid_proposals import fresh_stock
from china_advertising_plans import economics
import requests
KEY='china_agent:owner_price_review:2026-10-28:afternoon:v1'
NMS=[1473243916,1473244992,1535337780,1473243909,1473244348,1473242763]
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache();wb=WB();validate_identity(c,wb)
 if c.get(KEY):print('Existing price review');return
 source=copy.deepcopy(c.get('china_agent:new_ad_source:v1:2026-10-28'));products={int(p['nm_id']):p for p in source['products']}
 stock=fresh_stock(source,[products[n]['sa_name'] for n in NMS])
 r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params=dict(limit=1000,offset=0),headers={'Authorization':wb.token},timeout=60)
 if not r.ok:raise ValueError('Price read HTTP '+str(r.status_code))
 goods=r.json().get('data',{}).get('listGoods',[])
 if not goods or len(goods)>=1000:raise ValueError('Price scope incomplete')
 source.update(stock=stock,prices=goods)
 orders=(c.get('china_agent:owner_sales_ads_review:2026-10-28:afternoon:v1:orders') or {})['rows']
 history=(c.get('china_agent:demand_watch:v1') or {}).get('price_history',{})
 changed_today=c.get('china_agent:price_execution:v1:-1004342917488:155:307200273:e6c13e1e7186bedd902c081a1b11745e6e61099bfa6e2754dce69ef53929cbf7') or {}
 recent={int(x['selection']['nm_id']) for x in changed_today.get('items',[]) if x.get('status')=='applied'}
 out=dict(status='complete',observed_at=stamp(),rows=[],price_writes=0,wb_writes=0,telegram_calls=0)
 for nm in NMS:
  p=products[nm];pr=next((g for g in goods if g['nmID']==nm),None);st=next((s for s in stock if s['article'].casefold()==p['sa_name'].casefold()),None)
  daycounts=dict(collections.Counter(x['date'][:10] for x in orders if x.get('nmId')==nm and x.get('isCancel') is False))
  h=history.get(str(nm),{})
  row=dict(nm=nm,article=p['sa_name'],stock=st,current_price=pr,orders_by_day=daycounts,own_finished=p.get('finished_orders'),own_paid=p.get('is_payed'),last_price_change_at=(h.get('last_price_change') or {}).get('detected_at'),first_full_price_day=(h.get('increase') or {}).get('start_date'),raised_today=nm in recent)
  try:row['economics']=economics(source,nm)
  except (ValueError,KeyError,TypeError) as e:row['economics_blocker']=str(e)
  out['rows'].append(row)
 if not c.create(KEY,out):raise ValueError('Concurrent read review')
 print(json.dumps(dict(status='complete',reviewed=len(out['rows']),price_writes=0)))
if __name__=='__main__':main()
