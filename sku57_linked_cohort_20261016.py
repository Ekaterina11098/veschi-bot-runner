"""Join saved GN/SRID identities from the previous audit; no rereading closed sources."""
import sys,json,copy
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parent/'private-source'))
from stock_deploy_support import seal,error
from advertising_agent import agent_store as store
r=dict(source_calls=0,wb_calls=0,wb_writes=0,telegram_calls=0,assumed_buyout_ratio=None)
try:
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key) or {}
 audit=memory.get('mature_cohort_risk_20261016') or {}
 sources=audit.get('cohort_sources') or []
 tape=next(x for x in sources if x['source']=='mpstats_lk_wb_sales_tape_complete')
 orders=next(x for x in sources if x['source']=='orders')
 mapping={}
 for row in orders['matching_rows']:
  gn=str(row.get('gNumber') or '');srid=row.get('srid')
  if gn and srid:mapping.setdefault(gn,set()).add(srid)
 reverse={srid:gn for gn,ids in mapping.items() if len(ids)==1 for srid in ids}
 selected={};conflicts=[]
 for row in tape['matching_rows']:
  gn=str(row.get('gnumber') or '')
  if not gn:continue
  if gn in selected and selected[gn]!=row:conflicts.append(gn)
  selected[gn]=row
 if conflicts:raise ValueError('Conflicting retained order identities')
 r['order_identity_sources']=dict(mpstats_snapshot_id=tape['id'],wb_orders_snapshot_id=orders['id'],
  observed_at=tape['collected_at'],period_from=tape['period_from'],period_to=tape['period_to'])
 r['cohort_status']=[]
 for nm in (1123677454,320248210):
  all_rows=[x for x in selected.values() if x['nm_id']==nm]
  current=[x for x in all_rows if '2026-10-09'<=str(x.get('order_dt',''))[:10]<='2026-10-15']
  def status(x):
   if x.get('refund_dt') or (x.get('refunded_times') or 0)>0:return 'returned_observed'
   if x.get('is_canceled_order')==1:return 'cancelled_observed'
   if x.get('sale_dt') and (x.get('billed_times') or 0)>0:return 'buyout_observed_not_mature'
   return 'pending_or_unknown'
  from collections import Counter
  r['cohort_status'].append(dict(nm_id=nm,observed_period_counts=dict(Counter(status(x) for x in all_rows)),
   target_order_period='2026-10-09..2026-10-15',covered_only_through=tape['period_to'],
   target_rows=[dict(gnumber=x['gnumber'],ordered_at=x.get('order_dt'),status=status(x),srid=next(iter(mapping[str(x['gnumber'])])) if len(mapping.get(str(x['gnumber']),set()))==1 else None) for x in current],
   observed_target_counts=dict(Counter(status(x) for x in current)),
   full_target_cohort_complete=False,mature_retention_ratio=None,do_not_treat_no_observed_buyouts_as_zero_ratio=True))
 r['linked_failure_costs']=[]
 for product in audit['failed_order_evidence']:
  for failed in product['observed_orders']:
   gn=reverse.get(failed['order_id']);row=selected.get(gn)
   r['linked_failure_costs'].append(dict(nm_id=product['nm_id'],srid=failed['order_id'],gnumber=gn,
    ordered_at=failed['ordered_at'],financial_service_logistics=round(failed['logistics'],2),
    financial_operations=failed['operations'],exact_identity_join=row is not None,
    mpstats_status=status(row) if row else None,
    mpstats_order_profit_reported=row.get('order_profit') if row else None,
    reported_order_profit_not_used_as_settled_margin=True,
    costs_not_transferred_to_current_cohort=True))
 r['conclusion']=dict(expected_profit_per_current_order=None,retained_ratio=None,current_failed_order_cost=None,
  reason='Saved tape stops10Oct and was observed11Oct; unresolved target orders and missing11-15 cohort; later service recognition incomplete',
  next_method='Only two exact MPStats product order cohorts, then their unresolved outcomes; link gnumber to saved WB gNumber/srid and unique service operations; never divide weekly sales by weekly orders')
 from analytics.ip_daily_recommendations import KEY
 prior=store.cache_get(KEY);updated=copy.deepcopy(memory)
 updated['linked_cohort_risk_20261016']=r
 updated['pilot_57_readiness_20261016'].update(proposed_start='2026-10-19T11:00:00+03:00',preferred_end='2026-10-20T11:00:00+03:00',
  end_time_preference_only=True,test_window_approved=False,backup_participation_authorized=False,backup_availability_confirmed=False,
  deployment_approved=False,execution_authorized=False,restore_authorized=False)
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise ValueError('Common memory full readback failed')
 r['common_memory_full_readback']=True;r['canonical_decisions_unchanged']=prior==store.cache_get(KEY);r['status']='complete'
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('sku57-linked-cohort',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'))))
if r.get('status')!='complete':raise SystemExit(1)
