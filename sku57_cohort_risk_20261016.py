"""Saved-cohort risk audit; no assumed buyout ratio, no collection or executable test."""
import os,sys,json,copy
from pathlib import Path
from datetime import datetime,timezone,date
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
from stock_deploy_support import seal,error
from analytics.stage_one import read
from advertising_agent import agent_store as store
from analytics.ip_operation_diagnosis import collect_cached
from advertising_budget_evidence import budget_analysis
r=dict(wb_calls=0,wb_writes=0,source_calls=0,telegram_calls=0,rows_created=0,assumed_buyout_ratio=None,forecasts=False)
try:
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key) or {}
 units=(memory.get('decision_readiness_20261016') or {}).get('retained_unit_examples') or []
 if len(units)!=2:raise ValueError('Existing verified retained-unit examples missing; do not recalculate closed cases')
 r['retained_unit_examples_reused']=units
 metas=read('analytics_snapshots',dict(cabinet='eq.token_2',source='in.(mpstats_lk_wb_card_orders,mpstats_lk_wb_sales_tape,mpstats_lk_wb_sales_tape_complete,orders_ip,orders_ip_paginated,orders)',select='id,source,period_from,period_to,collected_at,status',order='id.desc',limit=40))
 r['cohort_source_metadata']=metas;r['cohort_sources']=[]
 seen=set()
 def lists(x):
  if isinstance(x,list):
   yield x
   for v in x:
    if isinstance(v,(dict,list)):yield from lists(v)
  elif isinstance(x,dict):
   for v in x.values():
    if isinstance(v,(dict,list)):yield from lists(v)
 for meta in metas:
  family=meta['source']
  if family in seen and family!='mpstats_lk_wb_card_orders':continue
  if family=='mpstats_lk_wb_card_orders' and meta.get('period_to','')<'2026-10-09':continue
  seen.add(family)
  snapshot=read('analytics_snapshots',dict(id='eq.'+str(meta['id']),select='id,payload'))[0]
  matches=[];identities=set()
  for values in lists(snapshot['payload']):
   for row in values:
    if not isinstance(row,dict):continue
    nm=next((row.get(k) for k in ('nm_id','nmId','nmID') if row.get(k) is not None),None)
    if str(nm) not in ('1123677454','320248210'):continue
    ident=json.dumps(row,sort_keys=True,default=str)
    if ident in identities:continue
    identities.add(ident);matches.append(row)
  obs=(snapshot['payload'][0] if isinstance(snapshot['payload'],list) and snapshot['payload'] else snapshot['payload'])
  r['cohort_sources'].append(dict(**meta,arguments=obs.get('arguments') if isinstance(obs,dict) else None,observation_status=obs.get('status') if isinstance(obs,dict) else None,matching_rows=matches))
 native=collect_cached(read,date(2026,10,9),date(2026,10,15),[(1123677454,'685-CelineaBag-black'),(320248210,'141-PamelaBag-brown')])
 r['operation_coverage']=native['day_coverage'];r['failed_order_evidence']=[]
 for product in native['products']:
  groups={}
  for o in product['operations']:
   if o.get('service_reason') not in ('К клиенту при отмене','От клиента при отмене','От клиента при возврате'):continue
   if not o.get('order_id') or o.get('logistics') is None:continue
   g=groups.setdefault(o['order_id'],dict(order_id=o['order_id'],ordered_at=o.get('ordered_at'),operations=[],logistics=0))
   g['operations'].append(o);g['logistics']+=o['logistics']
  r['failed_order_evidence'].append(dict(nm_id=product['nm_id'],observed_orders=list(groups.values()),
   all_observed_orders_predate_current_cohort=all(str(g['ordered_at'])[:10]<'2026-10-09' for g in groups.values()),
   mature_current_retention_ratio=None,current_failed_order_cost=None,
   unknown_not_zero=True,do_not_transfer_old_order_costs_to_new_orders=True))
 r['model']=dict(retention_ratio=None,nonretained_order_cost=None,storage_per_order=None,
  expression='E = q * retained_buyout_contribution - (1-q) * failed_order_cost - campaign_cost_per_order - other_scoped_costs',
  date_basis='One order-date cohort with final retained buyout outcomes; no division of same-period sales by orders',
  q_is_retained_after_returns=True,no_assumed_q=True,
  exact_current_expected_profit=None,old_failed_order_samples_not_new_cohort_estimate=True)
 budget=read('analytics_snapshots',dict(source='eq.advertising_campaign_budgets',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))
 r['new_campaign_budget']=next(x for x in budget_analysis(dict(budgets=budget,campaigns=[dict(wb_campaign_id=40223879,active_catalog_verified=True)]),datetime.now(timezone.utc)) if x['campaign_id']==40223879)
 r['new_campaign_budget']['source_snapshot_id']=budget[0]['id']
 from analytics.ip_daily_recommendations import KEY
 prior=store.cache_get(KEY)
 updated=copy.deepcopy(memory)
 updated['mature_cohort_risk_20261016']=r
 proposal=updated.setdefault('pilot_57_readiness_20261016',{})
 proposal.update(backup_participation_authorized=False,backup_availability_confirmed=False,backup_status='proposed_for_separate_test_consent',execution_authorized=False,restore_authorized=False,test_window_approved=False)
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise ValueError('Common memory full readback failed')
 r['common_memory_full_readback']=True;r['canonical_decisions_unchanged']=prior==store.cache_get(KEY);r['status']='complete'
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('sku57-cohort-risk',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),wb_writes=0)))
if r.get('status')!='complete':raise SystemExit(1)
