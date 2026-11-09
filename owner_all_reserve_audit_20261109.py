"""Read-only all-SKU posted-debit audit; no stock or runtime-ledger writes."""
import json,time
from datetime import datetime,timedelta,timezone
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_current_order_reserve import group_context,reconcile_current
from stock_unposted_source import ms_demands,ms_headers,ms_rows,bind_ozon_groups
ROOT='technical:owner-all-reserve-audit:2026-11-09'
LEDGER='technical:stock-shared:v1:6bca9c999b2927d674a432e675d21223d1518826829b2e82a9339b397a672511'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True)
   ledger=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',(LEDGER,)).fetchone()[0])['value']
   shared=SharedRequests(s);g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
   units=ledger['open_units'];context=group_context(ledger['order_catalog'])
   since=(min(datetime.fromisoformat(u['created_at'].replace('Z','+00:00')) for u in units)-timedelta(days=1)).astimezone(timezone(timedelta(hours=3))).strftime('%Y-%m-%d %H:%M:%S')
   docs,store_id,manifest=ms_demands(g,since,{u['article'] for u in units},units)
   physical,unresolved=g.load_ms_stocks_dict()
   _,store2,after=ms_headers(g,since)
   orders=ms_rows(g,g.MS_API+'/entity/customerorder',filter='moment>='+since)
   if store2!=store_id or after!=manifest['demands'] or digest(sorted((r['id'],r.get('updated')) for r in orders))!=manifest['orders']:
    raise Stopped('MS documents changed during all-SKU audit')
   before=reconcile_current(physical,units,ledger['documents'],store_id,context)
   # Read-only copies: resolve complete Ozon posting sets exactly as production.
   bind_ozon_groups(ledger['order_catalog']+units,docs)
   context=group_context(ledger['order_catalog'])
   errors={}
   for u in units:
    if any(d.get('unmapped') and d.get('group')==u['group'] for d in docs):
     errors[u['article']]='Unmapped linked MS debit composition; cannot release'
   after=reconcile_current(physical,units,docs,store_id,context,errors)
   rows=[]
   for art in sorted({u['article'] for u in units}):
    old=before['pending'].get(art,0);new=after['pending'].get(art,0)
    if old!=new:
     rows.append(dict(article=art,physical=physical.get(art),reserved_before=old,reserved_after=new,
      free_before=before['available_moscow'].get(art),free_after=after['available_moscow'].get(art),
      released_capacity=after['available_moscow'].get(art,0)-before['available_moscow'].get(art,0),
      units=[u for u in units if u['article']==art],
      evidence=[e for e in after['current_debit_evidence'] if e['article']==art],
      documents=[d for d in docs if art in d.get('quantities',{})]))
   receipt=dict(complete=True,at=time.time(),business_writes=0,runtime_ledger_writes=0,
    ledger_observed_at=ledger['source_observed_at'],since=since,catalog_count=len(ledger['order_catalog']),
    open_unit_rows=len(units),articles=len({u['article'] for u in units}),changes=rows,
    reserve_before=sum(before['pending'].values()),reserve_after=sum(after['pending'].values()),
    blocked=after['blocked'],all_pending=after['pending'],physical=physical,
    all_evidence=after['current_debit_evidence'],documents=docs,units=units)
   with s.transaction():s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
     (ROOT,canonical(receipt),'{}',digest({}),'technical-no-executor',time.time()))
   seal('all-reserve-audit',receipt)
   print(json.dumps({k:receipt[k] for k in ('complete','articles','reserve_before','reserve_after','business_writes','runtime_ledger_writes')}))
