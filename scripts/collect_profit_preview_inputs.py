"""Read-only private order-profit inputs. No marketplace writes or Telegram."""
import os,json,time
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import requests
from conversion_watches import runtime
from china_wb_evidence import ad_expenses,own_costs
KEY='china_agent:profit_preview_inputs:v1:2026-10-21:2026-10-23'
def main():
 original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper()
  if u.hostname=='api.telegram.org':raise PermissionError('No Telegram')
  if u.hostname and u.hostname.endswith('wildberries.ru') and m!='GET':raise PermissionError('Read only WB')
  if u.hostname==urlparse(os.environ['SUPABASE_URL']).hostname and m!='GET' and u.path!='/rest/v1/telegram_api_cache':raise PermissionError('Only private input cache')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  w=runtime();old=w.get(KEY)
  if old and old.get('complete'):
   stock=w.get('china_agent:analytic_read:v1:9e4056e823a5bfde339abb603e79046fcc37a63eecea08a6ee4eda999ad871d2')
   costs,evidence=own_costs(w,stock,[dict(nmId=1473245503,rrDate='2026-10-21',sellerOperName='销售')],'2026-10-21','2026-10-23')
   w.save(KEY+':cost_recovery',dict(cost_rub=costs.get(1473245503),evidence=evidence,wb_writes=0,telegram_sends=0))
   print(json.dumps(dict(status='cost_recovery',resolved=costs.get(1473245503) is not None)))
   return
  token=os.environ['WB_TOKEN_3'];first='2026-10-21';last='2026-10-23';msk=timezone(timedelta(hours=3))
  a=datetime(2026,10,21,tzinfo=msk);b=datetime(2026,10,24,tzinfo=msk)
  rows={};cursor=0;pages=0
  while True:
   r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':token},params={'limit':1000,'next':cursor,'dateFrom':int(a.timestamp()),'dateTo':int(b.timestamp())},timeout=60)
   if not r.ok:raise RuntimeError('WB orders HTTP '+str(r.status_code))
   j=r.json();part=j.get('orders',[]);pages+=1
   for row in part:
    if row['id'] in rows and rows[row['id']]!=row:raise ValueError('Conflicting order')
    rows[row['id']]=row
   nxt=j.get('next')
   if not part or not nxt:break
   if nxt==cursor or pages>=20:raise ValueError('Order pagination')
   cursor=nxt
   time.sleep(1)
  ads=ad_expenses(w,first,last)
  w.save(KEY,dict(complete=True,first=first,last=last,orders=list(rows.values()),pages=pages,advertising=ads,observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0))
  print(json.dumps(dict(complete=True,orders=len(rows),pages=pages,advertising_complete=ads.get('complete'),wb_writes=0,telegram_sends=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 main()
