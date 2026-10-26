"""Read-only reconciliation of campaign technical cancellations, exact owner dates."""
import os,json
from collections import defaultdict
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,stamp
KEY='china_agent:technical_cancels:40933588:2026-10-20:2026-10-26:v1'
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 c=Cache();w=WB()
 if c.get(KEY):print('Existing private report; no repeat reads');return
 stats=w.req('/adv/v3/fullstats?ids=40933588&beginDate=2026-10-20&endDate=2026-10-26')
 c.put(KEY+':raw_ads',dict(observed_at=stamp(),rows=stats))
 totals=[];by={}
 for camp in stats:
  assert camp['advertId']==40933588
  for d in camp.get('days',[]):
   day=d['date'][:10];totals.append(dict(date=day,canceled=d.get('canceled'),orders=d.get('orders')))
   for app in d.get('apps',[]):
    for n in app.get('nms',[]):
     nm=str(n['nmId']);x=by.setdefault(nm,dict(nm_id=n['nmId'],canceled=0,orders=0,by_date={}))
     x['canceled']+=n.get('canceled',0);x['orders']+=n.get('orders',0)
     x['by_date'][day]=x['by_date'].get(day,0)+n.get('canceled',0)
 p=dict(status='ads_collected',observed_at=stamp(),campaign_id=40933588,period_from='2026-10-20',period_to='2026-10-26',daily=totals,products=sorted([x for x in by.values() if x['canceled']],key=lambda x:-x['canceled']),total_canceled=sum(x['canceled'] or 0 for x in totals),wb_writes=0,telegram_sends=0,order_linkage='Advertising fullstats has no order identifiers or cancellation reasons')
 c.put(KEY,p)
 r=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/orders',params=dict(dateFrom='2026-10-20T00:00:00',flag=0),headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=80)
 if not r.ok:
  p['orders_status']='HTTP '+str(r.status_code);c.put(KEY,p);return
 raw=r.json()
 assert isinstance(raw,list)
 if len(raw)>=80000:p['orders_completeness']='possibly_truncated'
 else:p['orders_completeness']='response_below_80000'
 selected=[]
 fields=['date','lastChangeDate','supplierArticle','nmId','srid','isCancel','cancelDate','orderType','incomeID','isSupply','isRealization']
 for o in raw:
  if '2026-10-20'<=o.get('date','')[:10]<='2026-10-26':
   selected.append({k:o[k] for k in fields if k in o})
 c.put(KEY+':order_statuses',dict(observed_at=stamp(),source='WB Statistics supplier/orders dateFrom20Oct flag0 lastChangeDate selection',rows=selected,raw_count=len(raw),reason_fields_present=sorted({k for o in raw for k in o if 'reason' in k.lower()}),no_advertising_order_id_link=True))
 p.update(status='complete',orders_status='collected',orders_rows=len(selected),completed_at=stamp());c.put(KEY,p)
 print('Read-only private reconciliation complete')
if __name__=='__main__':main()
