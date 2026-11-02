"""Owner requested completed-day China sales diagnosis; immutable private output only."""
import os,json,requests
from datetime import datetime,timedelta
from china_hourly_sales_read import Cache,ReadOnlyWB,validate_identity,read_orders,select_rows,aggregate,comparison,stamp,MSK
ROOT='china_agent:owner_sales_completed:2026-11-01:review20261102:v1'
def main():
 c=Cache()
 if c.get(ROOT):print('Existing immutable analysis inputs; no repeated reads');return
 w=ReadOnlyWB();validate_identity(c,w)
 def get(path,params=None):
  if path not in ('/api/v3/orders','/api/v3/orders/new'):raise RuntimeError('Read-only FBS guard')
  r=requests.get('https://marketplace-api.wildberries.ru'+path,params=params,headers={'Authorization':w.token},timeout=50)
  if not r.ok:raise RuntimeError('FBS HTTP '+str(r.status_code))
  return r.json()
 new=get('/api/v3/orders/new').get('orders')
 if not isinstance(new,list):raise RuntimeError('New orders response missing')
 catalog=c.get('china_agent:prices:v1')
 if not catalog or catalog.get('cabinet')!='token_3':raise RuntimeError('Cabinet catalogue unavailable')
 allowed={r['nmID'] for r in catalog['rows']}
 result=dict(status='complete',cabinet='token_3',observed_at=stamp(),orders={},wb_writes=0,telegram_calls=0,grants_action_permission=False,basis='FBS created tasks all statuses; convertedPrice buyer-discounted CNY, not seller revenue, buyouts or proven entire cabinet')
 for ds in ('2026-10-31','2026-11-01','2026-10-25'):
  start=datetime.fromisoformat(ds).replace(tzinfo=MSK);end=start+timedelta(days=1)
  raw=read_orders(get,start,end);raw.update({r['id']:r for r in new})
  rows=select_rows(raw.values(),start,end);total=aggregate(rows)
  unknown=sorted({r['nmId'] for r in rows if r['nmId'] not in allowed})
  status='complete' if not unknown and not total['unknown_amount_ids'] else 'partial'
  result['orders'][ds]=dict(status=status,start_msk=start.isoformat(),end_msk=end.isoformat(),observed_at=stamp(),totals=total,rows=rows,unknown_catalogue_nm_ids=unknown)
  if status!='complete':result['status']='partial'
 result['comparisons']={ds:comparison(result['orders']['2026-11-01']['totals'],result['orders'][ds]['totals']) for ds in ('2026-10-31','2026-10-25')}
 if not c.create(ROOT,result):raise RuntimeError('Concurrent immutable inputs')
 if c.get(ROOT)!=result:raise RuntimeError('Private input readback mismatch')
 print(json.dumps(dict(status=result['status'],comparisons=result['comparisons'],wb_writes=0)))
if __name__=='__main__':main()
