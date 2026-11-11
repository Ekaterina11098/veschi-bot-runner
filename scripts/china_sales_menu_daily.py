"""Completed-day FBS created-order cache for approved Sales menu. Read-only WB; no Telegram."""
import os,time,json
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:sales_menu:v1:'
MSK=ZoneInfo('Europe/Moscow')
BASIS='FBS created units, all statuses, dedup id; native CNY buyer-discounted amount; not buyouts or all sales models'
def aggregate(rows):
 seen=set();by={};unknown=[]
 for r in rows:
  ident=r.get('id');nm=str(r.get('nmId'))
  if not isinstance(ident,int) or ident in seen:raise ValueError('Duplicate/missing FBS identity')
  seen.add(ident)
  if r.get('convertedCurrencyCode')!=156 or type(r.get('convertedPrice'))is not int or r['convertedPrice']<0:unknown.append(ident);continue
  v=by.setdefault(nm,dict(count=0,amount_minor=0));v['count']+=1;v['amount_minor']+=r['convertedPrice']
 out={nm:dict(count=v['count'],amount_cny=float(Decimal(v['amount_minor'])/100))for nm,v in by.items()}
 return dict(count=len(rows),amount_cny=None if unknown else float(sum(Decimal(r['convertedPrice'])for r in rows)/100),unknown_amount_ids=unknown),out
def collect(days=1):
 assert 1<=days<=28
 c=Cache();now=datetime.now(MSK);end=now.replace(hour=0,minute=0,second=0,microsecond=0);start=end-timedelta(days=days)
 needed=[start+timedelta(days=i)for i in range(days)if not (c.get(ROOT+'day:'+(start+timedelta(days=i)).date().isoformat())or{}).get('status')=='complete']
 if not needed:return dict(status='cached',days=days,wb_writes=0)
 lease=ROOT+'collection:'+end.date().isoformat()+':'+str(days)
 old=c.get(lease)
 if old and old.get('status')in ('reading','complete'):return dict(status='already_claimed',wb_writes=0)
 if old:return dict(status='prior_failure_no_blind_retry',wb_writes=0)
 assert c.create(lease,dict(status='reading',started_at=stamp(),wb_writes=0))
 w=WB();validate_identity(c,w)
 def get(path,params=None):
  assert path in ('/api/v3/orders','/api/v3/orders/new')
  time.sleep(1)
  r=requests.get('https://marketplace-api.wildberries.ru'+path,headers={'Authorization':w.token},params=params,timeout=45)
  if not r.ok:raise RuntimeError('FBS menu read HTTP '+str(r.status_code))
  j=r.json();assert isinstance(j.get('orders'),list);return j
 try:
  # One bounded period request, paginated by the native next cursor.
  raw={};cursor=0;pages=0
  begin=min(needed)
  while True:
   page=get('/api/v3/orders',dict(limit=1000,next=cursor,dateFrom=int(begin.timestamp()),dateTo=int(end.timestamp())))
   pages+=1;batch=page['orders']
   for r in batch:
    ident=r.get('id');assert type(ident)is int
    if ident in raw and raw[ident]!=r:raise ValueError('Conflicting FBS row')
    raw[ident]=r
   nxt=page.get('next')
   if not batch or nxt in (None,0) or len(batch)<1000:break
   if nxt==cursor or pages>=30:raise ValueError('Incomplete FBS pagination')
   cursor=nxt
  new=get('/api/v3/orders/new')['orders']
  for r in new:raw[r['id']]=r
  observed=stamp();written=[]
  for a in needed:
   b=a+timedelta(days=1);rows=[]
   for r in raw.values():
    t=datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(MSK)
    if a<=t<b:rows.append(r)
   totals,by=aggregate(rows);key=ROOT+'day:'+a.date().isoformat()
   value=dict(status='complete'if not totals['unknown_amount_ids']else'partial',cabinet='token_3',currency='CNY',basis=BASIS,date=str(a.date()),start_msk=a.isoformat(),end_msk=b.isoformat(),observed_at=observed,totals=totals,by_nm=by,source=dict(endpoint='/api/v3/orders + /api/v3/orders/new',period_from=begin.isoformat(),period_to=end.isoformat(),pages=pages,scope='created_at exact full Moscow days, all statuses, id dedup'),wb_writes=0)
   assert c.create(key,value);written.append(key)
  c.put(lease,dict(status='complete',source_keys=written,observed_at=observed,wb_writes=0));return dict(status='complete',completed_days=len(written),wb_writes=0)
 except Exception:
  c.put(lease,dict(status='failed',reason='Completed-day cache collection incomplete; no marketplace mutations',at=stamp(),wb_writes=0));raise
if __name__=='__main__':print(json.dumps(collect(28)))
