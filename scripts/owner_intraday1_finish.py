"""Resume the privately checkpointed read; never repeat completed input calls."""
import json,requests,time
from datetime import datetime,date,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import reading,allowed_read
from china_moysklad_read import read_stock
ROOT='china_agent:owner_intraday_review:2026-11-01:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 c=Cache()
 if c.get(ROOT+':inputs'):return
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Expired dated reader')
 state=c.get(ROOT+':checkpoint');old=c.get('china_agent:owner_report_review:2026-11-01:v2:inputs')
 if not state or 'today' not in state or 'prices' not in state['inputs']:raise ValueError('Completed statistics and prices required')
 if not c.create(ROOT+':finish2_lease',dict(started_at=stamp())):return
 w=WB();validate_identity(c,w);original=requests.sessions.Session.request
 def save():
  value=json.loads(json.dumps(state))
  try:c.put(ROOT+':checkpoint',value)
  except RuntimeError as ex:
   if str(ex)!='Private state HTTP 500':raise
   if c.get(ROOT+':checkpoint')==value:return
   time.sleep(2);c.put(ROOT+':checkpoint',value)
 def guard(session,method,url,**kw):
  if url.startswith(c.url) and method.upper() in ['GET','POST','PATCH']:return original(session,method,url,**kw)
  body=kw.get('json')
  if url=='https://marketplace-api.wildberries.ru/api/v3/stocks/2126188' and method.upper()=='POST' and isinstance(body,dict) and set(body)=={'chrtIds'} and 0<len(body['chrtIds'])<=1000 and all(type(x)is int and x>0 for x in body['chrtIds']):return original(session,method,url,**kw)
  if allowed_read(method,url,body):return original(session,method,url,**kw)
  raise ValueError('External write blocked')
 requests.sessions.Session.request=guard
 try:
  with reading():
   prices=state['inputs']['prices']['rows']
   if 'stock' not in state['inputs']:
    state['inputs']['stock']=read_stock(sorted({p['article'] for p in prices}));save()
   state['inputs']['products']=old['inputs']['products'];state['inputs']['fx']=old['inputs']['fx']
   # Read the one eligible growth candidate; use its exact product size identity.
   if 'published_stock' not in state:
    from china_advertising_state import AdvertisingIO
    io=AdvertisingIO();raw=io.prices([1535337769]);g=raw['1535337769'];sizes=[dict(nm_id=1535337769,size_id=s['sizeID']) for s in g['sizes']]
    rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':w.token},json={'chrtIds':[s['size_id'] for s in sizes]},timeout=50);rr.raise_for_status()
    state['published_stock']=dict(rows=rr.json()['stocks'],sizes=sizes,observed_at=stamp());save()
   state.setdefault('minimums',{})
   for cp in state['inputs']['campaigns']['rows']:
    if cp['status']!=9 or cp['settings'].get('payment_type')!='cpc':continue
    for zone,on in cp['settings']['placements'].items():
     key=str(cp['id'])+':'+zone
     if on and zone in ['search','recommendations'] and key not in state['minimums']:
      state['minimums'][key]=w.minimums(cp['id'],[n['nm_id'] for n in cp['nm_settings']],zone);save()
   state['minimums_at']=stamp()
   ids=[cp['id'] for cp in state['inputs']['campaigns']['rows']]
   state['inputs']['budgets']=dict(w.req('/api/advert/v2/budget','POST',dict(advertIds=ids)),observed_at=stamp());save()
  state.update(status='complete',completed_at=stamp());state=json.loads(json.dumps(state))
  if not c.create(ROOT+':inputs',state) or c.get(ROOT+':inputs')!=state:raise ValueError('Private readback mismatch')
  print(json.dumps(dict(status=state['status'],campaigns=len(ids),wb_writes=0,telegram_sends=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

