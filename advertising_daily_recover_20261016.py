"""Continue ONLY the proven unexecuted tail of the controlled 16 Oct pass."""
import os,json
from datetime import datetime,timezone
import advertising_daily_owner as daily
from advertising_daily_runtime_guard import recoverable_initial_day
store=daily.store
key='advertising:ip:daily_run:v1:2026-10-16'
state=store.cache_get(key)
if not recoverable_initial_day(state):raise RuntimeError('Exact untouched pre-analysis failure required; no replay')
state['recovery']=dict(run_id=os.environ['GITHUB_RUN_ID']+':'+os.environ.get('GITHUB_RUN_ATTEMPT','1'),
 original_failure='expired membership accepted by old daily cache; budgets rejected before any call',
 started_at=datetime.now(timezone.utc).isoformat(),analysis_previously_executed=False)
def save():
 store.cache_set(key,state,ttl_days=365)
 if store.cache_get(key)!=state:raise RuntimeError('Continuation full readback mismatch')
save()
for name in ('membership','budgets','analysis_and_delivery','budget_completion'):
 state['in_progress_stage']=name
 state['recovery']['last_stage_intent_at']=datetime.now(timezone.utc).isoformat()
 save()
 try:
  value=daily.stages[name]()
  state['stages'].append(dict(name=name,status='recorded_continuation',result=value))
  state.pop('in_progress_stage',None);save()
 except TimeoutError:
  if name not in ('budgets','budget_completion'):raise
  state['stages'].append(dict(name=name,status='incomplete_budget_evidence',unknown_is_not_zero=True))
  state.pop('in_progress_stage',None);save()
 except Exception as exc:
  state.update(status='incomplete',failed_stage=name,error_type=type(exc).__name__)
  save();daily.seal('advertising-daily',state)
  print(json.dumps(dict(status=state['status'],failed_stage=name,error_type=type(exc).__name__)))
  raise
state.update(status='completed_with_explicit_source_limits')
state.pop('failed_stage',None);state.pop('error_type',None);save()
daily.seal('advertising-daily',state)
print(json.dumps(dict(status=state['status'],wb_writes=0)))
