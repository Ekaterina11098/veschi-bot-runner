"""Bounded read-only price review; exact source is retained in the analysis journal."""
import copy,json
from bounded_sol_dialog import BoundedSol
from china_no_paid import require_paid_api

def compact(payload):
 p=copy.deepcopy(payload);d=p['data'];s=d['completed_source']
 actions=d.get('allowed_actions',{})
 nms={str(a.get('nm_id'))for a in actions.values()if a.get('nm_id')}
 cids={str(a.get('campaign_id'))for a in actions.values()if a.get('campaign_id')}
 products=s.get('products',{})
 s['products']={k:v for k,v in products.items()if str(v.get('nm_id'))in nms}
 eco=s.get('economics')or{};eco['rows']={k:v for k,v in eco.get('rows',{}).items()if k in nms};s['economics']=eco
 s['catalogue']={'rows':[r for r in s.get('catalogue',{}).get('rows',[])if str(r.get('nmID'))in nms]}
 s['current_campaigns']=[dict(c,nm_settings=[n for n in c.get('nm_settings',[])if str(n.get('nm_id'))in nms])for c in s.get('current_campaigns',[])if str(c.get('id'))in cids]
 for key in ('addition_scan','growth_inputs_scope'):s.pop(key,None)
 obs=d.get('intraday_observation')or{}
 d['intraday_observation']={k:obs[k]for k in ('day','observed_at','recommendation_basis')if k in obs}
 p['work_notes']=[]
 p['context_scope']='Review all exact prevalidated allowed actions with completed-day metrics/economics; full catalogue deterministic scan retained privately. No new research actions in this bounded review; return research empty. Missing evidence remains unavailable, not zero.'
 return p

def ask(core,identity,payload,validate,rules,root,digest,stamp,parse,message,model):
 require_paid_api(core.db.get('china_agent:codex_cloud:v1:policy')or{})
 payload=dict(payload,transport='responses_bounded_advertising_v1')
 fingerprint=digest(payload);key=root+digest([identity,fingerprint])
 state=core.db.get(key)
 receipt=dict(key=key,source_sha256=fingerprint,model=model,source_channel='codex_cloud',transport='responses_bounded_advertising_v1')
 if state and state.get('status')=='complete':return validate(copy.deepcopy(state['result'])),receipt
 token='advertising-bounded-'+fingerprint
 client=BoundedSol(core.db,root+'bounded:')
 if state:
  raw=client.recover(token)
 else:
  state=dict(status='starting',identity=identity,kind='advertising',source_sha256=fingerprint,created_at=stamp(),model=model,wb_action_permission=False,transport='responses_bounded_advertising_v1')
  core.db.once(key,state)
  try:
   raw=client.answer(token,rules,message(compact(payload)))
  except Exception as ex:
   state.update(status='attention_required',error_type=type(ex).__name__,error=str(ex)[:250],failed_at=stamp())
   core.db.update(key,state);raise
 completion=core.db.get(key+':completion')
 if completion:
  if completion.get('text')!=raw:raise ValueError('Immutable completion changed')
 else:core.db.once(key+':completion',dict(text=raw,observed_at=stamp()))
 try:value=validate(parse(raw))
 except Exception:
  state.update(status='invalid_output',finished_at=stamp());core.db.update(key,state);raise
 state.update(status='complete',result=value,completed_at=stamp(),source_channel='codex_cloud')
 core.db.update(key,state)
 return value,receipt


