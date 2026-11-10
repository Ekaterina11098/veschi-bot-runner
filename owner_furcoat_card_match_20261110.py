"""Read-only full furcoat card/assortment identity audit; no stock execution."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_approved_warehouses import install
ROOT='technical:owner-furcoat-card-match:2026-11-10'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);shared=SharedRequests(store)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
   g.STOCK_FURCOAT_ENABLED=True;install(g)
   result=dict(started=time.time(),business_writes=0,cards=[])
   for i,token in enumerate(g.cabinet_tokens()):
    cards=g.get_real_wb_cards_and_scores(token)
    result['cards'].append([dict(article=c.get('vendorCode'),nmID=c.get('nmID'),sizes=c.get('sizes'),photos=bool(c.get('photos'))) for c in cards if 'furcoat' in str(c.get('vendorCode','')).casefold()])
   ms=g.ms_rows(g.MS_API+'/entity/assortment',filter='archived=false;archived=true')
   result['ms_products']=[dict(article=p.get('article'),id=p.get('id'),name=p.get('name'),barcodes=p.get('barcodes')) for p in ms if 'furcoat' in str(p.get('article','')).casefold()]
   result.update(complete=True,finished_at=time.time())
   with store.transaction():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   seal('owner-furcoat-card-match',result)
   print(json.dumps(dict(complete=True,business_writes=0)))
