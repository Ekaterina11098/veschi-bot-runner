"""Owner requested China MGT preparation only: preview, never WB stock writes."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_china_mgt import collect_preview
ROOT='technical:mgt-china-preview:2026-11-11'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);shared=SharedRequests(store)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared;g.check_run_budget=lambda:None
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None
   result=collect_preview(g)
   with store.transaction():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   seal('mgt-china-preview',result);print(json.dumps(dict(complete=True,stock_writes=0,publication_enabled=False)))
