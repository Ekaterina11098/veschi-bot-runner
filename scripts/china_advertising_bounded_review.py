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
 eco['missing']={k:v for k,v in eco.get('missing',{}).items()if str(k)in nms}
 s['changes']=[x for x in s.get('changes',[])if str(x.get('nm'))in nms or str(x.get('campaign_id'))in cids]
 report=d.get('report')or{}
 report['campaigns']=[dict(c,focus=[r for r in c.get('focus',[])if r.get('action_id')in actions])for c in report.get('campaigns',[])if str(c.get('id'))in cids]
 d['report']=report
 d['candidate_evidence']={k:v for k,v in d.get('candidate_evidence',{}).items()if k in actions}
 blocks=d.get('readiness_blocks',[])
 d['readiness_blocks']={'excluded_not_ready_count':len(blocks),'scope':'Not actionable; missing evidence is not absence of opportunities'}
 s['catalogue']={'rows':[r for r in s.get('catalogue',{}).get('rows',[])if str(r.get('nmID'))in nms]}
 s['current_campaigns']=[dict(c,nm_settings=[n for n in c.get('nm_settings',[])if str(n.get('nm_id'))in nms])for c in s.get('current_campaigns',[])if str(c.get('id'))in cids]
 for key in ('addition_scan','growth_inputs_scope'):s.pop(key,None)
 obs=d.get('intraday_observation')or{}
 d['intraday_observation']={k:obs[k]for k in ('day','observed_at','recommendation_basis')if k in obs}
 p['work_notes']=[]
 p['context_scope']='Review all exact prevalidated allowed actions with completed-day metrics/economics; full catalogue deterministic scan retained privately. No new research actions in this bounded review; return research empty. Missing evidence remains unavailable, not zero.'
 return p

def ask_one(core,identity,payload,validate,rules,root,digest,stamp,parse,message,model):
 require_paid_api(core.db.get('china_agent:codex_cloud:v1:policy')or{})
 payload=dict(payload,transport='responses_bounded_advertising_v2')
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
   raw=client.answer(token,rules,message(payload))
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

def ask(core,identity,payload,validate,rules,root,digest,stamp,parse,message,model):
 """Review every candidate in bounded groups; retain exact actions and evidence."""
 actions=payload['data'].get('allowed_actions',{})
 groups=[];current={}
 def subset(items):
  p=copy.deepcopy(payload);p['data']['allowed_actions']=items
  return compact(p)
 for key,action in actions.items():
  trial=dict(current,**{key:action})
  if current and len(message(subset(trial)))+len(rules)>29000:
   groups.append(current);current={key:action}
  else:current=trial
 groups.append(current)
 values=[];receipts=[]
 for index,group in enumerate(groups):
  p=subset(group)
  p['context_scope']+=' This is candidate group '+str(index+1)+'/'+str(len(groups))+'. Coverage conclusions apply only to this group; do not claim the whole catalogue has no candidates.'
  def check(v):
   v=validate(v)
   if any(r['id']not in group for r in v['decisions']):raise ValueError('Decision outside candidate group')
   if v.get('research'):raise ValueError('Bounded review cannot invent research actions')
   return v
  value,receipt=ask_one(core,identity+':group:'+str(index),p,check,rules,root,digest,stamp,parse,message,model)
  values.append(value);receipts.append(receipt)
 result=dict(kind='advertising_review',decisions=[r for v in values for r in v['decisions']],research=[],summary='; '.join(v.get('summary','')for v in values),directions={})
 for direction in ('raise','add','reduce','exclude'):
  rows=[v['directions'][direction]for v in values]
  result['directions'][direction]=dict(status='unavailable'if any(r['status']=='unavailable'for r in rows)else'checked',note=('Candidate groups only; unready catalogue evidence remains private. '+'; '.join(r['note']for r in rows))[:3000])
 return validate(result),dict(identity=identity,transport='responses_bounded_advertising_v2',source_sha256=digest(payload),groups=receipts,model=model)