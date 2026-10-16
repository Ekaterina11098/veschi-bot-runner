"""Finish decisions from saved evidence; no source collection, Telegram, or WB mutation."""
import sys,json,copy,hashlib
from pathlib import Path
from datetime import datetime,timezone,date
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
from stock_deploy_support import seal,error
from analytics.stage_one import read
from advertising_agent import agent_store as store
from advertising_budget_evidence import budget_analysis
from advertising_current_promotion import guard
from analytics.ip_operation_diagnosis import collect_cached
r=dict(wb_writes=0,wb_calls=0,source_calls=0,telegram_calls=0,forecasts=False,test57_enabled=False)
try:
 control=store.cache_get('advertising:ip:pr27-controlled:20261016:v1')
 if not control or control.get('status')!='complete':raise ValueError('Exact retained analysis missing')
 config=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))[0]
 budgets=read('analytics_snapshots',dict(source='eq.advertising_campaign_budgets',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))
 r['budgets']=budget_analysis(dict(budgets=budgets,campaigns=[dict(wb_campaign_id=i,active_catalog_verified=True) for i in config['payload']['campaign_ids']]),datetime.now(timezone.utc))
 r['budget_snapshot_id']=budgets[0]['id']
 assert len(r['budgets'])==13 and all(x['balance'] is not None for x in r['budgets'])
 assert next(x for x in r['budgets'] if x['campaign_id']==40223879)['balance_observed_at']
 r['promotion']=guard(dict(period_from='2026-10-09',period_to='2026-10-15',campaigns=[dict(wb_campaign_id=40223879,totals={},products=[])]),config)['campaigns'][0]['current_promotion']
 day=read('analytics_snapshots',dict(id='eq.17628',select='id,payload,collected_at'))[0]
 rows=day['payload'][0]['data']['data']['data']
 native=collect_cached(read,date(2026,10,10),date(2026,10,10),[(1123677454,'685-CelineaBag-black'),(320248210,'141-PamelaBag-brown')])
 r['retained_unit_examples']=[]
 for n,ad_cpo in [(1123677454,669),(320248210,6946/9)]:
  raw=next(x for x in rows if x['nm_id']==n)
  own=control['after']['items'][str(n)]
  services=next(x for x in native['products'] if x['nm_id']==n)['operations']
  linked=[x for x in services if x['service_reason']=='К клиенту при продаже' and x['logistics'] is not None]
  if len(linked)!=1 or raw['sales_count']!=1 or raw['returns_count']!=0:raise ValueError('Historical sale unit not uniquely explainable')
  price=raw['sales_sum_without_spp'];commission=raw['total_commission_without_spp'];fee=raw['acquiring']
  cogs=own['cost_per_unit'];tax=price*own['tax_reserve_rate'];delivery=linked[0]['logistics']
  margin=round(price-commission-fee-cogs-tax-delivery,2)
  cancellation=sum(x['logistics'] or 0 for x in services if x['service_reason'] in ('К клиенту при отмене','От клиента при отмене'))
  financial=raw['for_pay']-cogs-tax
  reconciled=round(financial+raw['advertisement']+raw['storage_fee']+cancellation,2)
  if abs(reconciled-margin)>.02:raise ValueError('Example reconciliation failed; no approximate unit conclusion')
  r['retained_unit_examples'].append(dict(nm_id=n,article=raw['sa_name'],day='2026-10-10',source_snapshot_id=day['id'],observed_at=day['collected_at'],
   seller_price=price,commission=commission,commission_rate=commission/price,cogs=cogs,cogs_provenance=own.get('own_cost_provenance'),
   acquiring=fee,tax_reserve=tax,tax_reserve_rate=own['tax_reserve_rate'],linked_sale_delivery=delivery,service_operation=linked[0],
   cancellation_expenses_separate=cancellation,storage_separate=raw['storage_fee'],pre_ad_contribution=margin,
   historical_financial_reconciliation=reconciled,sample=1,
   contribution_is_conditional_retained_buyout_example=True,not_current_order_cohort=True,not_next_sale_forecast=True,
   ad_cost_per_order_context=ad_cpo,minimum_retention_ratio_ignoring_failed_order_costs=ad_cpo/margin,
   mature_current_retention_ratio=None,failed_order_costs_per_current_order=None,
   exact_next_price_scenario_ready=False))
 r['excluded_history']=[]
 metadata=read('analytics_snapshots',dict(source='eq.mpstats_lk_wb_reports_compare',cabinet='eq.token_2',select='id,period_from,period_to,collected_at',order='id.desc',limit=30))
 r['excluded_comparison_metadata']=metadata
 for meta in metadata[:8]:
  s=read('analytics_snapshots',dict(id='eq.'+str(meta['id']),select='id,payload,collected_at'))[0]
  for obs in s['payload']:
   data=obs.get('data') or {};rr=data.get('data',[])
   if isinstance(rr,dict):rr=rr.get('data',[])
   matches=[x for x in rr if str(x.get('nm_id',x.get('nmId','')))=='760746874' or str(x.get('p_id',''))=='124410523' or x.get('article',x.get('sa_name'))=='122-Zont-blue'] if isinstance(rr,list) else []
   r['excluded_history'].append(dict(snapshot_id=s['id'],collected_at=s['collected_at'],arguments=obs.get('arguments'),status=obs.get('status'),matches=matches))
 from analytics.ip_daily_recommendations import KEY
 old=store.cache_get(KEY)
 key='advertising:ip:focus_preparation:20261016'
 memory=store.cache_get(key) or {}
 saved=copy.deepcopy(memory)
 saved['decision_readiness_20261016']=r
 store.cache_set(key,saved,ttl_days=365)
 if store.cache_get(key)!=saved:raise ValueError('Full existing memory readback mismatch')
 r['existing_memory_full_readback']=True;r['canonical_decisions_unchanged']=old==store.cache_get(KEY)
 r['status']='complete'
except Exception as exc:r.update(status='incomplete',error=error(exc))
finally:
 seal('advertising-decision-readiness',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),wb_writes=0)))
if r.get('status')!='complete':raise SystemExit(1)
