"""Validate exact saved outcomes, reconcile identities and preserve history; no source calls."""
import sys,json,copy
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
from advertising_agent import agent_store as store
from analytics.stage_one import read
r=dict(wb_calls=0,wb_writes=0,source_calls=0,telegram_calls=0,products=[],production_actions_created=0)
def state(x):
 if x.get('refund_dt') or (x.get('refunded_times') or 0)>0:return 'returned_observed'
 if x.get('is_canceled_order')==1:return 'cancelled_observed'
 if not x.get('billed_times') and (x.get('backlogistic_times') or 0)>0:return 'nonbuyout_reverse_observed'
 if x.get('sale_dt') and (x.get('billed_times') or 0)>0:return 'buyout_observed_not_mature'
 return 'pending_or_unknown'
try:
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key) or {}
 refresh=memory['outcome_refresh_20261016']
 if refresh['status']!='received_for_validation':raise RuntimeError('Outcome refresh not available')
 audit=memory['mature_cohort_risk_20261016']
 tape=next(x for x in audit['cohort_sources'] if x['source']=='mpstats_lk_wb_sales_tape_complete')
 mapping_source=next(x for x in audit['cohort_sources'] if x['source']=='orders')
 maps={}
 for x in mapping_source['matching_rows']:
  if x.get('gNumber') and x.get('srid'):maps.setdefault(str(x['gNumber']),set()).add(x['srid'])
 old={str(x['gnumber']):x for x in tape['matching_rows']}
 for snapshot in refresh['saved']:
  reread=read('analytics_snapshots',dict(id='eq.'+str(snapshot['id']),select='id,payload,collected_at'))[0]
  if reread!=snapshot:raise RuntimeError('Independent exact source readback changed')
  obs=snapshot['payload'][0];data=obs['data'];rows=data['data'];pid=int(obs['arguments']['value'])
  nm={139147637:1123677454,124391695:320248210}[pid]
  filt=data.get('filterModel') or {}
  if obs.get('scope_verified') is not True or obs.get('status')!='received' or data.get('total')!=len(rows):raise RuntimeError('Response incomplete')
  if filt.get('product_id',{}).get('filter')!=pid or filt.get('order_dt',{}).get('dateFrom')!='2026-10-04' or filt.get('order_dt',{}).get('dateTo')!='2026-10-15':raise RuntimeError('Source filter not confirmed')
  ids=[str(x.get('gnumber') or '') for x in rows]
  if len(set(ids))!=len(ids) or '' in ids:raise RuntimeError('Duplicate or missing order identity')
  if any(x['nm_id']!=nm or not '2026-10-04'<=x['order_dt'][:10]<='2026-10-15' for x in rows):raise RuntimeError('Out of scope rows')
  oldids={gn for gn,x in old.items() if x['nm_id']==nm}
  missing=oldids-set(ids)
  if missing:raise RuntimeError('Previously saved target order omitted')
  target=[x for x in rows if '2026-10-09'<=x['order_dt'][:10]<='2026-10-15']
  failures=[]
  changes=[]
  for x in rows:
   gn=str(x['gnumber']);before=old.get(gn)
   if before and any(before.get(k)!=x.get(k) for k in ('sale_dt','refund_dt','is_canceled_order','backlogistic_times','order_profit','profit')):
    changes.append(dict(gnumber=gn,ordered_at=x['order_dt'],before={k:before.get(k) for k in ('sale_dt','refund_dt','is_canceled_order','backlogistic_times','order_profit','profit')},after={k:x.get(k) for k in ('sale_dt','refund_dt','is_canceled_order','backlogistic_times','order_profit','profit')}))
   if state(x) in ('returned_observed','cancelled_observed','nonbuyout_reverse_observed'):
    f=x.get('forward_logistic_rub');b=x.get('backward_logistic_rub')
    srid=next(iter(maps[gn])) if len(maps.get(gn,set()))==1 else None
    linked=[o for p in audit['failed_order_evidence'] if p['nm_id']==nm for group in p['observed_orders'] if group['order_id']==srid for o in group['operations']]
    failures.append(dict(gnumber=gn,srid=srid,ordered_at=x['order_dt'],state=state(x),target_cohort=x in target,confirmed=x.get('confirmed'),
     forward_logistics_reported=f,reverse_logistics_reported=b,reported_logistics_sum=round(f+b,2) if type(f) in (int,float) and type(b) in (int,float) else None,
     settled_failure_total=None,zero_reported_is_not_final_zero=True,financial_operations=linked,
     basis='MPStats order fields; linked finance separately, never added twice'))
  r['products'].append(dict(nm_id=nm,product_id=pid,snapshot_id=snapshot['id'],observed_at=obs['observed_at'],response_complete=True,
   order_period='2026-10-04..2026-10-15',rows=len(rows),observed_counts=dict(Counter(state(x) for x in rows)),
   target_period='2026-10-09..2026-10-15',target_rows=len(target),target_counts=dict(Counter(state(x) for x in target)),
   mature_retained_ratio=None,mature_expected_profit=None,maturity_basis='Source confirmed field is not an approved retention horizon or finality guarantee; unresolved and recent buyouts not mature',
   mature_part_recalculation='No independently settled mature denominator and final scoped failure costs; do not compute numeric retention or expected profit',
   target_orders=[dict(gnumber=x['gnumber'],ordered_at=x['order_dt'],sale_dt=x.get('sale_dt'),refund_dt=x.get('refund_dt'),state=state(x),confirmed=x.get('confirmed')) for x in target],
   updated_old_orders=changes,failed_order_evidence=failures,old_source_id=tape['id'],old_observed_at=tape['collected_at'],
   advertising_financial_recognition_and_order_costs_not_added=True,retained_unit_examples_reused=[u for u in memory['decision_readiness_20261016']['retained_unit_examples'] if u.get('nm_id')==nm]))
 updated=copy.deepcopy(memory);updated['validated_outcomes_20261016']=r
 updated['disabled_recovery_deployment_20261016']=dict(agent_merge_sha='8f681eb3403c66b3428e5e7d77c8a1861ed02d31',runner_merge_sha='1d7cc59b194c74a4cf896490dbc33abfc007ea4a',wb_execution=False,periodic_wakeup=False,production_actions_created=0,window_approved=False,backup_participation=False,preferred_time=None)
 r['status']='complete'
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise RuntimeError('Common memory full readback failed')
 r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('sku685-141-outcome-validation',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),products=len(r['products']),wb_writes=0)))
if r.get('status')!='complete':raise SystemExit(1)
