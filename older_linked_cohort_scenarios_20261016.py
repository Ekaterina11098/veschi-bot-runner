"""Join preserved sale/return identities, retain full order denominators and scenario scope."""
import sys,json,copy
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from advertising_agent import agent_store as store
from stock_deploy_support import seal,error
r=dict(source_calls=0,wb_calls=0,wb_writes=0,telegram_calls=0,cohorts=[],sku_scenarios=[])
try:
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key)
 audit=memory['older_sales_ledger_audit_20261016'];events={}
 for source in audit['matching_sales']:
  for x in source['rows']:
   identity=x.get('saleID')
   if not identity:continue
   old=events.get(identity)
   if old is None or str(old.get('lastChangeDate',''))<str(x.get('lastChangeDate','')):events[identity]=x
 by_order={}
 for x in events.values():by_order.setdefault(x.get('srid'),[]).append(x)
 def state(x):
  rows=by_order.get(x['srid'],[]);sold=sum(str(v.get('saleID','')).startswith('S') for v in rows);ret=sum(str(v.get('saleID','')).startswith('R') for v in rows)
  if x.get('isCancel') is True and sold>ret:return 'conflict_cancel_and_positive_sales'
  if sold>ret:return 'net_sold_observed_not_final'
  if sold and ret>=sold:return 'returned_observed'
  if ret and not sold:return 'return_without_sale_in_ledger'
  if x.get('isCancel') is True:return 'cancelled_observed'
  return 'unresolved'
 for nm,current_price in ((1123677454,None),(320248210,None)):
  unit=next(x for x in memory['decision_readiness_20261016']['retained_unit_examples'] if x['nm_id']==nm);current_price=unit['seller_price']
  rows=[x for x in audit['older_order_rows'] if x['nmId']==nm]
  scopes=[('all_older',rows),('orders_at_least_21_days_old_at_observation',[x for x in rows if x['date'][:10]<='2026-09-20']),('same_seller_price',[x for x in rows if abs(x.get('priceWithDisc',0)-current_price)<.01]),('same_price_WB_warehouse',[x for x in rows if abs(x.get('priceWithDisc',0)-current_price)<.01 and x.get('warehouseType')=='Склад WB'])]
  for name,chosen in scopes:
   counts=dict(Counter(state(x) for x in chosen));n=len(chosen);retained=counts.get('net_sold_observed_not_final',0)
   unresolved=sum(counts.get(v,0) for v in ('unresolved','conflict_cancel_and_positive_sales','return_without_sale_in_ledger'))
   r['cohorts'].append(dict(nm_id=nm,scope=name,orders=n,counts=counts,
    date_from=min((x['date'][:10] for x in chosen),default=None),date_to=max((x['date'][:10] for x in chosen),default=None),
    observed_at=max(x['collected_at'] for x in audit['matching_sales']),order_source_id=7936,sales_source_ids=[x['id'] for x in audit['matching_sales']],
    seller_prices=sorted({x['priceWithDisc'] for x in chosen}),delivery_modes=dict(Counter(str(x.get('warehouseType')) for x in chosen)),
    full_denominator_observed_retained_fraction=retained/n if n else None,
    completion_only_upper_fraction=(retained+unresolved)/n if n else None,
    maturity=False,limits='Fractions use every cohort order; upper completes unresolved only, assumes no later reversal of observed sales; not a current retention estimate or forecast'))
  # Reuse full product spending from retained investigation if available, never deduce exact cohort attribution.
  def find(x):
   if isinstance(x,dict):
    if x.get('nm_id')==nm and 'stat_campaign_total' in x:return x
    for v in x.values():
     z=find(v)
     if z:return z
   elif isinstance(x,list):
    for v in x:
     z=find(v)
     if z:return z
   return None
  case=find(memory)
  product=next(x for x in memory['validated_outcomes_20261016']['products'] if x['nm_id']==nm)
  if case:
   M=unit['pre_ad_contribution']
   fresh=next(s for s in memory['outcome_refresh_20261016']['saved'] if s['payload'][0]['data']['data'][0]['nm_id']==nm)
   raw_by_gn={str(x['gnumber']):x for x in fresh['payload'][0]['data']['data']}
   fee=next(x for x in product['failed_order_evidence'] if x['confirmed']==1 and x['reported_logistics_sum'] is not None and x['reported_logistics_sum']>0 and raw_by_gn[str(x['gnumber'])].get('is_fbs')==0)
   F=fee['reported_logistics_sum']
   spend=case['stat_campaign_total'];norms=[]
   for label,N in [('main_campaign_reported_order_count',case['shown_orders']),('observed_all_target_orders',product['target_rows'])]:
    C=spend/N
    norms.append(dict(basis=label,denominator=N,CPA_scenario=C,assumed_all_period_spend_allocation=True,actual_cohort_CPA_verified=False,
     threshold_base=(C+F)/(M+F),threshold_unknown_increment='D/'+str(round(M+F,2)),
     sensitivity=[dict(q=q,known_component=round(q*M-(1-q)*F-C,2),result='known_component minus unknown D') for q in (.2,.4,.6,.8,1)]))
   r['sku_scenarios'].append(dict(nm_id=nm,total_product_campaign_spend=spend,main_CPM_spend=case['main_spend'],period='2026-10-09..2026-10-15',M=M,F_example=F,fee_order_gnumber=fee['gnumber'],fee_source_state=fee['state'],fee_delivery_mode='FBO',fee_is_example_not_population_mean=True,
    normalizations=norms,not_statistical_confidence_interval=True,
    D='Unallocated storage and other costs, plus deviations of actual unit contribution/failure cost from these explicit scenario examples; unknown, never set to zero',
    warning='Advertising reported orders and card order-date cohort counts are different evidence; do not force equality or call this proven attribution'))
 r['status']='complete';updated=copy.deepcopy(memory);updated['older_linked_cohorts_and_sku_scenarios_20261016']=r
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise RuntimeError('Linked historical cohort full readback failed')
 r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('older-linked-cohort-scenarios',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),cohorts=len(r['cohorts']),sku_scenarios=len(r['sku_scenarios']))))
if r.get('status')!='complete':raise SystemExit(1)
