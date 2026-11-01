"""Add today's partial all-source funnel orders to the owner's eight regular articles."""
import json,time,requests
from datetime import datetime,date,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_wb_evidence import Reports
BASE='china_agent:owner_pasted_regular_orders:2026-11-01:v1'
ROOT=BASE+':today'
class State:
 def __init__(self,c):self.c=c
 def get(self,k):return self.c.get(k)
 def save(self,k,v):self.c.put(k,v);return True
 def db(self,method,table,params=None,body=None,prefer=None):
  if table!='telegram_api_cache':raise PermissionError('Cache only')
  return self.c.req(method,params,body,prefer)
def main():
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Expired')
 c=Cache()
 if c.get(ROOT+':result'):return
 original_result=c.get(BASE+':result')
 if not original_result or original_result.get('status')!='complete':raise ValueError('Prior exact owner table required')
 if not c.create(ROOT+':lease',dict(started_at=stamp())):return
 wb=WB();validate_identity(c,wb);original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper()
  db=u.scheme=='https'and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/')and(m=='GET'or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  read=u.scheme=='https'and u.hostname=='seller-analytics-api.wildberries.ru'and u.path=='/api/analytics/v3/sales-funnel/products'and m=='POST'
  if not(db or read):raise PermissionError('Today report is read-only')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  for attempt in range(12):
   f=Reports(State(c)).funnel('2026-11-01','2026-11-01')
   if f.get('complete'):break
   retry=f.get('retry_at');delay=max(2,(datetime.fromisoformat(retry)-datetime.now(timezone.utc)).total_seconds()+1)if retry else 22
   if delay>50:raise ValueError('Cooldown too long')
   time.sleep(delay)
  if not f.get('complete'):raise ValueError('Today funnel incomplete')
  rows=[]
  for x in original_result['rows']:
   if x['classification']!='regular_3_of_3':continue
   matches=[r for r in f['rows']if r['nm_id']==x['nm_id']]
   rows.append(dict(x,today=matches[0]['selected']if len(matches)==1 else None))
  out=dict(status='complete',cabinet='token_3',observed_at=stamp(),today_observed_at=f['observed_at'],today_source_key=f['source_key'],rows=rows,source_key=BASE+':result',today_is_partial=True,update_delay_hours=2,wb_writes=0,telegram_calls=0,grants_action_permission=False)
  if not c.create(ROOT+':result',out)or c.get(ROOT+':result')!=out:raise ValueError('Readback')
  print(json.dumps(dict(status='complete',rows=len(rows),today_observed_at=f['observed_at'],wb_writes=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()
