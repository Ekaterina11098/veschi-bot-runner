"""Targeted read-only clarification of missing31Oct expenses and selected minimums."""
import json,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import reading,allowed_read
ROOT='china_agent:owner_ad_review:2026-11-01:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
def main():
 c=Cache()
 if c.get(ROOT+':clarification'):return
 w=WB();validate_identity(c,w)
 if not c.create(ROOT+':clarification:lease',dict(at=stamp())):return
 s=c.get(ROOT+':inputs');req=c.get(ROOT+':minimums_request')
 if not s or not req or s.get('cabinet')!='token_3':raise ValueError('Source/identity missing')
 out=dict(cabinet='token_3',minimums={},errors={},wb_writes=0,telegram_sends=0,grants_action_permission=False)
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  if url.startswith(c.url) and (method.upper()=='GET' or method.upper() in ['POST','PATCH'] and str((kw.get('json')or{}).get('cache_key','')).startswith(ROOT)):return original(session,method,url,**kw)
  if allowed_read(method,url,kw.get('json')):return original(session,method,url,**kw)
  raise ValueError('Non-read request blocked')
 requests.sessions.Session.request=guard
 try:
  with reading():
   ids=sorted(int(k) for k in s['campaigns'])
   for label,begin,end in [('single31','2026-10-31','2026-10-31'),('through1nov','2026-10-30','2026-11-01')]:
    try:out[label]=dict(rows=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate='+begin+'&endDate='+end),observed_at=stamp())
    except Exception as ex:out['errors'][label]=type(ex).__name__
   for g in req['groups']:
    try:out['minimums'][str(g['cid'])+':'+g['zone']]=dict(values=w.minimums(g['cid'],g['nms'],g['zone']),observed_at=stamp())
    except Exception as ex:out['errors'][str(g['cid'])+':'+g['zone']]=type(ex).__name__
  out.update(status='complete' if not out['errors'] else 'partial',completed_at=stamp())
  if not c.create(ROOT+':clarification',out) or c.get(ROOT+':clarification')!=out:raise ValueError('Readback mismatch')
  print(json.dumps(dict(status=out['status'],wb_writes=0,telegram_sends=0)))
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()

