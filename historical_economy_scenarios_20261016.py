"""Offline checks and saved-history scenarios. No current buyout forecast or source collection."""
import sys,copy,json,subprocess,os
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import Counter
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
from advertising_agent import agent_store as store
from advertising_order_outcome_monitor import KEY,seed,plan,status
r=dict(source_calls=0,wb_calls=0,wb_writes=0,telegram_calls=0,historical=[],scenarios=[])
try:
 tests=subprocess.run([sys.executable,'test_advertising_order_outcome_monitor.py','-v'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 r['tests']=tests.stdout
 if tests.returncode:raise RuntimeError('Order monitor safety tests failed')
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key) or {}
 audit=memory['historical_cohort_audit_20261016']
 oldsource=next(x for x in memory['mature_cohort_risk_20261016']['cohort_sources'] if x['source']=='orders')
 seen={}
 for x in oldsource['matching_rows']:
  if x['date'][:10]>='2026-10-04':continue
  identity=x.get('srid') or str(x.get('gNumber'))
  if identity not in seen or str(seen[identity].get('lastChangeDate',''))<str(x.get('lastChangeDate','')):seen[identity]=x
 for nm in (1123677454,320248210):
  older=[x for x in seen.values() if x['nmId']==nm]
  r['historical'].append(dict(nm_id=nm,source_snapshot_id=oldsource['id'],observed_at=oldsource['collected_at'],
   period_from=oldsource['period_from'],period_to='2026-10-03',orders=len(older),
   observed_cancellations=sum(x.get('isCancel') is True for x in older),
   others_without_retained_buyout_outcome=sum(x.get('isCancel') is not True for x in older),
   seller_prices=sorted({x.get('priceWithDisc') for x in older if type(x.get('priceWithDisc')) in (int,float)}),
   delivery_modes=dict(Counter(str(x.get('warehouseType')) for x in older)),
   usable_for_retention=False,reason='Saved order endpoint contains cancellations but no complete sale/return outcomes; isCancel=false is not a retained buyout'))
 fresh=memory['outcome_refresh_20261016']['saved']
 for s in fresh:
  obs=s['payload'][0];rows=[x for x in obs['data']['data'] if x['order_dt'][:10]<'2026-10-09'];nm=rows[0]['nm_id']
  r['historical'].append(dict(nm_id=nm,source_snapshot_id=s['id'],observed_at=obs['observed_at'],period_from='2026-10-04',period_to='2026-10-08',
   orders=len(rows),counts=dict(Counter(status(x) for x in rows)),seller_prices=sorted({x['retail_price_withdisc_rub'] for x in rows}),
   delivery_modes=dict(Counter(str(x.get('is_fbs')) for x in rows)),
   usable_for_mature_retention=False,reason='Small sample; unresolved orders and/or recent buyouts without retention finality. No denominator restricted to completed orders'))
 for unit in memory['decision_readiness_20261016']['retained_unit_examples']:
  nm=unit['nm_id'];M=unit['pre_ad_contribution'];C=unit['ad_cost_per_order_context']
  product=next(x for x in memory['validated_outcomes_20261016']['products'] if x['nm_id']==nm)
  fee=next(x for x in product['failed_order_evidence'] if x['state']=='nonbuyout_reverse_observed' and x['confirmed']==1 and x['reported_logistics_sum'] is not None)
  F=fee['reported_logistics_sum']
  r['scenarios'].append(dict(nm_id=nm,retained_unit_example=M,example_sample=1,historical_main_campaign_CPA=C,
   failed_order_fee_example=F,fee_is_scenario_parameter_not_population_mean=True,
   current_retention=None,forecast=False,
   D='Other-campaign advertising allocated to the same cohort + storage + other omitted cohort costs + actual CPA/fee deviations; unknown, not zero',
   formula='R(q)=q*M-(1-q)*F-C-D',
   sensitivity=[dict(q_scenario=q,known_component=round(q*M-(1-q)*F-C,2),result='known_component - D; not a forecast') for q in (.2,.4,.6,.8,1)],
   threshold_formula='q*=(C+F+D)/(M+F)',
   threshold_known_component=(C+F)/(M+F),threshold_unknown_increment='D/'+str(round(M+F,2)),
   selection='Main CPM historical CPA is a context parameter, not verified current all-campaign cohort CPA; other campaign spend not ignored'))
 monitoring=seed(store.cache_get(KEY),memory)
 store.cache_set(KEY,monitoring,ttl_days=365)
 if store.cache_get(KEY)!=monitoring:raise RuntimeError('Monitor seed full readback failed')
 now=datetime.now(timezone.utc)
 r['monitor_seed_full_readback']=True;r['tracked_orders']=len(monitoring['orders'])
 r['next_day_plan']=plan(monitoring,now+timedelta(days=1),max_requests=4)
 r['same_day_plan']=plan(monitoring,now,max_requests=4)
 r['status']='complete';updated=copy.deepcopy(memory);updated['historical_economy_scenarios_20261016']=r
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise RuntimeError('Scenario full memory readback failed')
 r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('historical-economy-scenarios',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),wb_writes=0)))
if r.get('status')!='complete':raise SystemExit(1)
