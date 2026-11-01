"""Resume only missing read-only minima and current budgets; reuse completed own inputs."""
import copy,json,requests
from datetime import datetime,date,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import reading,allowed_read
ROOT='china_agent:owner_report_review:2026-11-01:v2'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 c=Cache()
 if c.get(ROOT+':inputs'):return
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Dated review expired')
 state=c.get(ROOT+':checkpoint')
 if not state or set(state.get('inputs',{}))!={'fx','stock','prices','products','campaigns'}:raise ValueError('Completed independent input checkpoint required')
 if not c.create(ROOT+':finish_lease',dict(started_at=stamp(),wb_writes=0)):return
 w=WB();validate_identity(c,w);original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  if url.startswith(c.url) and method.upper() in ['GET','POST','PATCH']:return original(session,method,url,**kw)
  if allowed_read(method,url,kw.get('json')):return original(session,method,url,**kw)
  raise ValueError('External write blocked')
 requests.sessions.Session.request=guard
 def save():c.put(ROOT+':checkpoint',json.loads(json.dumps(state)))
 try:
  with reading():
   for cp in state['inputs']['campaigns']['rows']:
    if cp['status']!=9 or cp['settings'].get('payment_type')!='cpc':continue
    for zone,on in cp['settings']['placements'].items():
     key=str(cp['id'])+':'+zone
     if on and zone in ['search','recommendations'] and key not in state['minimums']:
      try:state['minimums'][key]=w.minimums(cp['id'],[n['nm_id'] for n in cp['nm_settings']],zone)
      except Exception as ex:state['errors']['minimum:'+key]=str(ex)[:150] if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__
      save()
   state['minimums_at']=stamp()
   ids=[cp['id'] for cp in state['inputs']['campaigns']['rows']]
   state['inputs']['budgets']=dict(w.req('/api/advert/v2/budget','POST',dict(advertIds=ids)),observed_at=stamp());save()
  state.update(status='complete' if not state['errors'] else 'partial',completed_at=stamp())
  value=json.loads(json.dumps(state))
  if not c.create(ROOT+':inputs',value) or c.get(ROOT+':inputs')!=value:raise ValueError('Private final readback mismatch')
  print(json.dumps(dict(status=state['status'],minimum_campaigns=len(state['minimums']),errors=state['errors'],wb_writes=0,telegram_sends=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

