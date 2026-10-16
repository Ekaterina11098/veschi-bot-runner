"""Read-only integration acceptance; retain closed facts, never create executable plans."""
import sys,json,copy,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
from stock_deploy_support import seal,error
from analytics.stage_one import read
from advertising_agent import agent_store as store
from advertising_current_promotion import guard,daily_observations
r=dict(wb_calls=0,source_calls=0,telegram_calls=0,wb_writes=0,forecasts=False,test57_enabled=False)
try:
 owner=(ROOT/'advertising_analysis_owner.py').read_text()
 daily=(ROOT/'advertising_daily_owner.py').read_text()
 wf=(ROOT/'.github/workflows/advertising-daily-prepared.yml').read_text()
 assert 'install_dated_budgets()' in owner and 'install_current_promotion()' in owner
 assert "analysis_and_delivery=stage('advertising_analysis_owner.py'" in daily
 assert "cron: '30 4 * * *'" in wf and "ADVERTISING_EXECUTION_ENABLED: 'false'" in wf
 r['daily_integration']=dict(budget_installed=True,current_promotion_installed=True,ordinary_daily_owner_invokes_analysis=True,cron='30 4 * * *',wb_execution=False)
 cfg=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))[0]
 campaign=guard(dict(period_from='2026-10-09',period_to='2026-10-15',campaigns=[dict(wb_campaign_id=40223879,totals={},products=[])]),cfg)['campaigns'][0]
 days=read('analytics_snapshots',dict(source='eq.mpstats_campaign_report',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=20,**{'payload->0->>campaign_id':'eq.12194941','payload->0->>report':'eq.days'}))
 r['current_promotion_control']=dict(campaign['current_promotion'],daily_observations=daily_observations(days,campaign['current_promotion']['first_full_day'],'2026-10-15'))
 assert r['current_promotion_control']['daily_observations']==[]
 # Independent financial-risk decisions and watch/job/action tables are untouched.
 from analytics.ip_daily_recommendations import KEY
 before=store.cache_get(KEY)
 key='advertising:ip:focus_preparation:20261016'
 memory=store.cache_get(key) or {};saved=copy.deepcopy(memory)
 saved['closed_facts_20261016']=dict(no_repeat_without_new_evidence=True,
  budget_display_fixed=True,budgets_twelve_historical_preserved=True,new_campaign_budget_source_run='38932672818',
  finance_source_versions_verified=True,old_logistics_oct9_57_685_reconciled=True,
  daily_campaign_days_9_15_verified=True,financial_finality_not_claimed=True,
  open_only=['sku57_cloud_recovery_not_deployed','mature_current_order_cohorts_685_141','sku122_finance_missing_9_11_12','unlinked_service_operations_11_12'])
 saved['pilot_57_readiness_20261016']=dict(stage='draft_only',execution_authorized=False,
  private_pr26_head='ac3b1c439b2ef1bd6ad9e7e8093c91ecb86ae0db',runner_pr5_head='a57ff06f42afa7bd8d507c5278d64d343cf5f121',
  deployment_complete=False,cloud_recovery_enabled=False,cloud_cadence_seconds_proposed=300,
  backup='registered_owner',backup_channel='registered_advertising_chat',
  required_before_test=['separately_approved_recovery_deployment','fresh_WB_availability_and_settings','current_minimum_and_target_add_eligibility','employee_reservation_no_parallel_edit','exact_start_and_return_deadline','separate_explicit_remove_and_restore_consent'],
  backup_plan_only=['check_target_membership_before_any_manual_recovery','restore_only_target_SKU_if_absent_and_no_conflicting_employee_change','restore_saved_bid_only_when_permitted_and_not_overwriting_employee_change','respect_429_and_verify_readback','independent_personal_deadline_check_if_cloud_or_database_down'],
  actions_created=False,watches_created=False,jobs_created=False,window_19_20_approved=False)
 saved['promotion_control_40223879']=r['current_promotion_control']
 store.cache_set(key,saved,ttl_days=365)
 if store.cache_get(key)!=saved:raise ValueError('Readiness memory full readback failed')
 r['existing_memory_full_readback']=True;r['canonical_state_unchanged']=before==store.cache_get(KEY)
 r['status']='complete'
except Exception as exc:r.update(status='incomplete',error=error(exc))
finally:
 seal('advertising-daily-integration',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'))))
if r.get('status')!='complete':raise SystemExit(1)
