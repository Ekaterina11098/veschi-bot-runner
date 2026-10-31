"""Read-only coverage and order status verification for the frozen owner API comparison."""
import os,json,requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:same_hour_sales:2026-10-31:api:v1'
def run():
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(ROOT+':coverage'):return
 e=c.get(ROOT);ids=e['advertising']['campaign_ids_requested'];returned={s['advertId']for s in e['advertising']['stats']}
 missing=sorted(set(ids)-returned);cs=w.campaigns(missing)if missing else{}
 oids=[r['id']for r in e['orders']['rows']]
 rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/orders/status',headers={'Authorization':w.token},json={'orders':oids},timeout=45)
 status=dict(http_status=rr.status_code)
 if rr.ok:
  data=rr.json().get('orders',[]);status.update(rows=[{k:r.get(k)for k in['id','supplierStatus','wbStatus']}for r in data],complete={r['id']for r in data}==set(oids))
 result=dict(observed_at=stamp(),missing_campaigns=cs,orders_status=status,wb_writes=0,telegram_calls=0)
 c.create(ROOT+':coverage',result)
 print(json.dumps({'missing_campaigns':len(missing),'status_read_http':rr.status_code,'wb_writes':0}))
if __name__=='__main__':run()
