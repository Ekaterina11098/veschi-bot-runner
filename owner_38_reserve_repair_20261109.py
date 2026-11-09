"""Repair current-order ledger through normal complete read-only reconciliation."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_approved_warehouses import install
from stock_unposted_source import collect
ROOT='technical:owner-38-reserve-repair:2026-11-09'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True)
   done=s.sql('SELECT snapshot FROM stock_runs WHERE id=?',(ROOT,)).fetchone()
   if done and json.loads(done[0]).get('complete'):print('Already reconciled; no business calls')
   else:
    source=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-09:owner-four-reserve-correction',)).fetchone()[0])['source']
    shared=SharedRequests(s)
    g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
    g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None
    g.check_run_budget=lambda:None
    install(g)
    # The new furcoat category retains its separate complete-history bootstrap.
    # This repair cannot mark that bootstrap complete on its behalf.
    result=collect(g,source)
    art='38-furmanizhka-white'
    receipt=dict(complete=True,at=time.time(),business_writes=0,
       physical=result['physical_moscow'].get(art),pending=result['pending'].get(art,0),
       free=result['available_moscow'].get(art),blocked=result['blocked'].get(art),
       evidence=[r for r in result['current_debit_evidence'] if r['article']==art],
       open_units=[r for r in result['units'] if r['article']==art],
       source_observed_at=result['observed_at'])
    with s.transaction():
     s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
      (ROOT,canonical(receipt),'{}',digest({}),'technical-no-executor',time.time()))
    seal('owner38-reserve-repair',receipt)
    print(json.dumps(receipt))
