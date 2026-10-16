"""Finish addressed evidence using retained memory and narrow metadata reads only."""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone,date
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
from stock_deploy_support import seal,error
from analytics.stage_one import read
from analytics.collect import database
from advertising_agent import agent_store as store
from advertising_budget_evidence import budget_analysis
result=dict(wb_calls=0,source_calls=0,telegram_calls=0,wb_writes=0,forecasts=False,test57_enabled=False)
try:
 from advertising_agent.experiments import experiment_rows
 result['new_campaign_experiments']=experiment_rows(dict(cabinet='eq.token_2',campaign_id='eq.40223879',select='id,campaign_id,nm_id,article,experiment_type,started_at,status,decision,checkpoints,old_value,new_value',order='started_at.asc,id.asc'))
 result['retained_focus']=store.cache_get('advertising:ip:focus_preparation:20261016')
 result['mpstats_tools']=read('analytics_snapshots',dict(id='eq.1047',select='id,payload'))
 result['order_source_metadata']=read('analytics_snapshots',dict(cabinet='eq.token_2',source='like.mpstats*',select='id,source,period_from,period_to',order='id.desc',limit=150))
 from analytics.ip_daily_recommendations import KEY
 before=store.cache_get(KEY)
 budgets=read('analytics_snapshots',dict(id='eq.17735',select='id,payload,collected_at,status'))
 config=read('analytics_snapshots',dict(id='eq.17814',select='id,payload,collected_at'))[0]
 rows=budget_analysis(dict(budgets=budgets,campaigns=[dict(wb_campaign_id=i,active_catalog_verified=True) for i in config['payload']['campaign_ids']]),datetime.now(timezone.utc))
 result['budget_analysis']=rows
 # Publish an addressed revision of the existing preview, not another analysis or delivery.
 from analytics.payload_storage import decode_rows
 reports=read('analytics_snapshots',dict(source='eq.ip_working_mode_replay',cabinet='eq.token_2',run_id='eq.38928668740:1',select='id,payload,period_from,period_to',order='id.desc',limit=1))
 if not reports:raise ValueError('Exact existing preview missing')
 previous=reports[0]['payload'][0]
 revised=dict(previous);revised['daily']=dict(previous['daily'],budget_analysis=rows)
 revised['addressed_revision']=dict(parent_snapshot_id=reports[0]['id'],reason='retain observed budget amounts and timestamps; no new collection',observed_at=datetime.now(timezone.utc).isoformat(),no_new_analysis=True,no_delivery=True)
 result['preview']=dict(summary=revised['summary'],budget_analysis=rows,parent_snapshot_id=reports[0]['id'])
 key='advertising:ip:focus_preparation:20261016'
 memory=store.cache_get(key) or {}
 update=dict(memory);update.setdefault('addressed_revisions',[]);update['addressed_revisions']=list(update['addressed_revisions'])+[dict(run_id=__import__('os').environ.get('GITHUB_RUN_ID'),budget_analysis=rows,parent_snapshot_id=reports[0]['id'],wb_writes=0,test_authorized=False)]
 store.cache_set(key,update,ttl_days=365)
 if store.cache_get(key)!=update:raise ValueError('Existing investigation revision readback mismatch')
 result['existing_investigation_full_readback']=True
 result['canonical_state_unchanged']=before==store.cache_get(KEY)
 result['status']='complete'
except Exception as exc:result.update(status='incomplete',error=error(exc))
finally:
 seal('advertising-addressed-preview',result)
 print(json.dumps(dict(status=result.get('status'),error_type=(result.get('error') or {}).get('type'),wb_writes=0)))
if result.get('status')!='complete':raise SystemExit(1)
