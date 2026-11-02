"""Owner requested fresh13MSK snapshot and exact candidate stock read; no mutations/messages."""
import os,json,requests
from datetime import datetime
from zoneinfo import ZoneInfo
from china_hourly_sales_read import run
from china_cloud_cost_control import Cache,stamp
ROOT='china_agent:owner_growth_refresh:2026-11-02T13:v1'
def main():
 now=datetime.now(ZoneInfo('Europe/Moscow'))
 if now.date().isoformat()!='2026-11-02' or now.hour!=13:raise RuntimeError('Dated13MSKonly')
 run()
 c=Cache()
 if c.get(ROOT):print('Candidate refresh exists; no repeat');return
 cat=c.get('china_agent:prices:v1')or{}
 if cat.get('cabinet')!='token_3':raise RuntimeError('Cabinet catalogue unavailable')
 ids={1473243909,1560345283,1473244992}
 goods=[r for r in cat['rows']if r['nmID']in ids]
 if {r['nmID']for r in goods}!=ids:raise RuntimeError('Candidate coverage missing')
 size_nm={z['sizeID']:g['nmID']for g in goods for z in g['sizes']}
 r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':os.environ['WB_TOKEN_3']},json=dict(chrtIds=list(size_nm)),timeout=45)
 if not r.ok:raise RuntimeError('Published stock HTTP '+str(r.status_code))
 rows=r.json()['stocks']
 if {r['chrtId']for r in rows}!=set(size_nm):raise RuntimeError('Published stock response incomplete')
 value=dict(status='complete',cabinet='token_3',observed_at=stamp(),rows=[dict(nm_id=g['nmID'],article=g['vendorCode'],published_stock=sum(r['amount']for r in rows if size_nm[r['chrtId']]==g['nmID']))for g in goods],wb_writes=0,telegram_calls=0,grants_action_permission=False)
 if not c.create(ROOT,value):raise RuntimeError('Concurrent immutable refresh')
 if c.get(ROOT)!=value:raise RuntimeError('Readback mismatch')
 print(json.dumps(value))
if __name__=='__main__':main()
