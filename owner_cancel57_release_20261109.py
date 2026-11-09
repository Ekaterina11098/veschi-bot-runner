"""Owner-authorized exact early cancellation release; no marketplace stock writes."""
import json,time
from pathlib import Path
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_current_order_reserve import group_context,reconcile_current
from stock_owner_cancel_release import release
ROOT='technical:owner-cancel57-release:2026-11-09'
LEDGER='technical:stock-shared:v1:6bca9c999b2927d674a432e675d21223d1518826829b2e82a9339b397a672511'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True)
   done=s.sql('SELECT snapshot FROM stock_runs WHERE id=?',(ROOT,)).fetchone()
   if done and json.loads(done[0]).get('complete'):print('Already released; no repeat')
   else:
    origin=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:owner-debit2-reserve-repair:2026-11-09',)).fetchone()[0])
    if not origin.get('complete'):raise Stopped('Required complete current reconciliation missing')
    proof_path=Path(__import__('stock_owner_cancel_release').__file__).with_name('stock_owner_cancel_release_20261109_proofs.json')
    proofs=json.loads(proof_path.read_text())
    if {p['identity'] for p in proofs}!={'2:6155723784:597-noelbag-zbeige','2:6209276833:575-angelabag-black'}:raise Stopped('Exact owner-approved proof scope changed')
    shared=SharedRequests(s);g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
    g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
    ids=[int(p['order_key'].split(':')[1]) for p in proofs]
    rows=g.api('POST',g.WB_MARKET+'/api/v3/orders/status',g.cabinet_tokens()[2],json={'orders':ids}).get('orders')
    if not isinstance(rows,list) or {r.get('id') for r in rows}!=set(ids) or len(rows)!=len(ids):raise Stopped('Fresh cancellation status coverage incomplete')
    statuses={'2:'+str(r['id']):r for r in rows}
    physical,unresolved=g.load_ms_stocks_dict()
    with s.transaction():
     raw=s.sql('SELECT snapshot FROM stock_runs WHERE id=? FOR UPDATE',(LEDGER,)).fetchone()[0]
     payload=json.loads(raw);ledger=payload['value']
     updated,keys=release(ledger,proofs,origin['raw57'],statuses,time.time(),ROOT)
     for key in ('source_observed_at','ms_scan_from','order_catalog_observed_at','tracking_started_at'):
      if ledger.get(key)!=updated.get(key):raise Stopped('Original ledger checkpoint changed')
     if not set(ledger['closed_ids']).issubset(updated['closed_ids']):raise Stopped('Closed orders changed')
     before=reconcile_current(physical,ledger['open_units'],ledger['documents'],'3c67619d-f25d-11ee-0a80-0c6f000a027a',group_context(ledger['order_catalog']))
     after=reconcile_current(physical,updated['open_units'],updated['documents'],'3c67619d-f25d-11ee-0a80-0c6f000a027a',group_context(updated['order_catalog']))
     arts={p['row']['supplierArticle'].casefold() for p in proofs}
     summary={a:dict(physical=physical.get(a),reserve_before=before['pending'].get(a,0),reserve_after=after['pending'].get(a,0),
       free_before=before['available_moscow'].get(a),free_after=after['available_moscow'].get(a)) for a in arts}
     receipt=dict(complete=True,at=time.time(),business_writes=0,released_orders=keys,released_units=len(keys),remaining_candidates=55,
       articles=summary,proofs=proofs,current_statuses=statuses,prior_ledger_digest=digest(ledger),new_ledger_digest=digest(updated),
       original_source_observed_at=ledger['source_observed_at'],source_times_preserved=True)
     payload['value']=updated
     s.sql('UPDATE stock_runs SET snapshot=? WHERE id=?',(canonical(payload),LEDGER))
     s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
       (ROOT,canonical(receipt),'{}',digest({}),'technical-no-executor',time.time()))
    seal('owner-cancel57-release',receipt)
    print(json.dumps(dict(complete=True,released_units=len(keys),remaining_candidates=55,business_writes=0,articles=summary)))
