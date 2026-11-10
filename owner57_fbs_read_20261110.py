"""Read current managed FBS for owner bag57; no stock writes or order scans."""
import json,time,math
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_shared_requests import SharedRequests
from stock_execution_fence import cloud_writer
from stock_approved_warehouses import install,APPROVED
from stock_regular_service import restored_cards
from stock_ozon_source import collect as ozcollect
ART='57-noelbag-burgundy'
ROOT='technical:owner57-fbs-read:2026-11-10'
with runtime_db() as lock:
 with cloud_writer(lock):
  with runtime_db() as db:
   store=Store(db,postgres=True);shared=SharedRequests(store)
   g.STOCK_REQUEST_GATE=shared;g.STOCK_SHARED_ORDERS=shared
   g._CACHE_GET=lambda k:None;g._CACHE_SET=lambda *a:None;g.check_run_budget=lambda:None
   install(g)
   source=json.loads(store.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-10:0700',)).fetchone()[0])['source']
   cards=restored_cards(source);result=dict(article=ART,started_at=time.time(),business_writes=0,rows=[])
   for cab in range(3):
    ids=g.article_size_ids(cards[cab]).get(ART,set());observed=time.time()
    if not ids:
     result['rows'].append(dict(cabinet=cab,quantity=None,card_absent_in_reference=True,reference_observed_at=source['started']));continue
    data=g.api('POST',g.WB_MARKET+'/api/v3/stocks/'+str(APPROVED[cab][0]),g.cabinet_tokens()[cab],json={'chrtIds':sorted(ids)},retry_read_network=True)
    rows=data.get('stocks');values={}
    if not isinstance(rows,list):raise Stopped('Stock coverage missing')
    for row in rows:
     ident=row.get('chrtId');q=row.get('amount')
     if ident not in ids or ident in values or type(q) not in(int,float) or not math.isfinite(q) or q<0 or int(q)!=q:raise Stopped('Stock identity or quantity unknown')
     values[ident]=int(q)
    if set(values)!=ids:raise Stopped('Stock coverage incomplete')
    result['rows'].append(dict(cabinet=cab,warehouse=APPROVED[cab][0],quantity=sum(values.values()),observed_at=observed))
   oz=ozcollect(g,{ART},saved_orders=source['ozon']['sales'])
   result['rows'].append(dict(cabinet=3,quantity=oz['stocks'].get(ART),working_offer=ART in oz['locations'],observed_at=oz['started']))
   result.update(complete=True,finished_at=time.time(),total_fbs=sum(r['quantity'] for r in result['rows'] if r.get('quantity') is not None))
   with store.transaction():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
   seal('owner57-fbs-read',result)
   print(json.dumps(dict(complete=True,business_writes=0)))
