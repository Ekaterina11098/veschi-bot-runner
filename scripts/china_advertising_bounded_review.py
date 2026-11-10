"""Bounded read-only price review; exact source is retained in the analysis journal."""
import copy,json,os
from concurrent.futures import ThreadPoolExecutor
from bounded_sol_dialog import BoundedSol
from china_no_paid import require_paid_api
class PrefillComplete(Exception):pass

def replace_times(value,replacements):
 if isinstance(value,dict):return {k:replace_times(v,replacements)for k,v in value.items()}
 if isinstance(value,list):return [replace_times(v,replacements)for v in value]
 return replacements.get(value,value)if isinstance(value,str)else value

def compact(payload):
 p=copy.deepcopy(payload);d=p['data'];s=d['completed_source']
 actions=d.get('allowed_actions',{})
 nms={str(a.get('nm_id'))for a in actions.values()if a.get('nm_id')}
 nms.update(map(str,d.get('review_scope_nm_ids',[])))
 cids={str(a.get('campaign_id'))for a in actions.values()if a.get('campaign_id')}
 cids.update(str(c['id'])for c in s.get('current_campaigns',[])if any(str(n.get('nm_id'))in nms for n in c.get('nm_settings',[])))
 products=s.get('products',{})
 s['products']={k:v for k,v in products.items()if str(v.get('nm_id'))in nms}
 eco=s.get('economics')or{};eco['rows']={k:v for k,v in eco.get('rows',{}).items()if k in nms};s['economics']=eco
 eco['missing']={k:v for k,v in eco.get('missing',{}).items()if str(k)in nms}
 s['changes']=[x for x in s.get('changes',[])if str(x.get('nm'))in nms or (str(x.get('campaign_id'))in cids and (not d.get('relevant_changes_only')or x.get('nm')is None))]
 report=d.get('report')or{}
 report['campaigns']=[dict(c,focus=[r for r in c.get('focus',[])if r.get('action_id')in actions])for c in report.get('campaigns',[])if str(c.get('id'))in cids]
 d['report']=report
 d['candidate_evidence']={k:v for k,v in d.get('candidate_evidence',{}).items()if k in actions}
 blocks=d.get('readiness_blocks',[])
 d['readiness_blocks']={'excluded_not_ready_count':len(blocks),'scope':'Not actionable; missing evidence is not absence of opportunities'}
 s['catalogue']={'rows':[r for r in s.get('catalogue',{}).get('rows',[])if str(r.get('nmID'))in nms]}
 s['current_campaigns']=[dict(c,nm_settings=[n for n in c.get('nm_settings',[])if str(n.get('nm_id'))in nms])for c in s.get('current_campaigns',[])if str(c.get('id'))in cids]
 s.pop('addition_scan',None)
 obs=d.get('intraday_observation')or{}
 d['intraday_observation']={k:obs[k]for k in ('day','observed_at','recommendation_basis')if k in obs}
 p['work_notes']=[]
 p['context_scope']='Review every supplied SKU and all four directions using completed-day metrics/economics and current states. Full catalogue is partitioned losslessly across groups, including SKUs with no allowed actions. No new research actions in this bounded review; return research empty. Only exact prevalidated allowed actions can be selected. Owner-held SKUs must not change. Checked means this group was examined, not that a candidate exists; distinguish rejected unready candidates from an unperformed review. Missing evidence is not zero.'
 return p

def ask_one(core,identity,payload,validate,rules,root,digest,stamp,parse,message,model):
 require_paid_api(core.db.get('china_agent:codex_cloud:v1:policy')or{})
 payload=dict(payload,transport='responses_bounded_advertising_v3_full_scope')
 fingerprint=digest(payload);key=root+digest([identity,fingerprint])
 if core.db.get(key+':input')is None:core.db.once(key+':input',payload)
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
 day=(str(identity).split(':')+[''])[1]
 control=core.db.get('china_agent:advertising_midday_resume:'+day+':v1')or{} if core is not None else {}
 source=payload['data']['completed_source']
 nms=sorted({str(r['nmID'])for r in source.get('catalogue',{}).get('rows',[])}|{str(r['nm_id'])for r in source.get('products',{}).values()}|{str(a['nm_id'])for a in actions.values()if a.get('nm_id')})
 groups=[];current=[]
 def subset(ids,items=None):
  items=items if items is not None else {k:a for k,a in actions.items()if str(a.get('nm_id'))in ids}
  p=copy.deepcopy(payload);p['data']['allowed_actions']=items
  p['data']['review_scope_nm_ids']=ids
  if not control.get('enabled'):p['data']['relevant_changes_only']=True
  return compact(p)
 for nm in nms:
  trial=current+[nm]
  if current and len(message(subset(trial)))+len(rules)>27000:
   groups.append(current);current=[nm]
  else:current=trial
 if current:groups.append(current)
 funding={k:a for k,a in actions.items()if not a.get('nm_id')}
 if funding or not groups:groups.append([])
 replacements={}
 if control.get('enabled'):
  live=core.db.get(control['source_key']);frozen=control['full_input']
  def facts(v):return {k:x for k,x in v.items()if k!='observed_at'}
  if facts(live)!=facts(frozen):raise ValueError('Resume input facts changed; cached analysis cannot be reused')
  replacements[source.get('observed_at')]=control['full_observed_at']
  obs=(payload['data'].get('intraday_observation')or{}).get('observed_at')
  if obs:replacements[obs]=control['intraday_observed_at']
 def prepared(index,ids):
  group=funding if not ids else {k:a for k,a in actions.items()if str(a.get('nm_id'))in ids}
  p=subset(ids,group)
  p['context_scope']+=' This is candidate group '+str(index+1)+'/'+str(len(groups))+'. Coverage conclusions apply only to this group; do not claim the whole catalogue has no candidates.'
  return group,replace_times(p,replacements)
 if control.get('enabled'):
  _,first=prepared(0,groups[0])
  if digest(dict(first,transport='responses_bounded_advertising_v3_full_scope'))!=control['expected_first_sha']:raise ValueError('Recovery source fingerprint differs; no model submission')
 if os.environ.get('CHINA_AD_ANALYSIS_PREFILL')=='1':
  def fill(pair):
   index,ids=pair;group,p=prepared(index,ids)
   def check(v):
    v=validate(v)
    if any(r['id']not in group for r in v['decisions'])or v.get('research'):raise ValueError('Prefill outside exact group')
    return v
   return ask_one(core,identity+':group:'+str(index),p,check,rules,root,digest,stamp,parse,message,model)
  with ThreadPoolExecutor(max_workers=3)as pool:list(pool.map(fill,[(i,x)for i,x in enumerate(groups)if i>=control.get('prefill_from_group',9999)]))
  raise PrefillComplete('Remaining bounded analysis groups completed; no report delivery')
 def process(pair):
  index,ids=pair
  group,p=prepared(index,ids)
  def check(v):
   v=validate(v)
   if any(r['id']not in group for r in v['decisions']):raise ValueError('Decision outside candidate group')
   if v.get('research'):raise ValueError('Bounded review cannot invent research actions')
   return v
  value,receipt=ask_one(core,identity+':group:'+str(index),p,check,rules,root,digest,stamp,parse,message,model)
  return value,dict(receipt,scope_nm_ids=ids)
 if core is not None and not control.get('enabled'):
  with ThreadPoolExecutor(max_workers=3)as pool:results=list(pool.map(process,enumerate(groups)))
 else:results=[process(pair)for pair in enumerate(groups)]
 values=[v for v,r in results];receipts=[r for v,r in results]
 coverage_values=[v for (v,r),ids in zip(results,groups)if ids]or values
 result=dict(kind='advertising_review',decisions=[r for v in values for r in v['decisions']],research=[],summary='; '.join(v.get('summary','')for v in values),directions={})
 for direction in ('raise','add','reduce','exclude'):
  rows=[v['directions'][direction]for v in coverage_values]
  result['directions'][direction]=dict(status='unavailable'if any(r['status']=='unavailable'for r in rows)else'checked',note=('Candidate groups only; unready catalogue evidence remains private. '+'; '.join(r['note']for r in rows))[:3000])
 return validate(result),dict(identity=identity,transport='responses_bounded_advertising_v3_full_scope',source_sha256=digest(payload),groups=receipts,reviewed_nm_ids=nms,model=model)