"""Read only OOO order comparison, same Moscow cutoff; no price/stock/advert changes."""
import os,json,base64,time,requests
from datetime import datetime,timezone,timedelta
from collections import Counter
from china_cloud_cost_control import Cache,stamp
ROOT='china_agent:ooo_orders_compare:2026-10-29:v1';MSK=timezone(timedelta(hours=3))
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 cut=datetime.now(MSK);assert cut.date().isoformat()=='2026-10-29'
 c=Cache()
 if c.get(ROOT):print('Existing comparison');return
 token=os.environ['WB_TOKEN_1'];raw=token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
 assert claims.get('t') is False and claims.get('exp',0)>time.time()
 resp=requests.get(c.url.rsplit('/',1)[0]+'/analytics_snapshots',params=dict(cabinet='eq.token_1',source='eq.seller_identity',status='eq.complete',select='payload',limit=100),headers=c.h,timeout=30)
 if not resp.ok or {x['payload'].get('sid') for x in resp.json()}!={claims.get('sid')}:raise ValueError('OOO identity mismatch')
 assert {x['payload'].get('name') for x in resp.json()}=={'VESCHI'}
 resp=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/orders',params=dict(dateFrom='2026-10-28T00:00:00',flag=0),headers={'Authorization':token},timeout=80)
 if not resp.ok:raise RuntimeError('Orders read HTTP '+str(resp.status_code))
 data=resp.json()
 if not isinstance(data,list):raise ValueError('Orders shape')
 rows={}
 for x in data:
  if not x.get('srid') or not x.get('date'):raise ValueError('Missing identity')
  if x['srid'] not in rows or str(x.get('lastChangeDate',''))>str(rows[x['srid']].get('lastChangeDate','')):rows[x['srid']]={k:x.get(k) for k in ['srid','date','lastChangeDate','nmId','supplierArticle','isCancel','warehouseType','orderType']}
 days=[]
 for day in ['2026-10-28','2026-10-29']:
  selected=[]
  for row in rows.values():
   at=datetime.fromisoformat(row['date'].replace('Z','+00:00'))
   at=at.replace(tzinfo=MSK) if at.tzinfo is None else at.astimezone(MSK)
   if at.date().isoformat()==day and at.strftime('%H:%M:%S')<=cut.strftime('%H:%M:%S'):selected.append(row)
  days.append(dict(day=day,created=len(selected),known_cancels=sum(x['isCancel'] is True for x in selected),by_article=dict(Counter(x['supplierArticle'] for x in selected)),warehouse_types=dict(Counter(str(x['warehouseType']) for x in selected))))
 result=dict(status='complete',cabinet='token_1',seller_name='VESCHI',observed_at=stamp(),cutoff_msk=cut.isoformat(),days=days,latest_order=max((x['date'] for x in rows.values()),default=None),latest_change=max((x['lastChangeDate'] for x in rows.values()),default=None),rows_count=len(rows),raw_count=len(data),source='WB Statistics supplier/orders flag0, possible collection lag; not guaranteed complete realtime feed',wb_writes=0,telegram_sends=0)
 c.put(ROOT,result)
 print('OOO comparison stored privately')
if __name__=='__main__':main()
