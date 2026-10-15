"""Offline owner proof of exact approved analysis and delivery; DB only."""
import os,sys,copy,json,contextlib,io,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report=dict(wb_writes=0,source_calls=0,telegram_calls=0)
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  from analytics.stage_one import read,daily_ready
  from analytics.collect import database
  from advertising_agent import agent_store as store
  from analytics.ip_daily_recommendations import KEY
  from datetime import datetime,timezone
  params=dict(source='eq.ip_limited_working_review',cabinet='eq.token_2',run_id='eq.38818518560:1',select='id,payload,period_from,period_to,collected_at',order='id.desc',limit=1)
  rows=read('analytics_snapshots',params);again=read('analytics_snapshots',params)
  if rows!=again or len(rows)!=1:raise RuntimeError('Exact complete result readback mismatch')
  full=rows[0]['payload'][0]
  raw=database('GET','analytics_snapshots',params=dict(id='eq.'+str(rows[0]['id']),select='payload'))[0]['payload'][0]
  report.update(snapshot_id=rows[0]['id'],packed_payload_sha256=raw['sha256'],full_decoded_readback_verified=True,
    summary=full['summary'],period_from=rows[0]['period_from'],period_to=rows[0]['period_to'],
    new_day_complete=daily_ready('token_2','2026-10-15',datetime.now(timezone.utc)),
    campaign_summary=full['campaign_summary'],input_lineage=full.get('input_lineage'),
    delivery_health=store.cache_get('advertising:ip:delivery_health:v1'))
  state=store.cache_get(KEY);approval=store.cache_get('advertising:ip:limited_rollout:v1')
  assert state==store.cache_get(KEY) and approval==store.cache_get('advertising:ip:limited_rollout:v1')
  report.update(final_state=state,approval=approval,history_memory=store.cache_get('advertising:ip:historical_learning:v1'))
  report['open_investigations']=full['investigations']
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-final-proof',report)
 print(json.dumps({'source_calls':0,'telegram_calls':0,'verified':report.get('full_decoded_readback_verified'),'error_type':(report.get('error') or {}).get('type')}))
