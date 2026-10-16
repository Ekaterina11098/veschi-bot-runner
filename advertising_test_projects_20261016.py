"""Verify the exact refreshed twelve, daily entry point and non-executable CPM projects."""
import sys,json,copy,ast,os,subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import Counter
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.stage_one import read
from analytics.collect import database
from advertising_agent import agent_store as store
from stock_deploy_support import seal,error
from advertising_order_outcome_monitor import KEY,historical_685_scope,status,dt
r=dict(source_calls=0,wb_calls=0,wb_writes=0,telegram_calls=0,executable_actions_created=0,projects=[],economy=[])
try:
 tests=subprocess.run([sys.executable,'test_advertising_order_outcome_monitor.py','-v'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);r['tests']=tests.stdout
 if tests.returncode:raise RuntimeError('Observation boundary tests failed')
 key='advertising:ip:focus_preparation:20261016'
 before=database('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1})[0];memory=before['payload']
 scope=historical_685_scope(memory);gns=set(scope['target_gnumbers'])
 sources=read('analytics_snapshots',dict(source='eq.mpstats_lk_wb_card_orders',cabinet='eq.token_2',run_id='eq.38945224412:1',select='id,payload,collected_at',order='id.desc',limit=3))
 if not sources:
  sources=read('analytics_snapshots',dict(id='eq.17837',select='id,payload,collected_at'))
 if len(sources)!=1:raise RuntimeError('Exact historical refresh receipt ambiguous')
 source=sources[0];obs=source['payload'][0];body=obs['data'];rows=body['data']
 if obs.get('status')!='received' or obs.get('scope_verified') is not True or body.get('total')!=len(rows):raise RuntimeError('Historical response incomplete')
 targeted={str(x['gnumber']):x for x in rows if str(x['gnumber']) in gns}
 if set(targeted)!=gns or len(targeted)!=12:raise RuntimeError('Missing target GN')
 if any(x['nm_id']!=scope['nm_id'] or x['is_fbs']!=0 for x in targeted.values()):raise RuntimeError('Changed product or delivery scope')
 state=store.cache_get(KEY)
 if any(state['orders'][gn]['snapshot_id']!=source['id'] or state['orders'][gn]['raw']!=targeted[gn] for gn in gns):raise RuntimeError('Monitor actual target full readback mismatch')
 observed_counts=dict(Counter(status(x) for x in targeted.values()))
 def order_status(x):
  ledger=memory['older_sales_ledger_audit_20261016']
  events={}
  for s in ledger['matching_sales']:
   for e in s['rows']:
    if e.get('srid')==x['srid'] and e.get('saleID'):events[e['saleID']]=e
  a=sum(s.startswith('S') for s in events);b=sum(s.startswith('R') for s in events)
  return 'buyout' if a>b else 'returned' if a and b>=a else 'cancelled' if x['isCancel'] else 'unresolved'
 old_by_gn={str(x['gNumber']):x for x in scope['orders']}
 r['historical_twelve']=dict(snapshot_id=source['id'],observed_at=obs['observed_at'],raw_response_rows=len(rows),target_rows=12,counts=observed_counts,
  all_target_ids_present=True,monitor_full_readback=True,
  rows=[dict(gnumber=gn,ordered_at=x['order_dt'],before=order_status(old_by_gn[gn]),after=status(x),sale_dt=x.get('sale_dt'),refund_dt=x.get('refund_dt'),confirmed=x.get('confirmed'),
    forward_logistics=x.get('forward_logistic_rub'),reverse_logistics=x.get('backward_logistic_rub'),
    fee_not_assumed_final=True) for gn,x in targeted.items()],
  current_retention_estimate=None,financial_finality=False)
 # Execute the actual daily stage wrapper with an isolated subprocess boundary. No day claim or real daily run.
 daily=Path('advertising_daily_owner.py').read_text();tree=ast.parse(daily)
 stage_node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='stage')
 captured=[]
 def offline_child(args,**kw):
  assert Path(args[1]).name=='advertising_source_owner.py'
  assert 'WB_TOKEN_2' not in kw['env'] and 'ADVERTISING_TELEGRAM_BOT_TOKEN' not in kw['env']
  captured.append(dict(filename=Path(args[1]).name,execution=kw['env']['ADVERTISING_EXECUTION_ENABLED'],telegram=kw['env']['IP_LIMITED_TELEGRAM_DELIVERY']))
  return SimpleNamespace(returncode=0,stdout=json.dumps(dict(saved=1,error_type=None,wb_calls=0,telegram_calls=0)))
 ns=dict(os=os,sys=sys,json=json,ROOT=Path('.').resolve(),started=datetime.now(timezone.utc).isoformat(),preserve_checkpoint=lambda *a:None,
  subprocess=SimpleNamespace(run=offline_child,TimeoutExpired=subprocess.TimeoutExpired,PIPE=subprocess.PIPE,STDOUT=subprocess.STDOUT))
 exec(compile(ast.Module(body=[stage_node],type_ignores=[]),'actual_daily_stage','exec'),ns)
 with patch.dict(os.environ,{'WB_TOKEN_2':'offline-fixture','ADVERTISING_TELEGRAM_BOT_TOKEN':'offline-fixture'},clear=False):
  ns['stage']('advertising_source_owner.py',900)()
 source_code=Path('advertising_source_owner.py').read_text()
 assert "source=stage('advertising_source_owner.py'" in daily and "source_gaps=stage('advertising_source_owner.py'" in daily
 assert 'plan_order_checks(order_monitor,now,max_requests=4)' in source_code
 assert 'ingest_order_observation(order_monitor,obs,ident,target_new_ids=focus_target_ids)' in source_code
 workflow=Path('.github/workflows/advertising-daily-prepared.yml').read_text()
 assert "cron: '30 4 * * *'" in workflow and "ref: 6eb5f990aecfa1a92909169ffd76f05ac6da469d" in workflow
 now=datetime.now(timezone.utc);recent=[]
 for x in state['orders'].values():
  sale=dt((x.get('raw') or {}).get('sale_dt') or x.get('last_sale_at'))
  if x.get('status')=='buyout' and sale and 0<=(now-sale).days<=30:
   if not x.get('active') or x.get('next_check_at') is None:raise RuntimeError('Recent buyout stopped prematurely')
   recent.append(dict(gnumber=x['gnumber'],nm_id=x['nm_id'],sale_dt=sale.isoformat(),observed_at=x['observed_at'],next_check_at=x['next_check_at'],financially_final=x['financially_final']))
 r['daily_connection']=dict(actual_daily_wrapper_exercised_with_offline_child=True,wrapper_calls=captured,actual_source_callback_verified_by_refresh_run=38945224412,
  original_orders=58,now_tracked=len(state['orders']),recent_buyouts_still_active=recent,day_claim_replayed=False,scheduled_run_not_yet_observed=True,schedule_unchanged=True)
 def find(x,required):
  if isinstance(x,dict):
   if all(k in x for k in required):return x
   for v in x.values():
    z=find(v,required)
    if z is not None:return z
  elif isinstance(x,list):
   for v in x:
    z=find(v,required)
    if z is not None:return z
  return None
 follow=find(memory,['sku_reconciliation','reconciled_daily'])
 if follow is None:raise RuntimeError('Retained daily source details missing')
 config=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))[0]
 for nm,campaign in ((1123677454,40223314),(320248210,39410834)):
  unit=next(x for x in memory['decision_readiness_20261016']['retained_unit_examples'] if x['nm_id']==nm)
  metrics=find(memory,['cases'])['cases'];case=next(x for x in metrics if x['nm_id']==nm)
  daily=next(x for x in follow['sku_reconciliation'] if x['nm_id']==nm)['daily_ad_statistics']
  distinct={}
  for x in daily:
   identity=(x['mpstats_id'],x['day'])
   if identity in distinct and distinct[identity]['spend']!=x['spend']:raise RuntimeError('Conflicting daily ad versions')
   distinct[identity]=x
  S=sum(x['spend'] for x in distinct.values())
  product=next(x for x in memory['validated_outcomes_20261016']['products'] if x['nm_id']==nm)
  N=product['target_rows'];K=case['shown_orders'];C_A=S/K;C_B=S/N
  previous=next(x for x in memory['older_linked_cohorts_and_sku_scenarios_20261016']['sku_scenarios'] if x['nm_id']==nm)
  M=unit['pre_ad_contribution'];F=previous['F_example']
  ads=next(x for x in config['payload']['adverts'] if x['id']==campaign);setting=next(x for x in ads['nm_settings'] if x['nm_id']==nm)
  stats_by_campaign={cid:sum(x['spend'] for (cid2,day),x in distinct.items() if cid2==cid) for cid in {v[0] for v in distinct}}
  r['economy'].append(dict(nm_id=nm,period='2026-10-09..2026-10-15',daily_all_known_S=S,weekly_previous_current_campaigns_S=case['stat_campaign_total'],
   daily_components=stats_by_campaign,daily_source_ids=sorted({x['snapshot_id'] for x in distinct.values()}),
   main_campaign_reported_orders=K,unique_card_order_date_cohort_orders=N,
   formula_A='C_A=sum(SKU campaign/day spend)/main campaign reported orders; mismatched denominator, comparison only',
   formula_B='C_B=sum(SKU campaign/day spend)/unique SKU orders placed in same date period; descriptive period load, not proved attribution',
   preferred_descriptive_basis='B',causal_cohort_CPA_verified=False,C_A=C_A,C_B=C_B,M_example=M,F_example=F,F_delivery='FBO',
   D_articles=['cohort storage','paid acceptance/rebilling/other logistics not already in retained unit or failed-order example','evidenced cohort deductions/penalties',
     'q*(sample retained-unit contribution minus actual contribution): price/commission/acquiring/own COGS/tax/delivery corrections',
     '(1-q)*(actual failed-order cost minus sample fee): forward/reverse/late logistics corrections',
     'actual advertising allocation minus period normalization; same advertising expense, never an additional charge'],
   D_unknown=True,D_may_depend_on_q=True,
   sensitivity=[dict(q=q,A=round(q*M-(1-q)*F-C_A,2),B=round(q*M-(1-q)*F-C_B,2),result='each component minus unknown D; conditional example, not forecast') for q in (.2,.3,.4,.5,.6,.7,.8,.9,1)],
   threshold_A_base=(C_A+F)/(M+F),threshold_B_base=(C_B+F)/(M+F),threshold_formula='q*=(C+F+D)/(M+F) only if M,F,D fixed; otherwise solve q*M_actual-(1-q)*F_actual-C_actual-H=0',
   actual_threshold_known=False))
  r['projects'].append(dict(nm_id=nm,article=case['article'],campaign_id=campaign,
   exact_change='ONLY target SKU participation in this CPM: present -> absent -> original present',
   allowed_test_values=['present','absent'],bid_change_allowed=False,new_money_limit=None,
   cached_configuration=dict(snapshot_id=config['id'],observed_at=config['collected_at'],campaign_settings={k:v for k,v in ads.items() if k!='nm_settings'},target_setting=setting,sku_count=len(ads['nm_settings'])),
   reference_stats=dict(period='2026-10-09..2026-10-15',main_spend=case['main_spend'],reported_orders=K,turnover=case.get('shown_turnover'),reported_DRR_percent=case.get('shown_drr_pct'),all_known_daily_sku_spend=S),
   duration_hours_max=24,start_time=None,end_time=None,window_authorized=False,
   deadline='Approved T_end=T_start+24h; never move deadline after late confirmation or 429. No start if preflight not ready at approved start.',
   one_change='Temporary SKU membership only; keep saved original bids/placements, CPC and other SKUs. Restoration writes restore original values, not a second treatment.',
   stop=['fixed approved deadline','staff or other bidder intervention','availability/price/SPP/photo change','loss of durable journal/lease or unreliable source monitoring','unapproved other campaign changes'],
   restoration='Intent before mutation; fresh actual WB GET before each decision; after unknown write GET-only; exact target add/remove, never whole composition; original bid only if unchanged employee ownership and valid minimum. Conflicts -> incident, no overwrite.',
   retry_after='Respect actual endpoint pause and RetryAfter; do not extend test or blindly replay write; record overdue restoration',
   post_observation='48/72h from T_start are observation after restoration, never extension; unresolved buyouts/returns continue separate observation',
   sequence='After 57 is WB-confirmed restored and its 72h checkpoint reviewed; no overlap or automatic trigger' if nm==320248210 else 'Separately approved non-overlapping window; no simultaneous 57/141 changes',
   success='Confirmed absence/restoration; total SKU spend/orders and source freshness; 5% order DRR reference on compatible basis; later retained profit incl failures. No sample-size proof from elapsed 24/72h.',
   technical_scope_ready=False,technical_reason='Production core and cloud driver intentionally allow only SKU57; 685/141 need exact allowlist adaptation, isolated recovery proof, separate disabled deployment and arming approval',
   current_test_authorized=False,backup_operator_confirmed=False,employee_delivery_ready=False))
 # Verify actual deployed core/driver have not accidentally broadened execution.
 core=Path('recovery-source/advertising_agent/agent_actions.py').read_text()
 driver=Path('advertising_sku57_recovery_owner.py').read_text()
 assert 'if campaign.get("id") != 39410834 or nm_id != 1007948808' in core
 assert "'campaign_id':'eq.39410834','nm_id':'eq.1007948808'" in driver
 r['production_recovery_still_exact_57']=True
 updated=copy.deepcopy(memory);updated['test_projects_and_twelve_refresh_20261016']=r
 r['status']='complete';updated=json.loads(json.dumps(updated))
 database('PATCH','telegram_api_cache',params={'cache_key':'eq.'+key,'updated_at':'eq.'+before['updated_at']},body={'payload':updated,'updated_at':datetime.now(timezone.utc).isoformat()})
 if store.cache_get(key)!=updated:raise RuntimeError('Project common memory full readback failed')
 r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('test-projects-twelve',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),wb_writes=0,executable_actions_created=0)))
if r.get('status')!='complete':raise SystemExit(1)
