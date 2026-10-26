"""Owner requested current order-profit comparison. Read-only, private snapshots."""
import os
from datetime import datetime,timezone,timedelta
import requests
from china_cloud_cost_control import Cache,WB,stamp
KEY='china_agent:profit_compare:2026-10-25:2026-10-26:full:v1'
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 c=Cache();w=WB()
 if c.get(KEY):print('Existing report; no repeated collection');return
 out=dict(status='collecting',observed_at=stamp(),cutoff_msk=datetime.now(timezone(timedelta(hours=3))).isoformat(),wb_writes=0,telegram_sends=0)
 c.put(KEY,out)
 r=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/orders',params=dict(dateFrom='2026-10-25T00:00:00',flag=0),headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=80)
 if not r.ok:out.update(status='blocked',error='WB orders HTTP '+str(r.status_code));c.put(KEY,out);return
 raw=r.json();assert isinstance(raw,list) and len(raw)<80000
 fields=['date','lastChangeDate','supplierArticle','nmId','srid','isCancel','cancelDate','totalPrice','discountPercent','spp','finishedPrice','priceWithDisc','currency','currencyName','currencyCode','orderType']
 selected=[{k:o[k] for k in fields if k in o} for o in raw if o.get('date','')[:10] in ['2026-10-25','2026-10-26']]
 c.put(KEY+':orders',dict(observed_at=stamp(),rows=selected,raw_count=len(raw),available_fields=sorted({k for o in raw for k in o}),selection='order dates25-26Oct from lastChangeDate>=25Oct flag0'))
 inv=w.req('/adv/v1/promotion/count')
 ids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
 stats=[]
 for start in range(0,len(ids),50):
  stats+=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids[start:start+50]))+'&beginDate=2026-10-25&endDate=2026-10-26')
 c.put(KEY+':ads',dict(observed_at=stamp(),rows=stats,ids=ids,basis='all campaign statuses day totals once, not SKU/app sum'))
 out.update(status='complete',completed_at=stamp(),orders=len(selected),campaigns=len(ids));c.put(KEY,out)
 print('Private comparison snapshots saved; no external writes')
if __name__=='__main__':main()
