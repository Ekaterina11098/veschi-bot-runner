"""One-time owner-confirmed cancelled55over72h ledger cleanup; never writes stock."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_owner_cancel_age_release import release,created_epoch
from stock_current_order_reserve import group_context,reconcile_current,identity
ROOT='technical:owner-cancel55-72h-release:2026-11-09'
LEDGER='technical:stock-shared:v1:6bca9c999b2927d674a432e675d21223d1518826829b2e82a9339b397a672511'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True)
   done=s.sql('SELECT snapshot FROM stock_runs WHERE id=?',(ROOT,)).fetchone()
   if done and json.loads(done[0]).get('complete'):print('Owner age cleanup already complete; no repeat')
   else:
    audit=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:owner55-supply-debit-audit:2026-11-09',)).fetchone()[0])
    base=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:owner-cancel57-audit:2026-11-09',)).fetchone()[0])
    targets=audit['targets'];expected=[u for u in base['candidates'] if u['id'] not in('6155723784','6209276833')]
    if not audit.get('complete') or len(targets)!=55 or {identity(u) for u in targets}!={identity(u) for u in expected}:raise Stopped('Exact owner55scope changed')
    shared=SharedRequests(s);g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
    g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
    statuses={}
    for cab in sorted({u['cabinet'] for u in targets}):
     ids=[int(u['id']) for u in targets if u['cabinet']==cab]
     rows=g.api('POST',g.WB_MARKET+'/api/v3/orders/status',g.cabinet_tokens()[cab],json={'orders':ids}).get('orders')
     if not isinstance(rows,list) or len(rows)!=len(ids) or {r.get('id') for r in rows}!=set(ids):raise Stopped('Fresh55cancellation status coverage incomplete')
     statuses.update({str(cab)+':'+str(r['id']):r for r in rows})
    physical,unresolved=g.load_ms_stocks_dict();now=time.time()
    with s.transaction():
     raw=s.sql('SELECT snapshot FROM stock_runs WHERE id=? FOR UPDATE',(LEDGER,)).fetchone()[0]
     payload=json.loads(raw);ledger=payload['value']
     updated,outcome=release(ledger,targets,statuses,now,ROOT)
     for key in ('source_observed_at','ms_scan_from','order_catalog_observed_at','tracking_started_at'):
      if ledger.get(key)!=updated.get(key):raise Stopped('Original reserve observation/checkpoint changed')
     if not set(ledger['closed_ids']).issubset(updated['closed_ids']):raise Stopped('Prior confirmed closed orders changed')
     before=reconcile_current(physical,ledger['open_units'],ledger['documents'],'3c67619d-f25d-11ee-0a80-0c6f000a027a',group_context(ledger['order_catalog']))
     after=reconcile_current(physical,updated['open_units'],updated['documents'],'3c67619d-f25d-11ee-0a80-0c6f000a027a',group_context(updated['order_catalog']))
     released=set(outcome['released']);arts={u['article'] for u in targets if identity(u) in released}
     details={a:dict(physical=physical.get(a),reserve_before=before['pending'].get(a,0),reserve_after=after['pending'].get(a,0),
      free_before=before['available_moscow'].get(a),free_after=after['available_moscow'].get(a)) for a in arts}
     receipt=dict(complete=True,at=now,owner_confirmation='Owner9Nov:exact55already-cancelled orders older than72hours no longer reserve MSK;active orders excluded',
      scope_count=55,eligible_by_age=sum(now-created_epoch(u)>72*3600 for u in targets),released_units=len(released),
      outcome=outcome,statuses=statuses,articles=details,original_source_observed_at=ledger['source_observed_at'],
      source_times_preserved=True,business_writes=0,evening_run_not_restarted=True,claims_untouched=True)
     payload['value']=updated
     s.sql('UPDATE stock_runs SET snapshot=? WHERE id=?',(canonical(payload),LEDGER))
     s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
      (ROOT,canonical(receipt),'{}',digest({}),'technical-no-executor',now))
    seal('owner-cancel55-72h-release',receipt)
    print(json.dumps(dict(complete=True,released_units=receipt['released_units'],held=len(outcome['held']),already_closed=len(outcome['already_closed']),business_writes=0)))
