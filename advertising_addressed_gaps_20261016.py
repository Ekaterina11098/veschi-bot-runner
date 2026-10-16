"""Narrow remaining metadata and source identity audit, cached only."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'private-source'))
from stock_deploy_support import seal,error
from analytics.stage_one import read
from analytics.collect import _database_transport
from advertising_agent import agent_store as store
r=dict(wb_calls=0,source_calls=0,telegram_calls=0,wb_writes=0)
try:
 ids=[14447,14449,17056,17819,17817,17815]
 r['request_versions']=_database_transport('GET','analytics_snapshots',params=dict(id='in.('+','.join(map(str,ids))+')',select='id,source,period_from,period_to,collected_at,args:payload->0->arguments,request_key:payload->0->>request_key,state:payload->0->>status,info:payload->0->data->data->info,count:payload->0->data->data->>total'))
 caps=read('analytics_snapshots',dict(source='eq.mpstats_connection',cabinet='eq.shared',select='id,payload',order='id.desc',limit=1))
 r['capability_snapshot_id']=caps[0]['id']
 ts=caps[0]['payload'][0]['tools']
 r['relevant_tools']=[t for t in ts if t.get('name') in ('lk_wb_products','lk_wb_card_orders') or (t.get('name','').startswith('lk_wb') and any(x in t.get('name','') for x in ('detail','operation')))]
 r['retained_card_orders_metadata']=read('analytics_snapshots',dict(source='eq.mpstats_lk_wb_card_orders',cabinet='eq.token_2',select='id,period_from,period_to,collected_at,arguments:payload->0->arguments',order='id.desc',limit=40))
 r['retained_card_orders']=[]
 for x in r['retained_card_orders_metadata']:
  if '2026-10-11'<=x['period_from']<='2026-10-12' and x['period_from']==x['period_to']:
   r['retained_card_orders']+=read('analytics_snapshots',dict(id='eq.'+str(x['id']),select='id,payload'))
 r['status']='complete'
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 seal('advertising-addressed-gaps',r)
 print(json.dumps(dict(status=r.get('status'),error_type=(r.get('error') or {}).get('type'))))
if r.get('status')!='complete':raise SystemExit(1)
