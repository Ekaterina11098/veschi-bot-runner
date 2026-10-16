"""Pure activation guards; no source or delivery calls."""
from datetime import datetime
def membership_cache_valid(snapshot,now):
 if not isinstance(snapshot,dict):return False
 try:age=(now-datetime.fromisoformat(snapshot['collected_at'].replace('Z','+00:00'))).total_seconds()
 except (KeyError,TypeError,ValueError):return False
 return 0<=age<21600

def recoverable_initial_day(state):
 return (isinstance(state,dict) and state.get('day')=='2026-10-16'
  and state.get('run_id')=='38855942470:1' and state.get('status')=='incomplete'
  and state.get('failed_stage')=='budgets' and not state.get('recovery')
  and [s.get('name') for s in state.get('stages',[])]==['source','source_gaps','membership'])
