"""Preserve explicit historical counterfactuals and draft risk recommendations, never actions."""
import sys,json,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from advertising_agent import agent_store as store
from stock_deploy_support import seal,error
r=dict(source_calls=0,wb_calls=0,wb_writes=0,telegram_calls=0,results=[],executable_actions_created=0)
try:
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key)
 linked=memory['older_linked_cohorts_and_sku_scenarios_20261016']
 for sku in linked['sku_scenarios']:
  nm=sku['nm_id'];facts=[x for x in linked['cohorts'] if x['nm_id']==nm]
  scenarios=[]
  for cohort in facts:
   if cohort['scope'] not in ('same_seller_price','same_price_WB_warehouse') or not cohort['orders']:continue
   qs=(cohort['full_denominator_observed_retained_fraction'],cohort['completion_only_upper_fraction'])
   scenarios.append(dict(scope=cohort['scope'],orders=cohort['orders'],historical_q_scenarios=qs,
    assumptions='Observed net sales remain retained; unresolved become either no retained buyout or all retained; later returns can make actual retention lower. These are not confidence bounds or current forecasts.',
    conditional_results=[dict(allocation=n['basis'],values=[round(q*sku['M']-(1-q)*sku['F_example']-n['CPA_scenario'],2) for q in qs],result='each value minus unknown D') for n in sku['normalizations']]))
  r['results'].append(dict(nm_id=nm,campaign_id=40223314 if nm==1123677454 else 39410834,source_period=sku['period'],
   total_product_ad_spend=sku['total_product_campaign_spend'],historical_facts=facts,historical_counterfactuals=scenarios,
   current_retention_estimate=None,forecast=False,
   recommendation='Candidate for a separately approved bounded reduction of this SKU CPM exposure; keep alternative campaigns separate, restore original participation if a real test is later approved',
   confirmed_reason='High loss sensitivity including failure costs, observed historical cancellations/returns, and historical main CPM DRR above owner 5% reference',
   limits='Not proven causal loss from advertising; no claim sales remain after reduction; no justified exact new price/bid or budget. Test parameters and restoration for this SKU need separate review.',
   employee_delivery_ready=False,why_not_delivered='A risk-supported test candidate is not an executable staff action; no finished parameters/permission',
   real_test_authorized=False,amounts_are_not_risk_limits=True))
 updated=copy.deepcopy(memory);updated['economic_risk_decisions_20261016']=r
 r['status']='complete';store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise RuntimeError('Economic risk decision readback failed')
 r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('economic-risk-decisions',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),executable_actions_created=0)))
if r.get('status')!='complete':raise SystemExit(1)
