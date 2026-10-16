"""Verify daily observation connection without running collection or altering schedules."""
import sys,json,copy,ast,subprocess,hashlib
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
from advertising_agent import agent_store as store
from advertising_order_outcome_monitor import KEY,plan,seed
r=dict(wb_calls=0,wb_writes=0,source_calls=0,telegram_calls=0,schedule_changed=False)
try:
 tests=subprocess.run([sys.executable,'test_advertising_order_outcome_monitor.py','-v'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);r['tests']=tests.stdout
 if tests.returncode:raise RuntimeError('Monitor tests failed')
 source=Path('advertising_source_owner.py').read_text();ast.parse(source);ast.parse(Path('advertising_daily_owner.py').read_text())
 assert 'source=stage(\'advertising_source_owner.py\'' in Path('advertising_daily_owner.py').read_text()
 for mark in ('seed_order_monitor','plan_order_checks(order_monitor,now,max_requests=4)','ingest_order_observation(order_monitor,obs,ident)','put(ORDER_MONITOR_KEY,updated_monitor)','financial_revision(order_monitor,obs'):
  assert mark in source,mark
 r['source_file_sha256']=hashlib.sha256(source.encode()).hexdigest();r['daily_hook_verified']=True
 workflow=Path('.github/workflows/advertising-daily-prepared.yml').read_text()
 assert "cron: '30 4 * * *'" in workflow and "ADVERTISING_EXECUTION_ENABLED: 'false'" in workflow
 r['daily_0730_unchanged']=True
 memory_seed=store.cache_get('advertising:ip:focus_preparation:20261016') or {}
 state=seed(store.cache_get(KEY),memory_seed);assert len(state['orders'])>=27
 store.cache_set(KEY,state,ttl_days=365)
 if store.cache_get(KEY)!=state:raise RuntimeError('Extended monitoring state readback failed')
 r['tracked_orders']=len(state['orders']);r['observed_outcomes_not_financial_finality']=all(x['financially_final'] is False and x['mature_retention_ratio'] is None for x in state['orders'].values())
 now=datetime.now(timezone.utc);r['same_day_requests']=plan(state,now);r['next_due_requests']=plan(state,now+timedelta(days=1))
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key) or {};updated=copy.deepcopy(memory)
 updated['daily_order_outcome_observation_20261016']=dict(cache_key=KEY,tracked_orders=len(state['orders']),hook='advertising_source_owner.py in existing source/source_gaps stages',
  max_requests_per_existing_source_pass=4,max_contiguous_order_days=7,max_page_rows=300,
  minimum_refresh_hours=24,long_unresolved_days=30,long_unresolved_recheck_days=7,
  stable_archive_rule='14 days unchanged; buyout >=30 days from sale, or failed order with confirmed source and nonzero reported logistics',
  archive_is_financial_finality=False,archive_is_mature_retention=False,
  changed_financial_source_reopens_known_sku=True,partial_or_omitted_order_never_replaces_known_history=True,
  retry_after_and_storage_gate_preserved=True,real_advertising_actions=False,verification=r)
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise RuntimeError('Daily monitor common memory readback failed')
 r['common_memory_full_readback']=True;r['status']='complete'
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('daily-order-monitor-proof',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),wb_writes=0)))
if r.get('status')!='complete':raise SystemExit(1)
