"""Inspect retained WB sale/return ledger for older known target order identities only."""
import sys,json,copy
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.stage_one import read
from advertising_agent import agent_store as store
from stock_deploy_support import seal,error
r=dict(source_calls=0,wb_calls=0,wb_writes=0,telegram_calls=0)
def lists(x):
 if isinstance(x,list):
  yield x
  for v in x:
   if isinstance(v,(dict,list)):yield from lists(v)
 elif isinstance(x,dict):
  for v in x.values():
   if isinstance(v,(dict,list)):yield from lists(v)
try:
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key)
 orders_source=next(x for x in memory['mature_cohort_risk_20261016']['cohort_sources'] if x['source']=='orders')
 orders={x['srid']:x for x in orders_source['matching_rows'] if x['date'][:10]<'2026-10-04'}
 metas=read('analytics_snapshots',dict(source='eq.sales',cabinet='eq.token_2',status='eq.complete',select='id,source,period_from,period_to,collected_at,status',order='id.desc',limit=20))
 r['sales_metadata']=metas;r['matching_sales']=[]
 selected=[];seen=set()
 for meta in metas:
  identity=(meta['period_from'],meta['period_to'])
  if identity in seen:continue
  seen.add(identity);selected.append(meta)
  if len(selected)>=3:break
 for meta in selected:
  value=read('analytics_snapshots',dict(id='eq.'+str(meta['id']),select='payload'))[0]['payload']
  if len(json.dumps(value,ensure_ascii=False))>15_000_000:raise RuntimeError('Saved sales evidence size bound')
  matches={}
  for rows in lists(value):
   for x in rows:
    if not isinstance(x,dict) or str(x.get('nmId')) not in ('1123677454','320248210'):continue
    identity=str(x.get('saleID') or x.get('srid'))+':'+str(x.get('lastChangeDate') or x.get('date'))
    matches[identity]=x
  r['matching_sales'].append(dict(**meta,rows=list(matches.values())))
 r['older_order_rows']=list(orders.values());r['status']='complete'
 updated=copy.deepcopy(memory);updated['older_sales_ledger_audit_20261016']=r
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise RuntimeError('Older sales ledger readback failed')
 r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('older-sales-ledger-audit',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'),sources=len(r.get('matching_sales',[])))))
if r.get('status')!='complete':raise SystemExit(1)
