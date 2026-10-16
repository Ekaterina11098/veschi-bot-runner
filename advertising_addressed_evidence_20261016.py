"""Addressed cached evidence audit. No source, Telegram, or WB credentials/calls."""
import sys,json,hashlib,contextlib,io
from pathlib import Path
from datetime import datetime,timezone,date
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
from stock_deploy_support import seal,error
from analytics.stage_one import read
from advertising_agent import agent_store as store
from advertising_cached_finance_reader import install
import analytics.stage_one as stage
install(stage)
from advertising_budget_evidence import budget_analysis
FOCUS={1007948808:'57-NoelBag-burgundy',1123677454:'685-CelineaBag-black',320248210:'141-PamelaBag-brown'}
result=dict(wb_calls=0,source_calls=0,telegram_calls=0,wb_writes=0,forecasts=False,test57_enabled=False)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
try:
 control=store.cache_get('advertising:ip:pr27-controlled:20261016:v1')
 if not control or control.get('status')!='complete':raise ValueError('Exact prior controlled result missing')
 budgets=read('analytics_snapshots',dict(id='eq.17735',select='id,payload,collected_at,status'))
 config=read('analytics_snapshots',dict(id='eq.17814',select='id,payload,collected_at'))[0]
 ids=config['payload']['campaign_ids']
 result['budgets']=budget_analysis(dict(budgets=budgets,campaigns=[dict(wb_campaign_id=i,active_catalog_verified=True) for i in ids]),datetime.now(timezone.utc))
 result['budget_snapshot_digest']=digest(budgets)
 allids=set()
 for version in ['before','after']:
  for row in control[version]['items'].values():allids.update(row.get('component_snapshot_ids',[]))
 snapshots=read('analytics_snapshots',dict(id='in.('+','.join(map(str,sorted(allids)))+')',select='id,source,cabinet,period_from,period_to,collected_at,payload'))
 byid={r['id']:r for r in snapshots}
 def rows(s):return s['payload'][0]['data']['data']['data']
 def ident(r):return str(r.get('p_id'))
 result['versions']={}
 catalogs={}
 for version in ['before','after']:
  entries=[]
  selectedids=control[version]['items']['1007948808']['component_snapshot_ids']
  for sid in selectedids:
   s=byid[sid];rr=rows(s);catalogs[sid]={ident(r):r for r in rr}
   focus=[]
   for r in rr:
    if any(str(n) in str(r.get('nm_id',r.get('nmId',''))) or a in str(r) for n,a in FOCUS.items()):focus.append(r)
   entries.append(dict(id=sid,day=s['period_from'],observed_at=s['collected_at'],payload_sha256=digest(s['payload']),count=len(rr),focus_rows=focus))
  result['versions'][version]=entries
 union=set().union(*(set(v) for v in catalogs.values()))
 result['catalog_differences']=[]
 for sid,items in catalogs.items():
  missing=union-set(items)
  if missing:
   result['catalog_differences'].append(dict(snapshot_id=sid,day=byid[sid]['period_from'],missing=[dict(identity=k,retained_examples=[dict(snapshot_id=other,row=catalogs[other][k]) for other in catalogs if k in catalogs[other]][:2]) for k in sorted(missing)]))
 result['profit_changes']=control['profit_changes']
 result['focus_financial_facts']={n:dict(before=control['before']['items'][n],after=control['after']['items'][n]) for n in control['after']['items']}
 from analytics.ip_operation_diagnosis import collect_cached
 result['retained_operations']=collect_cached(read,date(2026,10,9),date(2026,10,15),list(FOCUS.items()))
 result['campaign_configuration']=config
 previous=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',id='lt.17814',select='id,payload,collected_at',order='id.desc',limit=1))
 result['previous_configuration']=previous
 result['new_campaign_products']=read('analytics_snapshots',dict(id='in.(17821,17823)',select='id,payload,collected_at,period_from,period_to,source'))
 # Existing experiment history only, bounded read; never create/modify an experiment.
 from analytics.ip_daily_recommendations import KEY
 result['decision_state_digest']=digest(store.cache_get(KEY))
 result['metadata_sources']=read('analytics_snapshots',dict(cabinet='eq.token_2',source='in.(mpstats_product_order_detail,mpstats_lk_wb_orders,ip_focus_followup)',select='id,source,period_from,period_to,collected_at',order='id.desc',limit=30))
 result['status']='complete'
except Exception as exc:
 result.update(status='incomplete',error=error(exc))
finally:
 seal('advertising-addressed-evidence',result)
 print(json.dumps(dict(status=result.get('status'),error_type=(result.get('error') or {}).get('type'),wb_writes=0)))
if result.get('status')!='complete':raise SystemExit(1)
