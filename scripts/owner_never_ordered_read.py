"""Owner's current-catalogue no-orders audit; all-source funnel and FBS crosscheck."""
import os,json,time,requests
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_wb_evidence import Reports
ROOT='china_agent:owner_never_ordered:2026-11-01:v1'
MSK=ZoneInfo('Europe/Moscow')
class State:
 def __init__(self,c):self.c=c
 def get(self,k):return self.c.get(k)
 def save(self,k,v):self.c.put(k,v);return True
 def db(self,method,table,params=None,body=None,prefer=None):
  if table!='telegram_api_cache':raise PermissionError('Cache only')
  return self.c.req(method,params,body,prefer)
def main():
 if datetime.now(MSK).date()!=date(2026,11,1):raise ValueError('Expired audit')
 c=Cache()
 if c.get(ROOT+':result'):return
 if not c.create(ROOT+':lease:resume3',dict(started_at=stamp())):return
 w=WB();validate_identity(c,w);state=State(c);original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper()
  db=u.hostname==urlparse(c.url).hostname and u.scheme=='https' and u.path.startswith('/rest/v1/') and (m=='GET' or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  read=u.scheme=='https' and ((u.hostname=='content-api.wildberries.ru' and u.path=='/content/v2/get/cards/list' and m=='POST')or(u.hostname=='seller-analytics-api.wildberries.ru' and u.path=='/api/analytics/v3/sales-funnel/products' and m=='POST')or(u.hostname=='marketplace-api.wildberries.ru' and u.path=='/api/v3/orders' and m=='GET'))
  if not(db or read):raise PermissionError('Audit is read-only')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  cards={};cursor={'limit':100}
  for page in range(30):
   response=requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list',headers={'Authorization':w.token},json={'settings':{'cursor':cursor,'filter':{'withPhoto':-1}}},timeout=55);response.raise_for_status();data=response.json()
   if not isinstance(data.get('cards'),list):raise ValueError('Catalogue unavailable')
   for card in data['cards']:
    if card['nmID']in cards:raise ValueError('Duplicate catalogue page')
    cards[card['nmID']]=dict(nm_id=card['nmID'],article=card['vendorCode'],created_at=card['createdAt'])
   nxt=data.get('cursor',{})
   if nxt.get('total',100)<100:break
   cursor={'limit':100,'updatedAt':nxt['updatedAt'],'nmID':nxt['nmID']};time.sleep(1)
  else:raise ValueError('Catalogue pagination incomplete')
  if not cards:raise ValueError('Empty catalogue not proof of zeros')
  first=min(datetime.fromisoformat(x['created_at'].replace('Z','+00:00')).astimezone(MSK).date()for x in cards.values());last=date(2026,11,1)
  if (last-first).days>89:raise ValueError('Catalogue history exceeds bounded90-day audit; do not claim lifetime zero')
  c.put(ROOT+':catalogue',dict(rows=list(cards.values()),complete=True,first_created=str(first),observed_at=stamp()))
  periods=[];cursor_day=first
  while cursor_day<=last:
   end=min(last,cursor_day+timedelta(days=30));periods.append((str(cursor_day),str(end)));cursor_day=end+timedelta(days=1)
  coverage=[]
  for start,end in periods:
   for retry in range(15):
    source=Reports(state).funnel(start,end)
    if source.get('complete'):break
    retry_at=source.get('retry_at')
    delay=max(1,(datetime.fromisoformat(retry_at)-datetime.now(timezone.utc)).total_seconds()+1)if retry_at else 22
    if delay>45:raise ValueError('Report cooldown exceeds bounded audit')
    time.sleep(delay)
   if not source.get('complete'):raise ValueError('Funnel incomplete')
   coverage.append(source);c.put(ROOT+':checkpoint',dict(completed_periods=[[s['period_from'],s['period_to']]for s in coverage],wb_writes=0))
  fbs={};begin=datetime.combine(first,datetime.min.time(),MSK);cutoff=datetime.now(MSK);window_start=begin;pages_total=0
  while window_start<cutoff:
   window_end=min(cutoff,window_start+timedelta(days=29));cursor=0;seen=set()
   for page in range(40):
    response=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':w.token},params=dict(limit=1000,next=cursor,dateFrom=int(window_start.timestamp()),dateTo=int(window_end.timestamp())),timeout=55);response.raise_for_status();data=response.json();pages_total+=1
    if not isinstance(data.get('orders'),list):raise ValueError('FBS page unavailable')
    for order in data['orders']:
     at=datetime.fromisoformat(order['createdAt'].replace('Z','+00:00')).astimezone(MSK)
     if begin<=at<cutoff:fbs[order['id']]=order['nmId']
    nxt=data.get('next')
    if not data['orders']or not nxt:break
    if nxt==cursor or nxt in seen:raise ValueError('FBS cursor incomplete')
    seen.add(cursor);cursor=nxt;time.sleep(1)
   else:raise ValueError('FBS pagination incomplete')
   window_start=window_end;time.sleep(1)
  fbs_counts={}
  for nm in fbs.values():fbs_counts[nm]=fbs_counts.get(nm,0)+1
  zero=[];positive=[];unknown=[]
  for nm,card in cards.items():
   total=0;missing=[]
   for source in coverage:
    if date.fromisoformat(source['period_to'])<datetime.fromisoformat(card['created_at'].replace('Z','+00:00')).astimezone(MSK).date():continue
    rows=[r for r in source['rows']if r['nm_id']==nm]
    if len(rows)!=1:missing.append((source['period_from'],source['period_to']));continue
    n=rows[0]['selected']['orders']
    if type(n)is not int or n<0:raise ValueError('Unknown all-source counter')
    total+=n
   row=dict(card,funnel_orders=total,fbs_created=fbs_counts.get(nm,0))
   if total>0 or row['fbs_created']>0:positive.append(row)
   elif missing:unknown.append(dict(row,missing_periods=missing))
   else:zero.append(row)
  result=dict(status='complete',cabinet='token_3',period_from=str(first),period_to=str(last),observed_at=stamp(),fbs_cutoff_msk=cutoff.isoformat(),catalogue_count=len(cards),zero_count=len(zero),positive_count=len(positive),unknown_count=len(unknown),zero=zero,positive=positive,unknown=unknown,source_keys=[s['source_key']for s in coverage],fbs_total_orders=len(fbs),fbs_pages=pages_total,fbs_complete=True,includes_today_partial=True,funnel_update_delay_hours=2,wb_writes=0,telegram_calls=0,grants_action_permission=False)
  result=json.loads(json.dumps(result))
  if not c.create(ROOT+':result',result)or c.get(ROOT+':result')!=result:raise ValueError('Audit readback mismatch')
  print(json.dumps({k:result[k]for k in ['status','catalogue_count','zero_count','positive_count','unknown_count','wb_writes','telegram_calls']}))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()
