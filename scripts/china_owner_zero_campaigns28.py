"""Read-only diagnosis of current zero-order campaigns and small traffic-test candidates."""
import os,json,copy
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
from china_bid_proposals import fresh_stock
from china_advertising_plans import economics
from china_advertising_v2 import history
from china_advertising_midday import post_change_pending
KEY='china_agent:zero_campaign_review:2026-10-28:afternoon:v1'
CIDS=[41270471,41325622,41270474,40964981,41296359,41187173,41155824]
CANDIDATES=[(41325622,1535337780,'search'),(40964981,1560345287,'recommendations'),(41187173,1560230896,'recommendations')]
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(KEY):print('Existing zero campaign check');return
 stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,CIDS))+'&beginDate=2026-10-25&endDate=2026-10-28');cs=w.campaigns(CIDS)
 source=copy.deepcopy(c.get('china_agent:new_ad_source:v1:2026-10-28'))
 labels={int(p['nm_id']):p for p in source['products']}
 stock=fresh_stock(source,[labels[nm]['sa_name'] for cid,nm,z in CANDIDATES])
 rr=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params=dict(limit=1000,offset=0),headers={'Authorization':w.token},timeout=60)
 if not rr.ok:raise ValueError('Fresh price HTTP '+str(rr.status_code))
 goods=rr.json().get('data',{}).get('listGoods',[])
 if not goods or len(goods)>=1000:raise ValueError('Prices incomplete')
 source.update(stock=stock,prices=goods)
 midday=c.get('china_agent:advertising_midday_source:2026-10-28:v2') or {};records=list(midday.get('executions',[]))
 for pointer in (c.get('china_agent:verified_campaign_state:v1') or {}).values():
  r=c.get(pointer)
  if r and r.get('status')=='verified':records.append(dict(cache_key=pointer,payload=r))
 changes=history(records);out=dict(status='complete',observed_at=stamp(),rows=[],candidates=[],wb_writes=0,telegram_calls=0)
 for cid in CIDS:
  st=next((x for x in stats if x['advertId']==cid),None);camp=cs[str(cid)]
  days={d['date'][:10]:{k:d.get(v) for k,v in dict(spend='sum',amount='sum_price',orders='orders',clicks='clicks',views='views',baskets='atbs').items()} for d in (st or {}).get('days',[])}
  out['rows'].append(dict(cid=cid,name=camp['settings']['name'],days=days,statistics_present=st is not None,members=camp['nm_settings']))
 for cid,nm,zone in CANDIDATES:
  camp=cs[str(cid)];p=labels[nm];n=next(n for n in camp['nm_settings'] if n['nm_id']==nm)
  row=dict(cid=cid,nm=nm,article=p['sa_name'],placement=zone,current_minor=n['bids_kopecks'][zone],minimum_minor=w.minimums(cid,[nm],zone)[nm],protected=post_change_pending(changes,cid,nm,'2026-10-28',camp),latest_events=[e for e in changes if e['nm']==nm][-5:])
  try:row['economics']=economics(source,nm)
  except (ValueError,KeyError,TypeError) as ex:row['blocker']=str(ex)
  out['candidates'].append(row)
 if not c.create(KEY,out):raise ValueError('Concurrent diagnosis')
 print(json.dumps(dict(status='complete',campaigns=len(out['rows']),candidates=len(out['candidates']),wb_writes=0)))
if __name__=='__main__':main()
