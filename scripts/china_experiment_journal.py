"""Evidence-linked experiment journal and preliminary risk limits; no marketplace calls."""
import copy,hashlib,json,math
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:experiment_journal:v1:'
POLICY=ROOT+'policy'
def instant(value):
 try:
  t=datetime.fromisoformat(value.replace('Z','+00:00'))
  return t if t.tzinfo else None
 except (AttributeError,ValueError,TypeError):return None
def number(v):return type(v) in (int,float) and math.isfinite(v)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:24]
def immutable(w,key,value):
 prior=w.get(key)
 if prior is not None:return prior
 if hasattr(w,'save'):
  try:w.save(key,value,insert=True)
  except TypeError:w.save(key,value)
 else:w.create(key,value)
 saved=w.get(key)
 if saved!=value:raise ValueError('Experiment journal immutable readback failed')
 return saved
def receipt_changes(key,receipt,labels=None):
 """A campaign receipt affects only changed members/bids, never all its SKUs."""
 if receipt.get('status')!='verified':return []
 before,after=receipt.get('before'),receipt.get('after')
 if receipt.get('kind')=='price_change':
  if receipt.get('cabinet')!='token_3' or not isinstance(before,dict) or not isinstance(after,dict) or before.get('nmID')!=after.get('nmID') or type(after.get('nmID'))is not int:return []
  if any(p.get('currencyIsoCode4217')!='CNY' for p in (before,after)):return []
  prices=[{z.get('discountedPrice') for z in p.get('sizes',[])} for p in (before,after)]
  if any(len(p)!=1 for p in prices):return []
  old,new=[next(iter(p)) for p in prices]
  started=receipt.get('submitted_at') or receipt.get('verified_at')
  if not all(number(p) and p>0 for p in (old,new)) or old==new or not instant(started):return []
  return [dict(nm_id=after['nmID'],kind='price',before=old,after=new,currency='CNY',article=after.get('vendorCode'),source_key=key,record_type='verified_action',at=started,at_basis='submitted_at' if receipt.get('submitted_at') else 'first_verified_readback',verified_at=receipt.get('verified_at'),grants_action_permission=False)]
 if not isinstance(before,dict) or not isinstance(after,dict) or before.get('id')!=after.get('id') or type(after.get('id'))is not int:return []
 started=receipt.get('submitted_at') or receipt.get('created_at') or receipt.get('verified_at')
 if not instant(started):return []
 old={n['nm_id']:n for n in before.get('nm_settings',[])}
 new={n['nm_id']:n for n in after.get('nm_settings',[])}
 changes=[]
 for nm in sorted(set(old)|set(new)):
  if nm not in old or nm not in new:
   changes.append(dict(nm_id=nm,campaign_id=after['id'],kind='membership_add' if nm in new else 'membership_remove',before=nm in old,after=nm in new))
   continue
  a,b=old[nm].get('bids_kopecks',{}),new[nm].get('bids_kopecks',{})
  for placement in sorted(set(a)|set(b)):
   if a.get(placement)!=b.get(placement):
    changes.append(dict(nm_id=nm,campaign_id=after['id'],kind='bid',placement=placement,before=a.get(placement),after=b.get(placement)))
 return [dict(change,source_key=key,record_type='verified_action',at=started,verified_at=receipt.get('verified_at'),article=(labels or {}).get(change['nm_id']),grants_action_permission=False) for change in changes]
def normalize_experience(event):
 action=event.get('action') or {}
 if event.get('record_type')!='verified_action' or not event.get('source_key') or not instant(event.get('started_at')):return []
 out=[]
 for nm in action.get('nm_ids',[]):
  out.append(dict(nm_id=nm,campaign_id=action.get('campaign_id'),kind='price' if action.get('kind')=='price_change' else 'bid' if action.get('kind')=='bid_change' else action.get('kind'),placement=action.get('placement'),before=action.get('before'),after=action.get('after'),article=action.get('article'),source_key=event['source_key'],record_type='verified_action',at=event['started_at'],verified_at=event.get('verified_at'),experience_id=event.get('event_id'),grants_action_permission=False))
 return out
def window(change,now):
 at=instant(change.get('at'))
 if at is None:return dict(available=False)
 today=now.astimezone(MSK).date();day=at.astimezone(MSK).date();first=day+timedelta(days=1)
 return dict(excluded_change_day=str(day),first_full_day=str(first),first_review_at_msk=datetime.combine(first+timedelta(days=1),datetime.min.time(),MSK).isoformat(),completed_days=max(0,(today-first).days),changed_today=day==today,evaluation_status='waiting_first_full_day' if today<=first else 'requires_comparable_saved_results',causality='not_established')
def summarize_observation(event):
 observations=event.get('observations') or []
 if not observations:return dict(status='pending',business_outcome='unconfirmed',causality='not_established')
 last=observations[-1];before=last.get('before') or {};after=last.get('after') or {}
 comparable=(before.get('period_complete') is True and after.get('period_complete') is True and before.get('days')==after.get('days') and before.get('currency')==after.get('currency') and bool(last.get('source_keys')))
 financial=comparable and number(before.get('total_profit')) and number(after.get('total_profit')) and before.get('profit_method')==after.get('profit_method')
 return dict(status='observed' if comparable else 'inconclusive',financial_comparison=financial,business_outcome=(last.get('result') or {}).get('outcome','unconfirmed') if financial else 'unconfirmed',advertising_direction=last.get('advertising_direction','unconfirmed') if comparable else 'unconfirmed',period_before=[before.get('period_from'),before.get('period_to')],period_after=[after.get('period_from'),after.get('period_to')],source_keys=last.get('source_keys',[]),conditions=last.get('condition_comparison'),causality='not_established',note='Observed movement is not a causal proof or permission to repeat.')
def context(w,nm_ids=(),experiences=None,persist=True):
 now=getattr(w,'now',datetime.now(timezone.utc));wanted=set(nm_ids);labels={int(n):a for n,a in w.catalog()} if hasattr(w,'catalog') else {}
 from china_experience import read_rows
 if experiences is None:
  rows=read_rows(w,'china_agent:experience:v1:',limit=500)
  experiences=[r['payload'] for r in rows if r.get('payload')]
 else:rows=[]
 changes=[];observations=[]
 for event in experiences:
  selected=set((event.get('action') or {}).get('nm_ids',[]))
  if wanted and not wanted.intersection(selected):continue
  changes+=normalize_experience(event)
  observations.append(dict(experience_id=event.get('event_id'),nm_ids=sorted(selected),assessment=summarize_observation(event)))
 registry=w.get('china_agent:verified_campaign_state:v1') or {}
 canonical_keys=set()
 for cid,key in registry.items():
  receipt=w.get(key) or {}
  if str((receipt.get('after') or {}).get('id'))!=str(cid):continue
  actual=receipt_changes(key,receipt,labels)
  if actual:canonical_keys.add(key)
  changes+=actual
 policy=w.get(POLICY) or {}
 for key in policy.get('additional_receipt_keys',[])[:30]:
  actual=receipt_changes(key,w.get(key) or {},labels)
  if actual:canonical_keys.add(key)
  changes+=actual
 changes=[x for x in changes if not (x.get('experience_id') and x['source_key'] in canonical_keys)]
 unique={}
 for change in changes:
  if wanted and change['nm_id'] not in wanted:continue
  # Same canonical action imported through experience and registry is one event.
  signature=[change['source_key'],change['nm_id'],change.get('campaign_id'),change.get('placement'),change['kind'],change.get('before'),change.get('after')]
  ident=digest(signature);change=dict(change,event_id=ident)
  previous=unique.get(ident)
  if previous is None or instant(change['at'])>instant(previous['at']):unique[ident]=change
 # Existing action facts are immutable; current assessments are computed, not model-written.
 items=sorted(unique.values(),key=lambda x:instant(x['at']),reverse=True)
 if persist:
  known={r['cache_key'] for r in read_rows(w,ROOT+'event:',limit=1000)}
  # Incremental immutable imports, bounded independently of the complete decision view.
  for change in items[:12]:
   key=ROOT+'event:'+change['event_id']
   if key not in known:immutable(w,key,dict(change,kind='experiment_action',schema_version=1))
 decisions=[r['payload'] for r in read_rows(w,ROOT+'decision:',limit=60) if r.get('payload',{}).get('visibility')=='work']
 if wanted:decisions=[d for d in decisions if wanted.intersection(d.get('nm_ids',[]))]
 latest={}
 for change in items:
  latest.setdefault(str(change['nm_id']),dict(change,window=window(change,now)))
 return dict(source='canonical experiment journal',source_key=ROOT,observed_at=now.isoformat(),events=items[:80],latest_by_nm=latest,decisions=decisions,observations=observations[:80],history_scan_truncated=len(rows)>=500,grants_action_permission=False,wb_writes=0,rules=['Change day excluded; first full following MSK day, never current-day selection','Same SKU across campaigns is one experiment risk scope','Unknown/small sample is not success/failure; association is not causality','Past negative result requires review, not permanent rejection','Journal and proposed risk ceiling never authorize WB or budget changes'])
def guard(journal,nm,now):
 item=journal.get('latest_by_nm',{}).get(str(nm))
 if not item:return dict(allowed=True,reason='No recent canonical change in returned journal; other checks still required')
 info=window(item,now)
 return dict(allowed=info.get('completed_days',0)>0,latest_change=item,**info)
def risk_limits(pre_ad_per_created_order_cny,buyout,completed_sample,bid_cny=None,spent_cny=None):
 """A modelling ceiling is not an automatic WB stop or an approved loss budget."""
 if not number(pre_ad_per_created_order_cny) or not number(buyout) or not 0<=buyout<=1:
  return dict(available=False,reason='Unknown own margin or buyout; no zero/default substitution',execution_authorized=False)
 if not number(completed_sample) or completed_sample<=0:return dict(available=False,reason='Own completed buyout sample missing',execution_authorized=False)
 pre=pre_ad_per_created_order_cny;ceiling=max(0,pre)
 # A conservative initial risk proposal: half one expected break-even order, capped20CNY.
 # Working hypothesis, not owner-approved automatic spending.
 proposed=round(min(20,ceiling*.5),2)
 scenarios=[dict(click_order_pct=cr,break_even_cpc_cny=round(ceiling*cr/100,4)) for cr in (1,2,3)]
 required=bid_cny/pre*100 if number(bid_cny) and bid_cny>=0 and pre>0 else None
 return dict(available=True,currency='CNY',target_drr_pct=5,no_orders_requires_cost_review=True,pre_ad_per_created_order_cny=round(pre,4),break_even_cpa_model_cny=round(ceiling,4),buyout=buyout,completed_sample=completed_sample,small_sample=completed_sample<20,required_click_order_pct=round(required,4) if required is not None else None,cpc_scenarios=scenarios,suggested_initial_risk_budget_cny=proposed,spent_since_change_cny=spent_cny if number(spent_cny) and spent_cny>=0 else None,remaining_proposed_risk_cny=round(max(0,proposed-spent_cny),4) if number(spent_cny) and spent_cny>=0 else None,risk_scope='one SKU across all campaigns after latest verified change',risk_budget_is_working_hypothesis=True,not_statistical_significance=True,not_net_profit=True,unknown_reverse_and_shared_costs=True,requires_fresh_inputs=True,execution_authorized=False,automatic_stop=False,automatic_funding=False)


