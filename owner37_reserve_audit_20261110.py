"""Read-only current37 reserve and posted MSK debit audit after warehouse transfer."""
import json,time,math
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_approved_warehouses import install,APPROVED
from stock_unposted_source import collect
from stock_regular_service import restored_cards
from stock_ozon_source import collect as ozon_collect
ROOT='technical:owner37-reserve-audit:2026-11-10:1406-transfer'
PROPOSALS={'37-furmanizhka-dbrown':0}
class ReadOnlyLedgerShared(SharedRequests):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.ledger_candidate=None
 def get(self,key,*a,**kw):
  if key.startswith('stock-current-order-reserve-v') and self.ledger_candidate is not None:return self.ledger_candidate
  return super().get(key,*a,**kw)
 def put(self,key,value,ttl):
  if key.startswith('stock-current-order-reserve-v'):
   self.ledger_candidate=value
   return
  return super().put(key,value,ttl)
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   s=Store(db,postgres=True);shared=ReadOnlyLedgerShared(s)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
   install(g)
   source=json.loads(s.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-10:0700',)).fetchone()[0])['source']
   result=dict(complete=False,started=time.time(),business_writes=0,runtime_ledger_writes=0,rows={},stage='orders_initial')
   def save():
    with s.transaction():s.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',
     (ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   save()
   initial=collect(g,source)
   result['initial_orders_observed_at']=initial['observed_at'];result['stage']='fresh_fbs';save()
   cards=restored_cards(source);wb=[];wb_evidence=[]
   for cab in range(3):
    sizes=g.article_size_ids(cards[cab]);ids=sorted({v for art in PROPOSALS for v in sizes.get(art,set())})
    observed=time.time();data=g.api('POST',g.WB_MARKET+'/api/v3/stocks/'+str(APPROVED[cab][0]),g.cabinet_tokens()[cab],json={'chrtIds':ids},retry_read_network=True)
    rows=data.get('stocks')
    if not isinstance(rows,list):raise Stopped('Fresh WB stock rows missing')
    amounts={}
    for row in rows:
     ident=row.get('chrtId');qty=row.get('amount')
     if ident in amounts or ident not in ids or type(qty) not in(int,float) or not math.isfinite(qty) or qty<0 or int(qty)!=qty:
      raise Stopped('Fresh WB stock identity/quantity invalid')
     amounts[ident]=int(qty)
    values={}
    for art in PROPOSALS:
     selected=sizes.get(art,set())
     values[art]=None if not selected else (sum(amounts[v] for v in selected) if selected.issubset(amounts) else 'unknown')
    wb.append(values);wb_evidence.append(dict(cabinet=cab,warehouse=APPROVED[cab][0],observed_at=observed,amounts=amounts))
   ozon=ozon_collect(g,set(PROPOSALS),saved_orders=source['ozon']['sales'])
   result.update(wb_evidence=wb_evidence,ozon_stocks=ozon['stocks'],ozon_observed_at=ozon['started'],stage='orders_tail');save()
   # Fresh accepted-order tail follows FBS reads; reconcile fresh MS physical
   # and posted debits again using only ephemeral in-memory ledger candidates.
   final=collect(g,source,units=shared.ledger_candidate['order_catalog'])
   result['source_observed_at']=final['observed_at'];result['physical_observed_at']=final['physical_observed_at'];result['received_at']=final['received_at']
   result['reserve_proof']=[p for p in final.get('proof',[]) if p['article'] in PROPOSALS]
   journal={}
   args=tuple(PROPOSALS)
   pending=s.sql("SELECT l.article,o.state,o.body,o.run FROM stock_sku_locks l JOIN stock_operations o ON o.run=l.owner_run WHERE l.article IN ("+','.join('?' for _ in args)+") AND o.state IN ('prepared','sent','uncertain')",args).fetchall()
   for art,state,body,run in pending:journal.setdefault(art,[]).append(dict(state=state,body=json.loads(body),run=run))
   for art,original_target in PROPOSALS.items():
    stocks=[wb[i][art] for i in range(3)]+[ozon['stocks'].get(art)]
    physical=final['physical_moscow'].get(art);held=final['pending'].get(art,0);free=final['available_moscow'].get(art)
    known=all(v is None or type(v) is int for v in stocks)
    total=sum(v for v in stocks if type(v) is int) if known else None
    china=stocks[2];other=sum(v for i,v in enumerate(stocks) if i!=2 and type(v) is int) if known else None
    maximum=max(0,free-other) if free is not None and known else None
    headroom=max(0,free-total) if free is not None and known else None
    blocked=final['blocked'].get(art)
    if blocked or free is None:decision='hold_incomplete_reserve_or_msk'
    elif journal.get(art):decision='hold_unresolved_journal_operation'
    elif not known or type(china) is not int:decision='hold_unknown_fbs'
    elif china>=original_target:decision='already_at_report_target'
    elif headroom>=1:decision='can_add_one'
    else:decision='cannot_add_one'
    result['rows'][art]=dict(physical_msk=physical,pending_unposted=held,free_msk=free,
      fbs=stocks,total_fbs=total,china_current=china,other_fbs=other,max_china_total=maximum,
      total_growth_headroom=headroom,report_china_target=original_target,
      original_report_target_allowed=(original_target<=maximum) if maximum is not None else None,
      safe_add_one_target=(china+1) if decision=='can_add_one' else None,decision=decision,
      blocked=blocked,journal_pending=journal.get(art,[]),
      current_orders=[u for u in final['units'] if u['article']==art],
      debit_evidence=[e for e in final['current_debit_evidence'] if e['article']==art])
   result.update(complete=True,stage='complete',finished_at=time.time(),documents=final['documents'],store_id=final['store_id'])
   save();seal('owner37-reserve-audit',result)
   print(json.dumps(dict(complete=True,business_writes=0,runtime_ledger_writes=0)))
