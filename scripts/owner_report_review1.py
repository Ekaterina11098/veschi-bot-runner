"""Dated owner review: collect exact current inputs; no WB mutations or Telegram."""
import copy,json,os,time
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
import requests
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import Analyst,reading,allowed_read
from china_moysklad_read import read_stock
from china_advertising_state import AdvertisingIO
from china_advertising_v2 import refresh_budget_context
ROOT='china_agent:owner_report_review:2026-11-01:v2'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 c=Cache()
 if c.get(ROOT+':inputs'):return
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Dated review expired')
 if not c.create(ROOT+':lease',dict(started_at=stamp(),wb_writes=0)):return
 w=WB();validate_identity(c,w)
 source=copy.deepcopy(c.get('china_agent:advertising_source:2026-11-01:v2'))
 if not source or source.get('day_quality',{}).get('usable') is not True:raise ValueError('Completed31Oct advertising source missing')
 state=dict(status='collecting',cabinet='token_3',observed_at=stamp(),inputs={},errors={},wb_writes=0,telegram_sends=0,grants_action_permission=False)
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  if url.startswith(c.url) and method.upper() in ['GET','POST','PATCH']:return original(session,method,url,**kw)
  if allowed_read(method,url,kw.get('json')):return original(session,method,url,**kw)
  raise ValueError('Review permits only external read endpoints')
 requests.sessions.Session.request=guard
 def save():c.put(ROOT+':checkpoint',copy.deepcopy(state))
 def failure(topic,ex):
  state['errors'][topic]=str(ex)[:180] if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__;save()
 try:
  with reading():
   io=AdvertisingIO();source=refresh_budget_context(io,source,'2026-11-01')
   campaigns=w.campaigns(source['ids']);state['inputs']['campaigns']=dict(rows=list(campaigns.values()),observed_at=stamp());save()
   ids=sorted({n['nm_id'] for cp in campaigns.values() if cp['status']==9 for n in cp['nm_settings']})
   state['nm_ids']=ids
   try:
    raw=io.prices(ids);prices=[]
    for nm in ids:
     p=raw[str(nm)];values={s.get('discountedPrice') for s in p.get('sizes',[])}
     if p.get('currencyIsoCode4217')!='CNY' or len(values)!=1:continue
     price=next(iter(values))
     if type(price) not in (int,float) or price<=0:continue
     prices.append(dict(nm_id=nm,article=p['vendorCode'],currency='CNY',seller_price=price))
    state['inputs']['prices']=dict(rows=prices,observed_at=stamp(),missing_ids=sorted(set(ids)-{r['nm_id'] for r in prices}));save()
   except Exception as ex:failure('prices',ex)
   class Work:
    now=datetime.now(timezone.utc)
    def get(self,key):return c.get(key)
    def save(self,key,v):raise ValueError('Only dated review snapshots may be saved')
    def catalog(self):return [(str(p['nmID']),p['vendorCode']) for p in source['catalogue']['rows']]
   try:
    an=Analyst(Work(),dict(request_text='Закончить проверку экономики'),[])
    p=an.collect('products',[],date(2026,10,2),date(2026,10,31))
    state['inputs']['products']=dict(p,observed_at=stamp(),period_from='2026-10-02',period_to='2026-10-31');save()
   except Exception as ex:failure('products',ex)
   try:
    articles=sorted({r['article'] for r in state['inputs'].get('prices',{}).get('rows',[])})
    if not articles:raise ValueError('Exact current article list unavailable')
    state['inputs']['stock']=read_stock(articles);save()
   except Exception as ex:failure('stock',ex)
   fx=(c.get('china_agent:owner_profit_now:2026-10-31:v1:collection') or {}).get('inputs',{}).get('fx')
   if fx and fx.get('effective_date')=='2026-10-31':state['inputs']['fx']=fx
   else:state['errors']['fx']='Verified CBR31Oct source unavailable'
   state['source']=source;state['minimums']={}
   for cid,cp in campaigns.items():
    if cp['status']!=9 or cp['settings'].get('payment_type')!='cpc':continue
    nms=[n['nm_id'] for n in cp['nm_settings']]
    for zone,on in cp['settings']['placements'].items():
     if on and zone in ['search','recommendations']:
      try:state['minimums'][str(cid)+':'+zone]=w.minimums(int(cid),nms,zone)
      except Exception as ex:failure('minimum:'+str(cid)+':'+zone,ex)
    save()
   state['minimums_at']=stamp()
  state.update(status='complete' if not state['errors'] else 'partial',completed_at=stamp())
  if not c.create(ROOT+':inputs',state):raise ValueError('Review input identity already exists')
  print(json.dumps(dict(status=state['status'],topics=list(state['inputs']),errors=state['errors'],wb_writes=0,telegram_sends=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

