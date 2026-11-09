"""Exact 57-order cancellation verification; business read endpoints only."""
import json,time
from datetime import datetime,timezone,timedelta
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_wb_supply_history import paged
ROOT='technical:owner-cancel57-audit:2026-11-09'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True);shared=SharedRequests(s)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
   base=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:owner-all-reserve-audit:2026-11-09',)).fetchone()[0])
   candidates=[u for u in base['units'] if u['cabinet']<3 and u.get('supplier_status') in ('new','confirm') and u.get('wb_status')=='canceled_by_client']
   if len(candidates)!=57:raise Stopped('Original57 identity coverage changed')
   result=dict(complete=False,started=time.time(),business_writes=0,runtime_ledger_writes=0,candidates=candidates,cabinets={})
   def save():
    with s.transaction():s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
     (ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   save()
   for i in sorted({u['cabinet'] for u in candidates}):
    token=g.cabinet_tokens()[i];selected=[u for u in candidates if u['cabinet']==i];ids=[int(u['id']) for u in selected]
    item=dict(ids=ids,errors={});result['cabinets'][str(i)]=item
    item['statuses']=g.api('POST',g.WB_MARKET+'/api/v3/orders/status',token,json={'orders':ids})
    try:item['histories']=g.api('POST',g.WB_MARKET+'/api/v3/orders/status/history',token,json={'orders':ids})
    except Exception as exc:item['errors']['history']=str(exc)
    save()
    first=min(datetime.fromisoformat(u['created_at'].replace('Z','+00:00')) for u in selected)-timedelta(seconds=1)
    now=datetime.now(timezone.utc)
    raw=paged(g,token,'/api/v3/orders',dict(dateFrom=int(first.timestamp()),dateTo=int(now.timestamp())))
    item['raw_orders']=[r for k,r in raw.items() if int(k) in ids]
    save()
   result['complete']=True;result['received_at']=time.time();save();seal('cancel57-audit',result)
   print(json.dumps(dict(complete=True,candidates=len(candidates),business_writes=0)))
