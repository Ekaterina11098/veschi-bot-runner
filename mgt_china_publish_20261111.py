"""Owner command: exact18 articles, China MS pool -> Guangzhou2308581."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal,error
from stock_operation_store import Store,canonical,digest
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_china_mgt_publish import publish,ROOT,saved
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);shared=SharedRequests(store)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared;g.check_run_budget=lambda:None
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None
   try:
    result=publish(g,store)
    seal('mgt-china-publication',result)
    print(json.dumps(dict(execution_complete=result['execution_complete'],articles=len(result['confirmed_articles']))))
   except Exception as exc:
    with store.transaction():
     root=saved(store)
     if root:store.event(ROOT,None,'runner_stopped',error(exc))
     else:
      ident=ROOT+':diagnostic'
      store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ident,canonical(error(exc)),'{}',digest({}),'technical-no-executor',time.time()))
    seal('mgt-china-publication-error',error(exc));raise

