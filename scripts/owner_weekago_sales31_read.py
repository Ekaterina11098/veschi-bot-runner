"""Owner read-only prior Saturday comparison, same FBS API and native CNY fields."""
import json,time,requests
from datetime import datetime
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:same_hour_sales:2026-10-24:api:v1'
def run():
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(ROOT):return
 tz=ZoneInfo('Europe/Moscow');first=datetime(2026,10,24,tzinfo=tz);end=first.replace(hour=12);cursor=0;rows={};pages=0
 while True:
  rr=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':w.token},params={'limit':1000,'next':cursor,'dateFrom':int(first.timestamp()),'dateTo':int(end.timestamp())},timeout=50)
  if not rr.ok:raise ValueError('Order read HTTP '+str(rr.status_code))
  j=rr.json();part=j.get('orders',[]);pages+=1
  for r in part:
   at=datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(tz)
   if first<=at<end:rows[r['id']]={k:r.get(k)for k in['id','nmId','article','createdAt','price','currencyCode','convertedPrice','convertedCurrencyCode']}
  nxt=j.get('next')
  if not part or not nxt:break
  if nxt==cursor or pages>=12:raise ValueError('Pagination incomplete')
  cursor=nxt;time.sleep(.4)
 values=list(rows.values());cat=c.get('china_agent:prices:v1')or{};known={g['nmID']for g in cat.get('rows',[])}
 if cat.get('cabinet')!='token_3'or any(r['nmId']not in known for r in values):raise ValueError('Cabinet catalogue mismatch')
 if any(r.get('convertedCurrencyCode')!=156 or not isinstance(r.get('convertedPrice'),int)for r in values):raise ValueError('Native CNY field incomplete')
 result=dict(status='complete',cabinet='token_3',observed_at=stamp(),period_from=first.isoformat(),period_to=end.isoformat(),rows=values,pages=pages,count=len(values),amount_cny=sum(r['convertedPrice']for r in values)/100,currency='CNY',money_basis='convertedPrice/100 native156, same API as31Oct noon; all statuses, not buyouts',wb_writes=0,telegram_calls=0)
 if not c.create(ROOT,result):raise ValueError('Snapshot race')
 print(json.dumps({k:result[k]for k in['status','count','amount_cny','pages','wb_writes']}))
if __name__=='__main__':run()
