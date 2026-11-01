"""Owner inventory list: current China catalogue and completed-day order frequency."""
import json,time,requests
from datetime import datetime,date,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_wb_evidence import Reports
ROOT='china_agent:owner_pasted_regular_orders:2026-11-01:v1'
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
 req=c.get(ROOT+':request')
 if not req or not req['read_only']or req['cabinet']!='token_3'or not 1<=len(req['articles'])<=150:raise ValueError('Exact scoped request required')
 if not c.create(ROOT+':lease',dict(started_at=stamp())):return
 wb=WB();validate_identity(c,wb);original=requests.sessions.Session.request
 def guard(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper()
  db=u.scheme=='https'and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/')and(m=='GET'or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  read=u.scheme=='https'and m=='POST'and((u.hostname=='content-api.wildberries.ru'and u.path=='/content/v2/get/cards/list')or(u.hostname=='seller-analytics-api.wildberries.ru'and u.path=='/api/analytics/v3/sales-funnel/products'))
  if not(db or read):raise PermissionError('Only scoped catalogue and funnel reads')
  return original(session,method,url,*a,**kw)
 requests.sessions.Session.request=guard
 try:
  cards={};cursor={'limit':100}
  for page in range(10):
   r=requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list',headers={'Authorization':wb.token},json={'settings':{'cursor':cursor,'filter':{'withPhoto':-1}}},timeout=55);r.raise_for_status();j=r.json()
   if not isinstance(j.get('cards'),list):raise ValueError('Catalogue unavailable')
   for x in j['cards']:
    if x['nmID']in cards:raise ValueError('Catalogue pagination duplicate')
    cards[x['nmID']]=dict(nm_id=x['nmID'],article=x['vendorCode'])
   nxt=j.get('cursor',{})
   if nxt.get('total',100)<100:break
   cursor=dict(limit=100,updatedAt=nxt['updatedAt'],nmID=nxt['nmID']);time.sleep(1)
  else:raise ValueError('Catalogue incomplete')
  if not cards:raise ValueError('Empty catalogue not proof of absence')
  byarticle={}
  for x in cards.values():byarticle.setdefault(x['article'].strip().casefold(),[]).append(x)
  matched=[];absent=[];ambiguous=[]
  for text in req['articles']:
   found=byarticle.get(text.strip().casefold(),[])
   if len(found)==1:matched.append(dict(found[0],requested_article=text))
   elif not found:absent.append(text)
   else:ambiguous.append(dict(requested_article=text,matches=found))
  state=dict(status='collecting',cabinet='token_3',catalogue_observed_at=stamp(),catalogue_count=len(cards),matched=matched,not_found=absent,ambiguous=ambiguous,days={},wb_writes=0,telegram_calls=0,grants_action_permission=False)
  c.put(ROOT+':checkpoint',state)
  for day in req['periods']:
   for attempt in range(12):
    f=Reports(State(c)).funnel(day,day)
    if f.get('complete')and f.get('period_from')==f.get('period_to')==day:
     if str(datetime.fromisoformat(f['observed_at']).astimezone(ZoneInfo('Europe/Moscow')).date())<=day:raise ValueError('Intraday cache cannot establish full day')
     break
    retry=f.get('retry_at');delay=max(2,(datetime.fromisoformat(retry)-datetime.now(timezone.utc)).total_seconds()+1)if retry else 22
    if delay>50:raise ValueError('Funnel cooldown too long')
    time.sleep(delay)
   else:raise ValueError('Daily funnel incomplete')
   state['days'][day]=f;c.put(ROOT+':checkpoint',state)
  result=[]
  for x in matched:
   ds={};missing=[]
   for day,f in state['days'].items():
    found=[r for r in f['rows']if r['nm_id']==x['nm_id']]
    if len(found)!=1:missing.append(day);ds[day]=None;continue
    ds[day]=dict(orders=found[0]['selected']['orders'],buyouts=found[0]['selected']['buyouts'],amount=found[0]['selected']['order_amount_cny'],opens=found[0]['selected']['clicks'],carts=found[0]['selected']['cart_count'])
   counts=[v['orders']for v in ds.values()if v is not None]
   if any(type(v)is not int or v<0 for v in counts):raise ValueError('Invalid daily order counter')
   classification='unknown_daily'if missing else('regular_3_of_3'if all(v>0 for v in counts)else'intermittent'if any(v>0 for v in counts)else'zero_3_days')
   result.append(dict(x,daily=ds,missing_days=missing,classification=classification,orders_total=sum(counts)if not missing else None,days_with_orders=sum(v>0 for v in counts)))
  counts={k:sum(r['classification']==k for r in result)for k in ['regular_3_of_3','intermittent','zero_3_days','unknown_daily']}
  out=dict(status='complete',cabinet='token_3',observed_at=stamp(),catalogue_observed_at=state['catalogue_observed_at'],catalogue_count=len(cards),requested_count=len(req['articles']),matched_count=len(matched),not_found=absent,ambiguous=ambiguous,counts=counts,rows=result,periods=req['periods'],source_keys={day:dict(key=f['source_key'],observed_at=f['observed_at'])for day,f in state['days'].items()},definition=req['definition'],wb_writes=0,telegram_calls=0,grants_action_permission=False)
  if not c.create(ROOT+':result',out)or c.get(ROOT+':result')!=out:raise ValueError('Private readback mismatch')
  print(json.dumps(dict(status=out['status'],matched=len(matched),not_found=len(absent),counts=counts,wb_writes=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

