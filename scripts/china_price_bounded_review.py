"""Bounded read-only price review; exact source is retained in the analysis journal."""
import copy,json
from bounded_sol_dialog import BoundedSol
from china_no_paid import require_paid_api

def compact(payload):
 p=copy.deepcopy(payload);d=p['data'];s=d['completed_source']
 text='\n'.join(d.get('rows',{}).values())
 selected=[r for r in s.get('financial_rows',[]) if r.get('sa_name') and r['sa_name'] in text]
 ids={str(r['nm_id']) for r in selected}
 assessment=s.get('assessment')or{}
 results=assessment.get('results')or{}
 s['financial_row_count']=len(s.get('financial_rows',[]))
 s['financial_rows']=selected
 s['assessment']=dict(assessment,results={k:v for k,v in results.items() if k in ids or (v.get('article') and v['article'] in text)})
 if d.get('rows') and not selected:raise ValueError('Draft candidates could not be bound to financial evidence')
 s['model_scope']='Exact draft candidates only; full catalogue evidence retained privately. Do not infer no other opportunities.'
 d.pop('draft_evidence',None)
 p['work_notes']=[] # Contract rules and source-specific decisions remain; unrelated notes are not report evidence.
 p['context_scope']='Exact price candidates, original immutable rows, completed-period evidence and report rules.'
 return p

def ask(core,identity,payload,validate,rules,root,digest,stamp,parse,message,model):
 require_paid_api(core.db.get('china_agent:codex_cloud:v1:policy')or{})
 payload=dict(payload,transport='responses_bounded_price_v1')
 fingerprint=digest(payload);key=root+digest([identity,fingerprint])
 state=core.db.get(key)
 receipt=dict(key=key,source_sha256=fingerprint,model=model,source_channel='codex_cloud',transport='responses_bounded_price_v1')
 if state and state.get('status')=='complete':return validate(copy.deepcopy(state['result'])),receipt
 token='price-bounded-'+fingerprint
 client=BoundedSol(core.db,root+'bounded:')
 if state:
  raw=client.recover(token)
 else:
  state=dict(status='starting',identity=identity,kind='price',source_sha256=fingerprint,created_at=stamp(),model=model,wb_action_permission=False,transport='responses_bounded_price_v1')
  core.db.once(key,state)
  try:
   raw=client.answer(token,rules,message(compact(payload)))
  except Exception as ex:
   state.update(status='attention_required',error_type=type(ex).__name__,error=str(ex)[:250],failed_at=stamp())
   core.db.update(key,state);raise
 core.db.once(key+':completion',dict(text=raw,observed_at=stamp()))
 try:value=validate(parse(raw))
 except Exception:
  state.update(status='invalid_output',finished_at=stamp());core.db.update(key,state);raise
 state.update(status='complete',result=value,completed_at=stamp(),source_channel='codex_cloud')
 core.db.update(key,state)
 return value,receipt


