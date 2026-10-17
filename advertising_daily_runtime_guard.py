"""Pure activation guards; no source or delivery calls."""
from datetime import datetime
def membership_cache_valid(snapshot,now):
 if not isinstance(snapshot,dict):return False
 try:age=(now-datetime.fromisoformat(snapshot['collected_at'].replace('Z','+00:00'))).total_seconds()
 except (KeyError,TypeError,ValueError):return False
 return 0<=age<21600

def recoverable_initial_day(state):
 return (isinstance(state,dict) and state.get('day')=='2026-10-16'
  and state.get('run_id')=='38855942470:1' and state.get('status')=='incomplete'
  and state.get('failed_stage')=='budgets' and not state.get('recovery')
  and [s.get('name') for s in state.get('stages',[])]==['source','source_gaps','membership'])

# Daily state helpers stay pure so budget-only continuation can be tested offline.
def independent_statuses(state):
 stages=state.get('stages') or []
 def last(name):return next((r for r in reversed(stages) if r.get('name')==name),{})
 a=last('analysis_and_delivery');v=a.get('result') or {}
 state['analysis_status']='complete' if v.get('analysis_saved') is True or (a.get('status')=='complete' and not v.get('reason')) else ('failed' if a.get('status')=='failed' else 'incomplete')
 state['notification_status']=('incomplete' if v.get('delivery_unconfirmed_count',0) else ('complete' if state['analysis_status']=='complete' else 'not_evaluated'))
 b=last('budget_completion') or last('budgets')
 state['budget_status']='complete' if b.get('status')=='complete' else ('failed' if b.get('status')=='failed' else 'pending')
 state['analysis_status_scope']='saved_calculation'
 state['notification_status_scope']='confirmed_delivery_receipts'
 state['zero_messages_is_quality_acceptance']=False
 state['analysis_complete']=state['analysis_status']=='complete'
 return state

def merge_telemetry(state,attempt,stage,metric):
 import copy
 ledger=state.setdefault('telemetry',{'attempts':{},'measurement':'decoded HTTP response bytes; request bodies separately; wire bytes unknown'})
 stages=ledger['attempts'].setdefault(attempt,{});old=stages.get(stage)
 if old is not None and old!=metric:raise RuntimeError('Immutable stage telemetry changed')
 stages[stage]=copy.deepcopy(metric)
 all_metrics=[m for a in ledger['attempts'].values() for m in a.values()]
 ledger['attempt_totals']={a:{field:sum(m.get(field,0) for m in items.values()) for field in ('calls','decoded_response_bytes','request_body_bytes')} for a,items in ledger['attempts'].items()}
 ledger['stage_totals']={name:{field:sum(items.get(name,{}).get(field,0) for items in ledger['attempts'].values()) for field in ('calls','decoded_response_bytes','request_body_bytes')} for name in {name for items in ledger['attempts'].values() for name in items}}
 ledger['decoded_response_bytes']=sum(m.get('decoded_response_bytes',0) for m in all_metrics)
 ledger['request_body_bytes']=sum(m.get('request_body_bytes',0) for m in all_metrics)
 ledger['calls']=sum(m.get('calls',0) for m in all_metrics)
 ledger['coverage_complete']=all(m.get('complete') is True and not m.get('failed_calls') and not m.get('in_flight') for m in all_metrics) and not ledger.get('legacy_unmeasured',False)
 return ledger

def budget_pending(payload,active,now):
 from datetime import datetime
 def fresh(item):
  try:return item.get('available') is True and 0<=(now-datetime.fromisoformat(item['observed_at'].replace('Z','+00:00'))).total_seconds()<21600
  except (KeyError,TypeError,ValueError):return False
 items={int(x['campaign_id']):x for x in payload.get('items',[])}
 pending=[int(cid) for cid in active if not fresh(items.get(int(cid),{}))]
 due=payload.get('next_retry_at')
 if due:
  datetime.fromisoformat(due.replace('Z','+00:00')) # fail closed on malformed provider time
 return dict(campaign_ids=list(active),pending_campaign_ids=pending,next_allowed_at=due,
  requests=[dict(campaign_id=cid,next_allowed_at=due,last_observed_at=items.get(cid,{}).get('observed_at'),current_value_unknown=True) for cid in pending],
  historical_values_are_not_current=True,complete=not pending)

class StageTraffic:
 """One subprocess record. No URL queries, tokens, or response bodies are recorded."""
 def __init__(self,path,baseline=0,limit=100000000):
  from pathlib import Path
  self.path=Path(path);self.baseline=baseline;self.limit=limit;self.cleanup=0
  self.value=dict(calls=0,decoded_response_bytes=0,request_body_bytes=0,failed_calls=0,buckets={},complete=False,in_flight=False)
 def persist(self):
  import json,os
  self.path.parent.mkdir(parents=True,exist_ok=True)
  tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.value),encoding='utf-8');os.replace(tmp,self.path)
 def request(self,native,session,method,url,*args,**kw):
  from urllib.parse import urlsplit
  host=urlsplit(url).hostname or 'unknown'
  if host=='mcp.mpstats.io' and self.baseline+self.value['decoded_response_bytes']>=self.limit:
   p=(kw.get('json') or {}).get('params') or {};a=p.get('arguments') or {}
   if p.get('name')=='lk_wb_cabinets' and a.get('action') in ('select','reset') and self.cleanup<2:self.cleanup+=1
   else:raise RuntimeError('100MB cumulative decoded-body collection threshold')
  self.value['calls']+=1;self.value['in_flight']=True;self.persist()
  response=None
  try:
   response=native(session,method,url,*args,**kw)
   n=len(response.content);body=getattr(getattr(response,'request',None),'body',None)
   size=len(body.encode('utf-8') if isinstance(body,str) else body) if isinstance(body,(str,bytes,bytearray)) else 0
   self.value['decoded_response_bytes']+=n;self.value['request_body_bytes']+=size
   bucket=self.value['buckets'].setdefault(host+':'+method.upper(),dict(calls=0,decoded_response_bytes=0,request_body_bytes=0))
   bucket['calls']+=1;bucket['decoded_response_bytes']+=n;bucket['request_body_bytes']+=size
   return response
  except BaseException:
   self.value['failed_calls']+=1;raise
  finally:
   self.value['in_flight']=False;self.persist()

def run_instrumented(filename,path,baseline):
 import requests,runpy
 meter=StageTraffic(path,int(baseline));native=requests.sessions.Session.request
 def request(session,method,url,*args,**kwargs):return meter.request(native,session,method,url,*args,**kwargs)
 requests.sessions.Session.request=request;meter.persist()
 try:runpy.run_path(filename,run_name='__main__')
 finally:
  meter.value['complete']=True;meter.persist();requests.sessions.Session.request=native

if __name__=='__main__':
 import sys
 if len(sys.argv)!=5 or sys.argv[1]!='--stage':raise SystemExit('Instrumented stage arguments required')
 run_instrumented(sys.argv[2],sys.argv[3],sys.argv[4] if len(sys.argv)>4 else '0')
