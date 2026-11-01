"""Compare exact old72 zero-order SKUs with later all-source orders; read-only."""
import json,time,requests
from datetime import datetime,date,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_wb_evidence import Reports
ROOT='china_agent:owner_zero72_followup:2026-11-01:v1'
OLD='china_agent:zero_orders:v1:2026-10-14:2026-10-27'
MSK=ZoneInfo('Europe/Moscow')
class State:
 def __init__(self,c):self.c=c
 def get(self,k):return self.c.get(k)
 def save(self,k,v):self.c.put(k,v);return True
 def db(self,method,table,params=None,body=None,prefer=None):
  if table!='telegram_api_cache':raise PermissionError('Private cache only')
  return self.c.req(method,params,body,prefer)
def main():
 if datetime.now(MSK).date()!=date(2026,11,1):raise ValueError('Expired dated comparison')
 c=Cache()
 if c.get(ROOT+':result'):return
 old=c.get(OLD)
 if not old or len(old.get('zero',[]))!=72:raise ValueError('Original72 scope unavailable')
 if not c.create(ROOT+':lease',dict(started_at=stamp())):return
 wb=WB();validate_identity(c,wb);w=State(c);original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper()
  db=u.scheme=='https' and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/') and (m=='GET' or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  read=u.scheme=='https' and ((u.hostname=='seller-analytics-api.wildberries.ru' and u.path=='/api/analytics/v3/sales-funnel/products' and m=='POST')or(u.hostname=='marketplace-api.wildberries.ru' and u.path=='/api/v3/orders' and m=='GET'))
  if not(db or read):raise PermissionError('Read-only comparison')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  for attempt in range(12):
   source=Reports(w).funnel('2026-10-28','2026-11-01')
   if source.get('complete'):break
   at=source.get('retry_at');delay=max(1,(datetime.fromisoformat(at)-datetime.now(timezone.utc)).total_seconds()+1)if at else 22
   if delay>45:raise ValueError('Source cooldown')
   time.sleep(delay)
  if not source.get('complete'):raise ValueError('All-source comparison incomplete')
  begin=datetime(2026,10,28,tzinfo=MSK);cutoff=datetime.now(MSK);cursor=0;seen=set();orders={}
  for page in range(30):
   response=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':wb.token},params=dict(limit=1000,next=cursor,dateFrom=int(begin.timestamp()),dateTo=int(cutoff.timestamp())),timeout=55);response.raise_for_status();raw=response.json();part=raw.get('orders')
   if not isinstance(part,list):raise ValueError('FBS page unavailable')
   for row in part:
    at=datetime.fromisoformat(row['createdAt'].replace('Z','+00:00')).astimezone(MSK)
    if begin<=at<cutoff:orders[row['id']]=dict(nm_id=row['nmId'],created_at=at.isoformat())
   nxt=raw.get('next')
   if not part or not nxt:break
   if nxt==cursor or nxt in seen:raise ValueError('FBS cursor incomplete')
   seen.add(cursor);cursor=nxt;time.sleep(1)
  else:raise ValueError('FBS bound exceeded')
  rows=[];by_nm={r['nm_id']:r for r in source['rows']}
  for prior in old['zero']:
   nm=prior['nm_id'];f=by_nm.get(nm);n=(f or{}).get('selected',{}).get('orders')
   if n is not None and (type(n)is not int or n<0):raise ValueError('Invalid all-source count')
   created=[r for r in orders.values()if r['nm_id']==nm]
   label='received_orders' if(n is not None and n>0)or created else'confirmed_zero'if n==0 else'unknown'
   rows.append(dict(nm_id=nm,article=prior['article'],funnel_orders=n,fbs_created=len(created),first_fbs_created=min([r['created_at']for r in created],default=None),classification=label))
  result=dict(status='complete',cabinet='token_3',old_source_key=OLD,source_key=source['source_key'],period_from='2026-10-28',period_to='2026-11-01',funnel_observed_at=source['observed_at'],observed_at=stamp(),fbs_cutoff_msk=cutoff.isoformat(),old_count=72,received_count=sum(r['classification']=='received_orders'for r in rows),zero_count=sum(r['classification']=='confirmed_zero'for r in rows),unknown_count=sum(r['classification']=='unknown'for r in rows),rows=rows,fbs_pages=page+1,includes_today_partial=True,orders_not_buyouts=True,wb_writes=0,telegram_calls=0,grants_action_permission=False)
  if not c.create(ROOT+':result',result)or c.get(ROOT+':result')!=result:raise ValueError('Private readback mismatch')
  print(json.dumps({k:result[k]for k in ['status','old_count','received_count','zero_count','unknown_count','wb_writes','telegram_calls']}))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()
