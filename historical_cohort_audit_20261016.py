"""Bounded audit of retained historical cohorts only; no external source calls."""
import sys,json,copy,hashlib
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from analytics.stage_one import read
from advertising_agent import agent_store as store
from stock_deploy_support import seal,error
r=dict(source_calls=0,wb_calls=0,wb_writes=0,telegram_calls=0,cohorts=[],candidates=[])
def lists(x):
 if isinstance(x,list):
  yield x
  for v in x:
   if isinstance(v,(dict,list)):yield from lists(v)
 elif isinstance(x,dict):
  for v in x.values():
   if isinstance(v,(dict,list)):yield from lists(v)
def state(x):
 if x.get('refund_dt') or (x.get('refunded_times') or 0)>0:return 'returned'
 if x.get('is_canceled_order')==1:return 'cancelled'
 if not x.get('billed_times') and (x.get('backlogistic_times') or 0)>0:return 'nonbuyout_reverse'
 if x.get('sale_dt') and (x.get('billed_times') or 0)>0:return 'buyout_not_final'
 return 'unresolved'
try:
 sources='in.(mpstats_lk_wb_card_orders,mpstats_lk_wb_sales_tape,mpstats_lk_wb_sales_tape_complete)'
 meta=[]
 for direction in ('asc','desc'):
  meta+=read('analytics_snapshots',dict(cabinet='eq.token_2',source=sources,select='id,source,period_from,period_to,collected_at,status,pid:payload->0->arguments->>value,obsstatus:payload->0->>status',order='id.'+direction,limit=150))
 metas={x['id']:x for x in meta}
 r['metadata']=sorted(metas.values(),key=lambda x:x['id']);r['metadata_query_bounded']=True
 selected=[];seen=set()
 for m in sorted(metas.values(),key=lambda x:x['id'],reverse=True):
  if m['source']=='mpstats_lk_wb_card_orders' and str(m.get('pid')) not in ('139147637','124391695'):continue
  ident=(m['source'],m['period_from'],m['period_to'],m.get('pid'))
  if ident in seen:continue
  seen.add(ident)
  if len(selected)>=12:break
  selected.append(m)
 for m in selected:
  data=read('analytics_snapshots',dict(id='eq.'+str(m['id']),select='payload'))[0]['payload']
  encoded=json.dumps(data,ensure_ascii=False)
  if len(encoded)>12_000_000:raise RuntimeError('Retained source audit size bound')
  matches={};conflicts=[]
  for values in lists(data):
   for row in values:
    if not isinstance(row,dict) or str(row.get('nm_id')) not in ('1123677454','320248210') or not row.get('gnumber'):continue
    gn=str(row['gnumber'])
    if gn in matches and matches[gn]!=row:conflicts.append(gn)
    matches[gn]=row
  obs=data[0] if isinstance(data,list) and data and isinstance(data[0],dict) else {}
  body=obs.get('data',{})
  r['candidates'].append(dict(**m,total=body.get('total') if isinstance(body,dict) else None,matching_rows=list(matches.values()),identity_conflicts=conflicts))
  for nm in (1123677454,320248210):
   rows=[x for x in matches.values() if x['nm_id']==nm]
   if not rows:continue
   c=dict(snapshot_id=m['id'],source=m['source'],period_from=m['period_from'],period_to=m['period_to'],observed_at=m['collected_at'],nm_id=nm,
    orders=len(rows),counts=dict(Counter(state(x) for x in rows)),unresolved=[x['gnumber'] for x in rows if state(x)=='unresolved'],
    actual_order_dates=sorted({x['order_dt'][:10] for x in rows}),prices=sorted({x.get('retail_price_withdisc_rub') for x in rows if type(x.get('retail_price_withdisc_rub')) in (int,float)}),
    delivery_modes=dict(Counter(str(x.get('is_fbs')) for x in rows)),regions=dict(Counter(str(x.get('region')) for x in rows)),
    maturity_confirmed=False,selection_bias='Never compute buyout ratio only among resolved orders',
    financial_finality='not supplied by source')
   r['cohorts'].append(c)
 key='advertising:ip:focus_preparation:20261016';memory=store.cache_get(key) or {}
 r['retained_unit_examples']=memory['decision_readiness_20261016']['retained_unit_examples']
 r['campaign_context']=memory.get('decision_readiness_20261016')
 r['status']='complete'
 updated=copy.deepcopy(memory);updated['historical_cohort_audit_20261016']=r
 store.cache_set(key,updated,ttl_days=365)
 if store.cache_get(key)!=updated:raise RuntimeError('Common memory full readback failed')
 r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('historical-cohort-audit',r)
 print(json.dumps(dict(status=r.get('status'),cohorts=len(r['cohorts']),error_type=(r.get('error') or {}).get('type'))))
if r.get('status')!='complete':raise SystemExit(1)
